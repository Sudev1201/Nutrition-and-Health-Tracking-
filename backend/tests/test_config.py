"""Settings: what production refuses, and the database URL forms hosts hand out.

Every Settings here is built with `_env_file=None`, and the fixture below takes
every setting out of the process environment, so neither a developer's
backend/.env nor CI's exported DATABASE_URL can decide an outcome.
"""

import pytest
from pydantic import ValidationError

from app.config import DEV_SESSION_SECRET, Settings

# Production-shaped and safe. Each refusal below changes one of these.
CLEAN_PRODUCTION = {
    "app_env": "production",
    "session_secret": "s" * 48,
    "google_client_id": "1234567890-abcdef.apps.googleusercontent.com",
    "cookie_secure": True,
    "frontend_origin": "https://app.test.invalid",
    "database_url": "postgresql+psycopg://hm:db-password@db.test.invalid:5432/hm?sslmode=require",
}

# The wording is pinned here, not imported: the image check in CI and the
# deploy runbook quote it.
SECRET = "SESSION_SECRET is the development default or shorter than 32 characters"
CLIENT_ID = "GOOGLE_CLIENT_ID is empty"
COOKIE = "COOKIE_SECURE must be true"
ORIGIN = "FRONTEND_ORIGIN must be an https:// origin with no trailing slash"
DATABASE = "DATABASE_URL points at localhost"
PLACEHOLDER_ORIGIN = "FRONTEND_ORIGIN is still the example.com placeholder"
PLACEHOLDER_DATABASE = "DATABASE_URL is still the example.com placeholder"


@pytest.fixture(autouse=True)
def bare_environment(monkeypatch):
    """Only what a test passes reaches Settings."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def refusal(**unsafe: object) -> str:
    """The one error Settings refuses CLEAN_PRODUCTION with, once `unsafe` is applied."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, **{**CLEAN_PRODUCTION, **unsafe})
    [error] = excinfo.value.errors()
    return str(error["ctx"]["error"])


# --- production --------------------------------------------------------------------------


def test_a_clean_production_config_loads():
    configured = Settings(_env_file=None, **CLEAN_PRODUCTION)

    assert configured.app_env == "production"
    assert configured.database_url == CLEAN_PRODUCTION["database_url"]


@pytest.mark.parametrize(
    ("unsafe", "problem"),
    [
        pytest.param({"session_secret": DEV_SESSION_SECRET}, SECRET, id="development-secret"),
        pytest.param({"session_secret": "s" * 31}, SECRET, id="short-secret"),
        pytest.param({"google_client_id": ""}, CLIENT_ID, id="no-client-id"),
        pytest.param({"google_client_id": "   "}, CLIENT_ID, id="blank-client-id"),
        pytest.param({"cookie_secure": False}, COOKIE, id="insecure-cookie"),
        pytest.param({"frontend_origin": "http://app.test.invalid"}, ORIGIN, id="http-origin"),
        pytest.param({"frontend_origin": "https://app.test.invalid/"}, ORIGIN, id="trailing-slash"),
        pytest.param({"frontend_origin": "https://app.test.invalid/app"}, ORIGIN, id="origin-path"),
        pytest.param(
            {"database_url": "postgresql+psycopg://hm:pw@localhost:5432/hm"},
            DATABASE,
            id="localhost-database",
        ),
        pytest.param(
            {"database_url": "postgresql+psycopg://hm:pw@127.0.0.1/hm"},
            DATABASE,
            id="loopback-database",
        ),
        # Normalised first, then checked.
        pytest.param(
            {"database_url": "postgres://hm:pw@localhost/hm"}, DATABASE, id="libpq-localhost"
        ),
        # fly.toml's placeholders, left in place.
        pytest.param(
            {"frontend_origin": "https://app.example.com"},
            PLACEHOLDER_ORIGIN,
            id="placeholder-origin",
        ),
        pytest.param(
            {"frontend_origin": "https://example.com"},
            PLACEHOLDER_ORIGIN,
            id="placeholder-apex-origin",
        ),
        pytest.param(
            {"frontend_origin": "https://APP.Example.COM:8443"},
            PLACEHOLDER_ORIGIN,
            id="placeholder-origin-any-case",
        ),
        pytest.param(
            {"database_url": "postgresql+psycopg://hm:pw@db.example.com:5432/hm"},
            PLACEHOLDER_DATABASE,
            id="placeholder-database",
        ),
        pytest.param(
            {"database_url": "postgres://hm:pw@example.com/hm"},
            PLACEHOLDER_DATABASE,
            id="placeholder-apex-database",
        ),
    ],
)
def test_each_unsafe_setting_is_refused_on_its_own(unsafe, problem):
    assert refusal(**unsafe) == f"Refusing to start in production: {problem}"


def test_every_problem_is_named_at_once():
    """The development defaults, as a first deploy that forgot every secret has them."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, app_env="production")

    [error] = excinfo.value.errors()
    assert str(error["ctx"]["error"]) == (
        f"Refusing to start in production: {SECRET}; {CLIENT_ID}; {COOKIE}; {ORIGIN}; {DATABASE}"
    )


def test_a_32_character_secret_is_long_enough():
    configured = Settings(_env_file=None, **{**CLEAN_PRODUCTION, "session_secret": "s" * 32})
    assert len(configured.session_secret) == 32


def test_a_port_on_the_origin_is_fine():
    origin = "https://app.test.invalid:8443"
    configured = Settings(_env_file=None, **{**CLEAN_PRODUCTION, "frontend_origin": origin})
    assert configured.frontend_origin == origin


@pytest.mark.parametrize(
    "origin",
    [
        pytest.param("https://app.notexample.com", id="ends-in-example-com-but-not-under-it"),
        pytest.param("https://example.com.test.invalid", id="example-com-as-a-subdomain"),
    ],
)
def test_only_example_com_and_names_under_it_are_placeholders(origin):
    configured = Settings(_env_file=None, **{**CLEAN_PRODUCTION, "frontend_origin": origin})
    assert configured.frontend_origin == origin


def test_both_placeholders_are_named_at_once_and_never_quoted():
    """As a first deploy that kept fly.toml's origin and pasted a docs example URL."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            **{
                **CLEAN_PRODUCTION,
                "frontend_origin": "https://app.example.com",
                "database_url": "postgresql+psycopg://hm:s3cret-pw@db.example.com/hm",
            },
        )

    [error] = excinfo.value.errors()
    assert str(error["ctx"]["error"]) == (
        f"Refusing to start in production: {PLACEHOLDER_ORIGIN}; {PLACEHOLDER_DATABASE}"
    )
    message = str(excinfo.value)
    assert "app.example.com" not in message
    assert "db.example.com" not in message
    assert "s3cret-pw" not in message


def test_the_refusal_never_repeats_a_value():
    """Pydantic's message would otherwise end with its input: on a platform's log
    stream, the tail of DATABASE_URL or the session secret."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            app_env="production",
            session_secret="short-secret",
            database_url="postgresql+psycopg://hm:s3cret-pw@localhost/hm",
        )

    message = str(excinfo.value)
    assert "Refusing to start in production" in message
    assert "short-secret" not in message
    assert "s3cret-pw" not in message


def test_app_env_is_read_from_the_environment(monkeypatch):
    """As fly.toml's [env] sets it."""
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(ValidationError, match="Refusing to start in production"):
        Settings(_env_file=None)


def test_a_misspelt_app_env_is_refused_rather_than_read_as_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")

    with pytest.raises(ValidationError, match="app_env"):
        Settings(_env_file=None)


# --- development -------------------------------------------------------------------------


def test_development_accepts_the_defaults():
    configured = Settings(_env_file=None)

    assert configured.app_env == "development"
    assert configured.session_secret == DEV_SESSION_SECRET
    assert configured.google_client_id == ""
    assert configured.cookie_secure is False
    assert configured.frontend_origin == "http://localhost:5173"
    assert "@localhost:5433/" in configured.database_url


# --- database URLs -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "used"),
    [
        pytest.param(
            "postgres://hm:pw@db.example.com/hm",
            "postgresql+psycopg://hm:pw@db.example.com/hm",
            id="postgres",
        ),
        pytest.param(
            "postgresql://hm:pw@db.example.com/hm?sslmode=require",
            "postgresql+psycopg://hm:pw@db.example.com/hm?sslmode=require",
            id="postgresql",
        ),
        pytest.param(
            "postgresql+psycopg://hm:pw@db.example.com/hm",
            "postgresql+psycopg://hm:pw@db.example.com/hm",
            id="already-psycopg",
        ),
        pytest.param(
            "postgres://hm:p%40ss@db.example.com/hm",
            "postgresql+psycopg://hm:p%40ss@db.example.com/hm",
            id="encoded-password-kept",
        ),
        pytest.param("sqlite:///scratch.db", "sqlite:///scratch.db", id="not-postgres"),
    ],
)
def test_database_urls_are_pointed_at_psycopg(given, used):
    configured = Settings(_env_file=None, database_url=given, test_database_url=given)

    assert (configured.database_url, configured.test_database_url) == (used, used)


def test_a_database_url_from_the_environment_is_normalised_too(monkeypatch):
    """The way a platform secret arrives."""
    monkeypatch.setenv("DATABASE_URL", "postgres://hm:pw@db.example.com/hm")

    assert Settings(_env_file=None).database_url == "postgresql+psycopg://hm:pw@db.example.com/hm"
