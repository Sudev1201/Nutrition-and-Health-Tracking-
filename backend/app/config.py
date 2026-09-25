from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor"
    )
    test_database_url: str = (
        "postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test"
    )

    google_client_id: str = ""

    session_secret: str = "dev-only-insecure-secret-change-me"
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


settings = Settings()
