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


settings = Settings()
