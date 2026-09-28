from __future__ import annotations

from ..config import Settings
from .base import WeatherProvider
from .open_meteo import OpenMeteoProvider


def build_providers(settings: Settings) -> dict[str, WeatherProvider]:
    """IMD, CHIRPS, ERA5-direct and ECMWF S2S are intentionally NOT registered: no verified
    programmatic access has been confirmed. See docs/DATA_SOURCES.md."""
    om = OpenMeteoProvider(settings.open_meteo_forecast_url, settings.open_meteo_archive_url,
                           settings.request_timeout_s, settings.max_retries)
    return {om.info.name: om}
