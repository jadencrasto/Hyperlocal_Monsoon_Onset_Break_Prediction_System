"""Application settings. Values come from environment variables prefixed MONSOON_ or a .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MONSOON_", env_file=ROOT / ".env", extra="ignore")

    data_dir: Path = ROOT / "data"
    models_dir: Path = ROOT / "models"
    request_timeout_s: float = 10.0
    max_retries: int = 2
    forecast_stale_hours: float = 12.0
    connectivity_host: str = "api.open-meteo.com"
    connectivity_archive_host: str = "archive-api.open-meteo.com"
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'app' / 'monsoon.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
