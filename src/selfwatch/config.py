from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    serpapi_key: str | None = None
    tineye_api_key: str | None = None
    max_results_per_provider: int = 25
    http_timeout: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
