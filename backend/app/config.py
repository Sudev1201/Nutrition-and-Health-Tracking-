from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The session secret's development default. It is public -- it is written right
# here -- so a server that signs sessions with it lets anyone sign one for any
# user. Production refuses it, and any secret shorter than 32 characters.
DEV_SESSION_SECRET = "dev-only-insecure-secret-change-me"
_MIN_SECRET_LENGTH = 32

# The URL forms Neon and Supabase hand out. SQLAlchemy no longer accepts
# postgres:// at all, and reads postgresql:// as psycopg2, which is not installed.
_LIBPQ_SCHEMES = ("postgres://", "postgresql://")
_PSYCOPG_SCHEME = "postgresql+psycopg://"

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# fly.toml and the runbook's examples use example.com, a name reserved for
# documentation (RFC 2606). A deploy that still points at it has not replaced
# the placeholder.
_PLACEHOLDER_DOMAIN = "example.com"


def _is_placeholder_host(host: str | None) -> bool:
    """`example.com` or any name under it, whatever its case."""
    if not host:
        return False
    host = host.lower().rstrip(".")
    return host == _PLACEHOLDER_DOMAIN or host.endswith("." + _PLACEHOLDER_DOMAIN)


def _is_https_origin(value: str) -> bool:
    """`https://host[:port]` and nothing after it.

    CORS compares FRONTEND_ORIGIN with the browser's Origin header character for
    character, and that header never carries a path or a trailing slash.
    """
    parts = urlsplit(value)
    return (
        value.startswith("https://")
        and bool(parts.hostname)
        and not parts.path
        and not parts.query
        and not parts.fragment
    )


class Settings(BaseSettings):
    # hide_input_in_errors: pydantic ends a validation message with the input it
    # was given. On a platform's log stream, a refusal would print the tail of
    # DATABASE_URL or a secret.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # "production" makes _refuse_unsafe_production below check the settings that
    # must never keep their development default. fly.toml sets it.
    app_env: Literal["development", "production"] = "development"

    database_url: str = (
        "postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor"
    )
    test_database_url: str = (
        "postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test"
    )

    google_client_id: str = ""

    session_secret: str = DEV_SESSION_SECRET
    session_cookie_name: str = "hm_session"
    session_ttl_hours: int = 720
    cookie_secure: bool = False

    frontend_origin: str = "http://localhost:5173"

    # Web push (VAPID). With either key empty, reminders are off on this server:
    # GET /push/public-key answers 503 and the Reminders screen says so. Both are
    # base64url strings; .env.example says how to generate a pair.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    # Who a push service contacts about this sender: a mailto: or https: URL.
    vapid_subject: str = "mailto:admin@example.com"

    # Sends reminders from the API process, checking every minute. Off by default:
    # every API test's TestClient runs the app's lifespan, and a loop there would
    # read the development database.
    scheduler_enabled: bool = False

    # AI descriptions (plan 9). Comma-separated Fernet keys: the first encrypts, every one
    # decrypts, so a new key goes first and an old one stays until scripts.rotate_llm_keys
    # has re-encrypted every row. Empty turns the feature off on this server. Never derived
    # from session_secret: rotating a leaked session secret must not destroy stored keys.
    llm_key_encryption_keys: str = ""

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _use_psycopg(cls, value: object) -> object:
        """Point a libpq-style URL at psycopg 3, the driver this project installs."""
        if isinstance(value, str):
            for scheme in _LIBPQ_SCHEMES:
                if value.startswith(scheme):
                    return _PSYCOPG_SCHEME + value.removeprefix(scheme)
        return value

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> Self:
        """In production, refuse every development default that is unsafe there.

        Every problem is named in one error, so a first deploy is fixed in one
        pass rather than one failed boot per setting. Reminders and AI
        descriptions are not required: without their keys they switch themselves
        off.
        """
        if self.app_env != "production":
            return self
        problems = []
        if (
            self.session_secret == DEV_SESSION_SECRET
            or len(self.session_secret) < _MIN_SECRET_LENGTH
        ):
            problems.append(
                "SESSION_SECRET is the development default or shorter than 32 characters"
            )
        if not self.google_client_id.strip():
            problems.append("GOOGLE_CLIENT_ID is empty")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true")
        if not _is_https_origin(self.frontend_origin):
            problems.append("FRONTEND_ORIGIN must be an https:// origin with no trailing slash")
        elif _is_placeholder_host(urlsplit(self.frontend_origin).hostname):
            problems.append("FRONTEND_ORIGIN is still the example.com placeholder")
        database_host = urlsplit(self.database_url).hostname
        if database_host in _LOCAL_HOSTS:
            problems.append("DATABASE_URL points at localhost")
        elif _is_placeholder_host(database_host):
            problems.append("DATABASE_URL is still the example.com placeholder")
        if problems:
            raise ValueError("Refusing to start in production: " + "; ".join(problems))
        return self


settings = Settings()
