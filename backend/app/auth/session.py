from datetime import UTC, datetime, timedelta

import jwt

from app.config import settings

_ALGORITHM = "HS256"


class InvalidSession(Exception):
    """Raised when a session cookie is missing, expired, or untrustworthy."""


def create_session_token(user_id: str, *, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(hours=settings.session_ttl_hours)
    payload = {
        "sub": user_id,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.session_secret, algorithm=_ALGORITHM)


def read_session_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidSession(str(exc)) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise InvalidSession("Session token carries no subject")
    return user_id
