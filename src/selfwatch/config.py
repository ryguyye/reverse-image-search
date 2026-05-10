from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    serpapi_key: str | None = None
    tineye_api_key: str | None = None
    tineye_private_key: str | None = None
    max_results_per_provider: int = 25
    http_timeout: int = 30
    db_path: str = "selfwatch.db"
    public_base_url: str | None = None
    scheduler_tick_seconds: int = 60
    webhook_timeout: int = 10
    min_cadence_minutes: int = 5

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_use_ssl: bool = False
    smtp_starttls: bool = True
    smtp_timeout: int = 20

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
