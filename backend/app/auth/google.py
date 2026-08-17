from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings


class InvalidGoogleToken(Exception):
    """Raised when a Google ID token cannot be trusted."""


@dataclass(frozen=True)
class GoogleIdentity:
    google_sub: str
    email: str
    name: str


def verify_google_id_token(raw_token: str) -> GoogleIdentity:
    try:
        claims = google_id_token.verify_oauth2_token(
            raw_token, google_requests.Request(), settings.google_client_id
        )
    except ValueError as exc:
        raise InvalidGoogleToken(str(exc)) from exc

    if not claims.get("email_verified", False):
        raise InvalidGoogleToken("Google account email is not verified")

    return GoogleIdentity(
        google_sub=claims["sub"],
        email=claims["email"],
        name=claims.get("name") or claims["email"],
    )
