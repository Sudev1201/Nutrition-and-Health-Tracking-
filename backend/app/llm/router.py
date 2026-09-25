"""The user's own Anthropic API key, for AI descriptions: GET, PUT and DELETE /settings/llm.

The key is write-only. PUT takes it in the JSON body -- never in a path or a query string,
which the access log records -- checks it with Anthropic and stores it encrypted. No
response carries it back: GET shows only its last four characters. A stolen session cookie
can therefore replace or remove a key, but never read one.

Every answer and refusal from these handlers says `Cache-Control: no-store`, so no browser
or proxy keeps a copy of it. The 401 for a missing session comes from the shared
`get_current_user` before any of this runs, and carries no key. No profile is needed: the
key belongs to the user.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, SecretStr
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.llm import crypto, service
from app.llm.providers import (
    DEFAULT_MODEL,
    MODEL_LABELS,
    MODELS,
    KeyRejected,
    ModelUnavailable,
    Provider,
    ProviderError,
    get_provider,
)
from app.models.user import User

router = APIRouter(prefix="/settings/llm", tags=["settings"])

NOT_SET_UP = "AI descriptions are not set up on this server"
UNREACHABLE = "Couldn't reach Anthropic to check the key. Nothing was saved."
REFUSED = "Anthropic refused this key"
MODEL_MESSAGE = "Your Anthropic account can't use {label}"
UNKNOWN_MODEL = "Choose one of the listed models"
# A body that failed validation before a handler here ran. app.main answers it with this,
# because FastAPI's own 422 would quote the input that failed, and that input is the key.
NOT_UNDERSTOOD = "The request was not understood"

# On every answer and refusal from these handlers: what this screen shows is nobody's to
# keep a copy of.
NO_STORE = "no-store"


class LlmKeyIn(BaseModel):
    # No Field constraints, deliberately: pydantic puts a failing value in its 422 body, and
    # this value is the key. The handler checks it instead, with fixed messages.
    api_key: SecretStr
    model: str = DEFAULT_MODEL


class LlmSettingsOut(BaseModel):
    # False when this server has no keyring: the feature is off here.
    available: bool
    provider: Literal["anthropic"] | None
    model: str | None
    # The key's last four characters, never the key.
    key_hint: str | None
    status: Literal["none", "ok", "rejected", "unreadable"]
    # The models this server offers, the default first.
    models: list[str]


def _out(summary: service.KeySummary) -> LlmSettingsOut:
    return LlmSettingsOut(
        available=summary.available,
        provider=summary.provider,
        model=summary.model,
        key_hint=summary.hint,
        status=summary.status,
        models=list(MODELS),
    )


def _refuse(status_code: int, detail: str) -> HTTPException:
    """An error answer, uncached like every other answer here."""
    return HTTPException(status_code, detail, headers={"Cache-Control": NO_STORE})


@router.get("", response_model=LlmSettingsOut)
def read_llm_settings(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LlmSettingsOut:
    response.headers["Cache-Control"] = NO_STORE
    return _out(service.summary(db, user))


@router.put("", response_model=LlmSettingsOut)
def save_llm_key(
    payload: LlmKeyIn,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: Provider = Depends(get_provider),
) -> LlmSettingsOut:
    if payload.model not in MODELS:
        raise _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, UNKNOWN_MODEL)
    try:
        # The one place the secret is unwrapped: it goes from here to the service.
        api_key = service.normalise_key(payload.api_key.get_secret_value())
    except service.InvalidKeyFormat:
        raise _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, service.FORMAT_MESSAGE) from None
    if not crypto.available():
        # Checked before Anthropic is asked: a key this server cannot store is not sent.
        raise _refuse(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_SET_UP)

    try:
        summary = service.save_key(
            db, user, api_key=api_key, model=payload.model, provider=provider
        )
    except KeyRejected:
        raise _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, REFUSED) from None
    except ModelUnavailable:
        label = MODEL_LABELS[payload.model]
        raise _refuse(
            status.HTTP_422_UNPROCESSABLE_CONTENT, MODEL_MESSAGE.format(label=label)
        ) from None
    except ProviderError:
        # Unreachable, rate-limited or failing on Anthropic's side. NoCredit lands here too,
        # although a model lookup costs nothing and should never meet it.
        raise _refuse(status.HTTP_503_SERVICE_UNAVAILABLE, UNREACHABLE) from None
    db.commit()
    response.headers["Cache-Control"] = NO_STORE
    return _out(summary)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_key(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    # Works with the feature off too: a user can always take their key back.
    service.delete_key(db, user)
    db.commit()
    response.headers["Cache-Control"] = NO_STORE
