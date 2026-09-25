"""The model behind AI descriptions: a Provider protocol, and one adapter on the Anthropic SDK.

The adapter makes two calls, both with the user's own key:
- `check_key` looks the chosen model up (`GET /v1/models/{id}`) when a key is saved. The
  lookup spends no tokens.
- `polish` asks for a description and a cooking tip for each dish in a batch, in one
  structured-output call.

What goes out is only what `app.planner.polish` hands over: an opaque reference, a dish name
and ingredient names. What comes back is returned unfiltered, because `polish` owns the guard.

Every SDK error, and a 200 that is not a message, becomes one of four `ProviderError`s, which
carry nothing from the provider's message: that message can quote the request. The log line
names the error class and the status code, and never uses `str(exc)`.
"""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic
import httpx2
from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)

MODELS: tuple[str, ...] = ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5")
DEFAULT_MODEL = "claude-opus-5"
MODEL_LABELS: Mapping[str, str] = {
    "claude-opus-5": "Claude Opus 5",
    "claude-sonnet-5": "Claude Sonnet 5",
    "claude-haiku-4-5": "Claude Haiku 4.5",
}
# The models that take `output_config.effort`. Claude Haiku 4.5 answers a 400 to it.
EFFORT_MODELS: frozenset[str] = frozenset({"claude-opus-5", "claude-sonnet-5"})
# The models sent with Anthropic's server-side refusal fallback. Whether the other two accept
# `fallbacks="default"` is not verified, and a 400 there would break polish for their users.
FALLBACK_MODELS: frozenset[str] = frozenset({"claude-opus-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Pinned, so an ANTHROPIC_BASE_URL in the server's environment cannot send users' keys to
# another host.
BASE_URL = "https://api.anthropic.com"
# Part of every cached description's hash: bumping it re-describes every dish once.
PROMPT_VERSION = 1

# The system prompt, verbatim: ten lines. The output schema is prompt too: the model reads
# PolishBatch's and _DishOut's class names, field names and any docstring. Changing either
# means bumping PROMPT_VERSION, so every cached description is written again under the new
# rules.
SYSTEM_PROMPT = (
    "You write short, friendly descriptions of South Indian home-cooked dishes for a"
    " meal-planning app.\n"
    "Each dish comes with a reference, its name, and the names of its ingredients as a"
    ' food-composition table lists them (for example "Rice, parboiled, milled").\n'
    "For every reference, return:\n"
    "- description: one sentence of at most 25 words on what the dish is and how it"
    " tastes.\n"
    "- cooking_note: one practical tip of at most 30 words for cooking it at home, or null"
    " when you have nothing useful to add.\n"
    "Rules:\n"
    "- Never mention amounts, portions, weights, calories, nutrients, percentages or any"
    " number, in digits or in words.\n"
    "- Never give medical, dietary or health advice, and never suggest changing the dish or"
    " its ingredients.\n"
    "- Write plain English; regional dish names are fine.\n"
    "- Return every reference you were given exactly once, and no others."
)


class ProviderError(Exception):
    """A provider call failed. Carries nothing from the provider's message."""


class KeyRejected(ProviderError):
    """The provider refused the key (401 or 403)."""


class ModelUnavailable(ProviderError):
    """The key's account cannot use the model (404)."""


class NoCredit(ProviderError):
    """The key's account has no credit left (402)."""


class ProviderUnavailable(ProviderError):
    """No usable answer: connection, timeout, 429, 5xx, or any other status."""


@dataclass(frozen=True)
class DishBrief:
    """All the model is told about one dish."""

    ref: str  # an opaque reference for this call only: "d1", "d2", ...
    name: str
    ingredients: tuple[str, ...]  # ingredient names, sorted


@dataclass(frozen=True)
class DishText:
    """What the model wrote for one dish, before any guard."""

    description: str
    cooking_note: str | None


class Provider(Protocol):
    def check_key(self, api_key: str, model: str) -> None: ...

    def polish(
        self, api_key: str, model: str, dishes: Sequence[DishBrief]
    ) -> dict[str, DishText]: ...


# The structured output polish asks for. The SDK sends these two classes to the model as a
# JSON schema, and pydantic would put a class docstring into it as the object's
# "description". So their notes are comments, and changing the classes means bumping
# PROMPT_VERSION. `extra="forbid"` puts `additionalProperties: false` on every object,
# which structured outputs require.
class _DishOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    description: str
    cooking_note: str | None


class PolishBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dishes: list[_DishOut]


def _default_http_client() -> httpx2.Client | None:
    """The HTTP client for a provider built without one: None, so the SDK builds its own.

    `tests/conftest.py` replaces this with a client that refuses every request, so no test
    can reach the network.
    """
    return None


class AnthropicProvider:
    """The Provider on the official SDK.

    A new SDK client per call, because every call carries its own user's key. `http_client`
    is for tests, which hand the SDK a mock transport.
    """

    def __init__(self, http_client: httpx2.Client | None = None) -> None:
        self._http_client = http_client

    def _client(self, api_key: str, *, timeout: float, max_retries: int) -> anthropic.Anthropic:
        # The SDK would send an empty key as an empty x-api-key header.
        if not api_key:
            raise ValueError("empty API key")
        http_client = self._http_client
        if http_client is None:
            http_client = _default_http_client()
        # An explicit api_key stops the SDK reading ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN
        # from the environment, and the explicit base_url beats ANTHROPIC_BASE_URL. With
        # http_client None, the SDK builds its own, which it closes when it is collected.
        return anthropic.Anthropic(
            api_key=api_key,
            base_url=BASE_URL,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )

    def check_key(self, api_key: str, model: str) -> None:
        """Raise unless this key can use this model. Spends no tokens."""
        # No retry: the user is waiting on the save, and a failed check saves nothing.
        client = self._client(api_key, timeout=10.0, max_retries=0)
        try:
            client.models.retrieve(model)
        except anthropic.APIError as exc:
            raise _translate(exc) from None

    def polish(self, api_key: str, model: str, dishes: Sequence[DishBrief]) -> dict[str, DishText]:
        """Text per reference, unfiltered, or {} when the model refused or was cut off."""
        client = self._client(api_key, timeout=120.0, max_retries=1)
        if not dishes:
            return {}
        options: dict[str, Any] = {}
        if model in EFFORT_MODELS:
            options["output_config"] = {"effort": "low"}
        if model in FALLBACK_MODELS:
            # A policy decline is re-run server-side on the model Anthropic recommends for it,
            # billed at that model's rates. The AI descriptions screen says so.
            options["betas"] = [FALLBACK_BETA]
            options["fallbacks"] = "default"
        try:
            # Non-streaming, and no temperature or top_p: the current models reject both.
            message = client.beta.messages.parse(
                model=model,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _batch_json(dishes)}],
                output_format=PolishBatch,
                **options,
            )
            stop_reason = message.stop_reason
            parsed = message.parsed_output
        except anthropic.APIError as exc:
            raise _translate(exc) from None
        except ValidationError:
            # A response cut off at max_tokens, or declined partway, ends in partial JSON, and
            # parse raises on it before the stop reason can be read. Not an error: the dishes
            # stay undescribed. The exception is not logged, because it quotes the output.
            logger.info("anthropic polish returned no text: the output did not parse")
            return {}
        except (AttributeError, TypeError, KeyError) as exc:
            # A 200 whose body is not a message: an HTML page from a proxy in between, or JSON
            # of another shape. The SDK does not validate a 200's body, so parse fails reading
            # it. No usable answer, like a 5xx. Logged by class name only, because the
            # exception's message can quote the body.
            logger.warning("anthropic call failed: %s (unreadable answer)", type(exc).__name__)
            raise ProviderUnavailable() from None
        # Stop reasons first: a refusal's or a cut-off's text is not an answer, even when it
        # happens to parse.
        if stop_reason in ("refusal", "max_tokens") or parsed is None:
            logger.info("anthropic polish returned no text: stop reason %s", stop_reason)
            return {}
        return {
            dish.ref: DishText(description=dish.description, cooking_note=dish.cooking_note)
            for dish in parsed.dishes
        }


def _batch_json(dishes: Sequence[DishBrief]) -> str:
    """The user message: each dish's reference, name and ingredient names, and nothing else."""
    return json.dumps(
        {
            "dishes": [
                {"ref": dish.ref, "name": dish.name, "ingredients": list(dish.ingredients)}
                for dish in dishes
            ]
        },
        ensure_ascii=False,
    )


def _translate(exc: anthropic.APIError) -> ProviderError:
    """The ProviderError for an SDK error, logged by class name and status code only.

    The caller raises it `from None`, so the SDK's error, whose message is the provider's own
    text and can quote the request, is not chained into the traceback either.
    """
    status = getattr(exc, "status_code", None)
    logger.warning("anthropic call failed: %s (status %s)", type(exc).__name__, status)
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return KeyRejected()
    if isinstance(exc, anthropic.NotFoundError):
        return ModelUnavailable()
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code == 402:
        return NoCredit()
    # Any other status (400, 408, 409, 413, 422, 429, 5xx), a connection error or a timeout.
    return ProviderUnavailable()


def get_provider() -> Provider:
    """The FastAPI dependency. API tests override it with conftest's FakeProvider."""
    return AnthropicProvider()
