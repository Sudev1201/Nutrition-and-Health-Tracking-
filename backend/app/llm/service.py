"""A user's own Anthropic API key: checked when saved, stored encrypted, never shown again.

The key belongs to the user, not the profile, so it lives in `user_settings`, a table a
profile save never touches. What the settings screen reads -- the provider, the model, the
last four characters and a status -- sits beside the ciphertext in plain columns, so a GET
never decrypts. `key_for` is the one place a key is decrypted, and it serves only the
signed-in user's own plan.

Services flush and never commit; the router commits.
"""

import datetime
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.llm import crypto
from app.llm.providers import Provider
from app.models.llm import UserSettings
from app.models.user import User

PROVIDER = "anthropic"
KEY_PATTERN = re.compile(r"^sk-ant-[A-Za-z0-9_-]+$")
# An Admin API key is an organisation credential: it manages members, keys and billing.
# Descriptions need an ordinary API key, and this server must never hold anything more.
ADMIN_PREFIX = "sk-ant-admin"
MIN_KEY_LENGTH = 20
MAX_KEY_LENGTH = 300
FORMAT_MESSAGE = "That doesn't look like an Anthropic API key"
KEY_STATUSES = ("ok", "rejected", "unreadable")


class InvalidKeyFormat(ValueError):
    """The key fails the format check. The message is always FORMAT_MESSAGE.

    Never the value: a key that fails the check can still be most of a real key.
    """

    def __init__(self) -> None:
        super().__init__(FORMAT_MESSAGE)


@dataclass(frozen=True)
class KeySummary:
    """What the settings screen may know about a key: everything but the key."""

    available: bool
    provider: str | None
    model: str | None
    hint: str | None
    status: str  # "none" | "ok" | "rejected" | "unreadable"


@dataclass(frozen=True)
class RotationCounts:
    rotated: int
    current: int
    unreadable: int


def normalise_key(raw: str) -> str:
    """The key as typed, stripped. InvalidKeyFormat unless it looks like an API key."""
    key = raw.strip()
    if not MIN_KEY_LENGTH <= len(key) <= MAX_KEY_LENGTH:
        raise InvalidKeyFormat
    if KEY_PATTERN.fullmatch(key) is None or key.startswith(ADMIN_PREFIX):
        raise InvalidKeyFormat
    return key


def summary(db: Session, user: User) -> KeySummary:
    """The user's key as the settings screen shows it. Never decrypts."""
    return _summary_of(_row(db, user))


def save_key(
    db: Session, user: User, *, api_key: str, model: str, provider: Provider
) -> KeySummary:
    """Check the key with the provider, then store it encrypted, replacing any earlier one.

    Nothing is written until the check has passed, and the provider's error propagates.
    A key Anthropic refuses, or one it could not be asked about, therefore leaves the
    earlier key exactly as it was.
    """
    if not crypto.available():
        raise crypto.NotConfigured
    provider.check_key(api_key, model)

    values = {
        "llm_provider": PROVIDER,
        "llm_model": model,
        # Encrypted here, before any SQL is built: the plaintext never reaches the database,
        # nor a SQLAlchemy error message, which quotes its bound parameters.
        "llm_key_ciphertext": crypto.encrypt(api_key, user_id=user.id),
        "llm_key_hint": api_key[-4:],
        "llm_key_status": "ok",
        "llm_key_set_at": datetime.datetime.now(datetime.UTC),
    }
    # One statement rather than a read and a write, so two saves at once cannot both insert.
    statement = insert(UserSettings).values(user_id=user.id, **values)
    statement = statement.on_conflict_do_update(constraint="uq_user_settings_user", set_=values)
    row = db.scalars(
        statement.returning(UserSettings),
        # The row may already be in this session's identity map, loaded earlier and still
        # held. Load what the statement wrote over it, not what the session remembers.
        execution_options={"populate_existing": True},
    ).one()
    return _summary_of(row)


def delete_key(db: Session, user: User) -> None:
    """Forget the key. Removing a key that is not there is not an error.

    The row stays, with all six key columns null, so a future setting that is not about
    the key survives the key's removal.
    """
    row = _row(db, user)
    if row is None:
        return
    row.llm_provider = None
    row.llm_model = None
    row.llm_key_ciphertext = None
    row.llm_key_hint = None
    row.llm_key_status = None
    row.llm_key_set_at = None
    db.flush()


def key_for(db: Session, user: User) -> tuple[str, str] | None:
    """The user's own key and model, decrypted, for polishing their own plan.

    None when there is no key to use: no row, no key, or a key whose status is not "ok".
    A key that no longer decrypts -- the keyring lost its key, or the row was copied from
    another user -- is marked "unreadable" and flushed, so the settings screen asks for
    it again, and is then treated as no key rather than a 500. The caller commits that
    mark. NotConfigured is raised before anything else, so a server with no keyring says
    so instead of telling the user to add a key they cannot save.
    """
    if not crypto.available():
        raise crypto.NotConfigured
    row = _row(db, user)
    if row is None or row.llm_key_ciphertext is None or row.llm_key_status != "ok":
        return None
    try:
        api_key = crypto.decrypt(row.llm_key_ciphertext, user_id=user.id)
    except crypto.Unreadable:
        row.llm_key_status = "unreadable"
        db.flush()
        return None
    return api_key, row.llm_model


def mark_status(db: Session, user: User, status: str) -> None:
    """Record what became of the stored key, such as "rejected" after Anthropic's 401."""
    if status not in KEY_STATUSES:
        raise ValueError(f"unknown key status {status!r}")
    row = _row(db, user)
    if row is None or row.llm_key_ciphertext is None:
        return
    row.llm_key_status = status
    db.flush()


def rotate_all(db: Session) -> RotationCounts:
    """Re-encrypt every stored key under the keyring's first key. Safe to re-run.

    Every token is opened, and its user binding checked against the row's user, whether
    it needs rotating or not. A key already under the first key and bound to its row's
    user is counted as current and left as it is. A key no key in the keyring can read,
    or one bound to another user, is marked unreadable and left in place for its owner
    to replace.

    The rows are locked for the run. Otherwise a key saved while the script runs could
    be overwritten by the rotated copy of the key it had just replaced.
    """
    rows = db.scalars(
        select(UserSettings)
        .where(UserSettings.llm_key_ciphertext.is_not(None))
        .order_by(UserSettings.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()

    rotated = current = unreadable = 0
    for row in rows:
        token = row.llm_key_ciphertext
        try:
            fresh = None if crypto.is_current(token) else crypto.rotate(token)
            # MultiFernet re-encrypts whatever any key decrypts, and is_current checks only
            # which key a token is under. The user binding is checked here, on every token,
            # so a row copied from another user is neither counted current nor given a
            # fresh token.
            crypto.decrypt(fresh or token, user_id=row.user_id)
        except crypto.Unreadable:
            row.llm_key_status = "unreadable"
            unreadable += 1
            continue
        if fresh is None:
            current += 1
        else:
            row.llm_key_ciphertext = fresh
            rotated += 1
    db.flush()
    return RotationCounts(rotated=rotated, current=current, unreadable=unreadable)


def _row(db: Session, user: User) -> UserSettings | None:
    return db.scalars(select(UserSettings).where(UserSettings.user_id == user.id)).one_or_none()


def _summary_of(row: UserSettings | None) -> KeySummary:
    available = crypto.available()
    if row is None or row.llm_key_ciphertext is None:
        return KeySummary(available=available, provider=None, model=None, hint=None, status="none")
    return KeySummary(
        available=available,
        provider=row.llm_provider,
        model=row.llm_model,
        hint=row.llm_key_hint,
        status=row.llm_key_status,
    )
