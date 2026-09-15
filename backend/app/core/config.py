from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded only from the local backend .env file."""

    app_name: str = "KrishiMitra API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://krishimitra:krishimitra_local_only@localhost:5432/krishimitra"
    frontend_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    gemini_api_key: str | None = None
    gemini_generation_model: str = "gemini-3.6-flash"
    gemini_embedding_model: str = "gemini-embedding-2"
    model_artifact_dir: Path = Path(__file__).resolve().parents[3] / "models" / "checkpoints" / "mobilenetv2-10class-v1"
    # Below this threshold, return the closest supported label as uncertain.
    # Non-leaf rejection is handled separately before model inference.
    health_confidence_threshold: float = 0.75

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
