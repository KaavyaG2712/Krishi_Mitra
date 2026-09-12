from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded only from the local backend .env file."""

    app_name: str = "KrishiMitra API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://krishimitra:krishimitra_local_only@localhost:5432/krishimitra"
    frontend_origins: str = "http://localhost:5173"
    gemini_api_key: str | None = None
    gemini_generation_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-2"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
