from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Runtime configuration, loaded only from the local backend .env file."""

    app_name: str = "KrishiMitra API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://krishimitra:krishimitra_local_only@127.0.0.1:5433/krishimitra"
    frontend_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    gemini_api_key: str | None = None
    gemini_generation_model: str = "gemini-3.1-flash-lite"
    gemini_speech_model: str | None = None
    weatherapi_key: str | None = None
    model_artifact_dir: Path = Path(__file__).resolve().parents[3] / "models" / "checkpoints" / "mobilenetv2-10class-v1"
    # Below this threshold, return the closest supported label as uncertain.
    # Non-leaf rejection is handled separately before model inference.
    health_confidence_threshold: float = 0.75
    signing_secret: str | None = None
    soil_health_api_url: str = "https://soilhealth4.dac.gov.in/"
    soil_health_api_token: str | None = None
    soil_health_refresh_token: str | None = None
    soil_health_timeout_seconds: float = Field(default=12, ge=1, le=30)
    soil_health_cache_seconds: int = Field(default=900, ge=1, le=86400)
    # Enable only when the issued credentials authorize area-level disclosure.
    soil_health_area_access: bool = False
    soil_health_units_json: str = "{}"
    soil_health_demo: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
