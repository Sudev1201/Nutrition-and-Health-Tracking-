"""The Anthropic adapter, run on the real SDK with a mock transport.

No request leaves the process. Each provider here gets an httpx2 client whose transport
records the request and answers it in Anthropic's wire format, so these tests see exactly what
the SDK would send: the headers, the path and the JSON body.

The key is a secret. It must reach Anthropic's host in the x-api-key header and nowhere else:
not in a log line, not in an exception, not at a host an environment variable names. That
includes these tests' own failure output. pytest prints both sides of a failed comparison,
so the key is only ever compared inside a helper that returns a bool.
"""

import json
from collections.abc import Callable

import httpx2
import pytest

from app.llm import providers
from app.llm.providers import (
    DEFAULT_MODEL,
    EFFORT_MODELS,
    FALLBACK_BETA,
    FALLBACK_MODELS,
    MODEL_LABELS,
    MODELS,
    SYSTEM_PROMPT,
    AnthropicProvider,
    DishBrief,
    DishText,
    KeyRejected,
    ModelUnavailable,
    NoCredit,
    ProviderUnavailable,
)

KEY = "sk-ant-api03-" + "x" * 40 + "WXYZ"
# What every error body's message says. Anthropic's own messages can quote the request, so
# none of this may reach a log line or a ProviderError.
PROVIDER_MESSAGE = "provider-text-that-may-quote-the-request"

BRIEFS = (
    DishBrief(ref="d1", name="Idli", ingredients=("Black gram, dal", "Rice, parboiled, milled")),
    DishBrief(ref="d2", name="Mor kuzhambu", ingredients=("Curd", "Tamarind, pulp")),
)
OUTPUT = {
    "dishes": [
        {
            "ref": "d1",
            "description": "Soft steamed cakes of rice and black gram, mild and fluffy.",
            "cooking_note": "Let the batter ferment overnight somewhere warm.",
        },
        {
            "ref": "d2",
            "description": "A tangy curd curry, gently spiced and cooling.",
            "cooking_note": None,
        },
    ]
}
MODEL_INFO = {
    "type": "model",
    "id": "claude-opus-5",
    "display_name": "Claude Opus 5",
    "created_at": "2026-01-01T00:00:00Z",
}


class AnthropicStub:
    """A stand-in for api.anthropic.com: records every request, answers with `respond`."""

    def __init__(self, respond: Callable[[httpx2.Request], httpx2.Response]) -> None:
        self.respond = respond
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.respond(request)

    def provider(self) -> AnthropicProvider:
        return AnthropicProvider(http_client=httpx2.Client(transport=httpx2.MockTransport(self)))

    @property
    def request(self) -> httpx2.Request:
        assert len(self.requests) == 1, f"expected one request, got {len(self.requests)}"
        return self.requests[0]

    @property
    def body(self) -> dict:
        return json.loads(self.request.content)


def answering(response: httpx2.Response) -> AnthropicStub:
    return AnthropicStub(lambda request: response)


def message(stop_reason: str = "end_turn", text: str | None = None) -> httpx2.Response:
    """A Messages API answer with at most one text block."""
    content = [] if text is None else [{"type": "text", "text": text}]
    return httpx2.Response(
        200,
        json={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 120, "output_tokens": 80},
        },
    )


def error(status: int, kind: str) -> httpx2.Response:
    # retry-after-ms: the SDK honours it, so polish's one retry of a 429 or a 5xx waits a
    # millisecond instead of its half-second backoff.
    return httpx2.Response(
        status,
        headers={"retry-after-ms": "1"},
        json={"type": "error", "error": {"type": kind, "message": PROVIDER_MESSAGE}},
    )


def call(provider: AnthropicProvider, which: str, *, key: str = KEY):
    """Make one of the adapter's two calls, with the default model."""
    if which == "check_key":
        return provider.check_key(key, DEFAULT_MODEL)
    return provider.polish(key, DEFAULT_MODEL, BRIEFS)


def sends_the_key(request: httpx2.Request) -> bool:
    return request.headers.get("x-api-key") == KEY


def has_header(request: httpx2.Request, name: str) -> bool:
    return name in request.headers


def betas_sent(request: httpx2.Request) -> list[str]:
    return request.headers.get("anthropic-beta", "").split(",")


def key_logged(caplog) -> bool:
    return KEY in caplog.text


def provider_message_logged(caplog) -> bool:
    return PROVIDER_MESSAGE in caplog.text


def adapter_log(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == providers.__name__]


# --- the models on offer -----------------------------------------------------


def test_the_default_model_is_listed_first_and_every_model_has_a_label():
    assert MODELS[0] == DEFAULT_MODEL == "claude-opus-5"
    assert set(MODEL_LABELS) == set(MODELS)
    assert FALLBACK_MODELS <= set(MODELS)
    assert EFFORT_MODELS <= set(MODELS)


def test_the_system_prompt_is_ten_clean_lines():
    lines = SYSTEM_PROMPT.split("\n")

    assert len(lines) == 10
    assert all(line and line == line.strip() for line in lines)
    assert lines[6].startswith("- Never mention amounts, portions, weights")


# --- checking a key ----------------------------------------------------------


def test_a_key_is_checked_by_looking_the_model_up():
    anthropic = answering(httpx2.Response(200, json=MODEL_INFO))

    anthropic.provider().check_key(KEY, "claude-sonnet-5")

    request = anthropic.request
    assert request.method == "GET"
    assert str(request.url) == "https://api.anthropic.com/v1/models/claude-sonnet-5"
    assert sends_the_key(request), "the key is not in the x-api-key header"
    assert request.content == b""
    assert request.extensions["timeout"]["read"] == 10.0


def test_a_key_check_is_not_retried():
    anthropic = answering(error(500, "api_error"))

    with pytest.raises(ProviderUnavailable):
        anthropic.provider().check_key(KEY, DEFAULT_MODEL)

    assert len(anthropic.requests) == 1


def test_the_key_goes_to_anthropic_whatever_the_environment_says(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://llm-proxy.example.com")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-" + "e" * 40 + "ENVK")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "environment-token")
    anthropic = answering(httpx2.Response(200, json=MODEL_INFO))

    anthropic.provider().check_key(KEY, DEFAULT_MODEL)

    request = anthropic.request
    assert request.url.host == "api.anthropic.com"
    assert sends_the_key(request), "the key is not in the x-api-key header"
    assert not has_header(request, "authorization")


# --- polishing a batch -------------------------------------------------------


def test_polish_is_one_structured_call_at_low_effort():
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    anthropic.provider().polish(KEY, "claude-opus-5", BRIEFS)

    request, body = anthropic.request, anthropic.body
    assert request.method == "POST"
    assert request.url.host == "api.anthropic.com"
    assert request.url.path == "/v1/messages"
    assert sends_the_key(request), "the key is not in the x-api-key header"
    assert request.extensions["timeout"]["read"] == 120.0
    # Exactly these fields: no temperature or top_p, which the current models reject, and
    # no stream or thinking settings.
    assert set(body) == {
        "model",
        "max_tokens",
        "system",
        "messages",
        "output_config",
        "fallbacks",
    }
    assert body["model"] == "claude-opus-5"
    assert body["max_tokens"] == 8000
    assert body["system"] == SYSTEM_PROMPT
    assert body["output_config"]["effort"] == "low"
    output_format = body["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    schema = output_format["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["dishes"]
    # The schema is prompt too, and pydantic sends a class docstring as an object's
    # "description". No implementation note may reach the model that way.
    assert "description" not in schema
    assert all("description" not in definition for definition in schema["$defs"].values())


def test_claude_opus_5_is_sent_with_the_refusal_fallback():
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    anthropic.provider().polish(KEY, "claude-opus-5", BRIEFS)

    assert anthropic.body["fallbacks"] == "default"
    assert FALLBACK_BETA in betas_sent(anthropic.request)


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-haiku-4-5"])
def test_the_other_models_are_sent_without_it(model):
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    anthropic.provider().polish(KEY, model, BRIEFS)

    assert anthropic.body["model"] == model
    assert "fallbacks" not in anthropic.body
    # The SDK sends a beta header of its own for structured outputs; the fallback's is absent.
    assert FALLBACK_BETA not in betas_sent(anthropic.request)


@pytest.mark.parametrize(
    ("model", "effort"),
    [("claude-opus-5", "low"), ("claude-sonnet-5", "low"), ("claude-haiku-4-5", None)],
)
def test_effort_is_sent_only_to_the_models_that_take_it(model, effort):
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    anthropic.provider().polish(KEY, model, BRIEFS)

    output_config = anthropic.body["output_config"]
    assert output_config.get("effort") == effort
    assert output_config["format"]["type"] == "json_schema"


def test_the_model_sees_only_references_names_and_ingredient_names():
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    messages = anthropic.body["messages"]
    assert [item["role"] for item in messages] == ["user"]
    assert json.loads(messages[0]["content"]) == {
        "dishes": [
            {
                "ref": "d1",
                "name": "Idli",
                "ingredients": ["Black gram, dal", "Rice, parboiled, milled"],
            },
            {"ref": "d2", "name": "Mor kuzhambu", "ingredients": ["Curd", "Tamarind, pulp"]},
        ]
    }


def test_names_go_out_as_written_not_escaped():
    anthropic = answering(message(text=json.dumps({"dishes": []})))
    brief = DishBrief(ref="d1", name="Pongal — ven", ingredients=("Rice, raw, milled",))

    anthropic.provider().polish(KEY, DEFAULT_MODEL, [brief])

    assert "Pongal — ven" in anthropic.body["messages"][0]["content"]


def test_polish_returns_each_dishs_text_by_reference():
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    texts = anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    assert texts == {
        "d1": DishText(
            description="Soft steamed cakes of rice and black gram, mild and fluffy.",
            cooking_note="Let the batter ferment overnight somewhere warm.",
        ),
        "d2": DishText(
            description="A tangy curd curry, gently spiced and cooling.", cooking_note=None
        ),
    }


def test_polish_passes_the_text_through_unfiltered():
    """The guard belongs to app.planner.polish, which also drops references it never sent."""
    output = {
        "dishes": [{"ref": "d9", "description": "Serves 2, at 300 kcal.", "cooking_note": None}]
    }
    anthropic = answering(message(text=json.dumps(output)))

    texts = anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    assert texts == {"d9": DishText(description="Serves 2, at 300 kcal.", cooking_note=None)}


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(message("refusal"), id="refused-before-any-output"),
        pytest.param(message("refusal", '{"dishes": [{"ref": "d1", "desc'), id="refused-partway"),
        pytest.param(message("max_tokens", '{"dishes": [{"ref": "d1", "desc'), id="cut-off"),
        # The stop reason is read before the content: neither a refusal nor a cut-off answer
        # is an answer, even when its text parses.
        pytest.param(message("refusal", json.dumps(OUTPUT)), id="refused-but-it-parses"),
        pytest.param(message("max_tokens", json.dumps(OUTPUT)), id="cut-off-but-it-parses"),
        pytest.param(message("end_turn"), id="no-text-at-all"),
    ],
)
def test_a_refusal_or_a_cut_off_answer_yields_no_text(response):
    anthropic = answering(response)

    assert anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS) == {}


def test_an_empty_batch_is_not_sent():
    anthropic = answering(message(text=json.dumps(OUTPUT)))

    assert anthropic.provider().polish(KEY, DEFAULT_MODEL, []) == {}
    assert anthropic.requests == []


def test_polish_retries_once_then_gives_up():
    anthropic = answering(error(529, "overloaded_error"))

    with pytest.raises(ProviderUnavailable):
        anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    assert len(anthropic.requests) == 2


# --- failures ----------------------------------------------------------------


@pytest.mark.parametrize("which", ["check_key", "polish"])
@pytest.mark.parametrize(
    ("status", "kind", "expected"),
    [
        (401, "authentication_error", KeyRejected),
        (403, "permission_error", KeyRejected),
        (404, "not_found_error", ModelUnavailable),
        (402, "billing_error", NoCredit),
        (400, "invalid_request_error", ProviderUnavailable),
        (429, "rate_limit_error", ProviderUnavailable),
        (500, "api_error", ProviderUnavailable),
        (529, "overloaded_error", ProviderUnavailable),
    ],
)
def test_each_status_becomes_its_provider_error(which, status, kind, expected):
    anthropic = answering(error(status, kind))

    with pytest.raises(expected):
        call(anthropic.provider(), which)


def connection_refused(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("connection refused", request=request)


def timed_out(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ReadTimeout("timed out", request=request)


@pytest.mark.parametrize("which", ["check_key", "polish"])
@pytest.mark.parametrize("failure", [connection_refused, timed_out])
def test_an_unreachable_anthropic_is_unavailable(which, failure):
    anthropic = AnthropicStub(failure)

    with pytest.raises(ProviderUnavailable):
        call(anthropic.provider(), which)


@pytest.mark.parametrize("which", ["check_key", "polish"])
def test_an_empty_key_is_refused_before_any_request(which):
    anthropic = answering(httpx2.Response(200, json=MODEL_INFO))
    provider = anthropic.provider()

    with pytest.raises(ValueError, match="empty API key"):
        call(provider, which, key="")

    assert anthropic.requests == []


def test_a_failure_is_logged_by_error_class_and_status_only(caplog):
    anthropic = answering(error(401, "authentication_error"))

    with pytest.raises(KeyRejected) as raised:
        anthropic.provider().check_key(KEY, DEFAULT_MODEL)

    assert adapter_log(caplog) == ["anthropic call failed: AuthenticationError (status 401)"]
    assert not key_logged(caplog), "the key reached a log line"
    assert not provider_message_logged(caplog), "the provider's message reached a log line"
    # Nothing of the SDK's error rides along: no message, and no exception shown as its cause.
    assert str(raised.value) == ""
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True


def test_a_connection_failure_is_logged_without_a_status(caplog):
    with pytest.raises(ProviderUnavailable):
        AnthropicStub(connection_refused).provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    assert adapter_log(caplog) == ["anthropic call failed: APIConnectionError (status None)"]
    assert not key_logged(caplog), "the key reached a log line"


def test_a_200_that_is_not_a_message_is_unavailable(caplog):
    """An intercepting proxy's sign-in page, say. The SDK does not validate a 200's body."""
    page = f"<html><body><p>Sign in to continue. {PROVIDER_MESSAGE}</p></body></html>"
    anthropic = answering(httpx2.Response(200, headers={"content-type": "text/html"}, text=page))

    with pytest.raises(ProviderUnavailable) as raised:
        anthropic.provider().polish(KEY, DEFAULT_MODEL, BRIEFS)

    assert len(anthropic.requests) == 1
    assert adapter_log(caplog) == ["anthropic call failed: AttributeError (unreadable answer)"]
    assert not provider_message_logged(caplog), "the page reached a log line"
    assert str(raised.value) == ""
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True


# --- the no-network guard ----------------------------------------------------


def test_a_provider_built_without_a_client_never_reaches_the_network(no_llm_network, monkeypatch):
    """conftest's no_llm_network guard: the client the SDK would build refuses every request.

    Two things keep this self-check off the network when it fails. It asks for the guard by
    name, so without the guard pytest stops at setup and the check_key below never runs. And
    every proxy variable points at a closed local port, so an adapter that skipped
    _default_http_client, letting the SDK build a client of its own, is refused on this
    machine. Then the guard saw no request, and the last assertion says so. Both cases are
    set, because a lowercase variable beats its uppercase twin, and NO_PROXY is cleared,
    because it would route the request around the proxy.
    """
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:1")

    with pytest.raises(ProviderUnavailable):
        AnthropicProvider().check_key(KEY, DEFAULT_MODEL)

    # The guard's transport refused the one request: the adapter used _default_http_client.
    assert [request.url.host for request in no_llm_network] == ["api.anthropic.com"]


def test_the_dependency_is_the_anthropic_adapter():
    assert isinstance(providers.get_provider(), AnthropicProvider)
