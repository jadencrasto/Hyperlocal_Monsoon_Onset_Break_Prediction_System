"""Common provider interface. Swap a provider by implementing WeatherProvider and registering it."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


class ProviderError(Exception):
    """Provider unreachable, rate-limited, or returned something we cannot trust."""


class NotSupported(ProviderError):
    """Provider does not offer this capability."""


@dataclass(frozen=True)
class DailyRecord:
    date: date
    precip_mm: float | None


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    description: str
    history_kind: str | None          # 'observation' | 'reanalysis' | None
    provides_forecast: bool
    forecast_horizon_days: int | None
    spatial_note: str
    requires_key: bool
    usage_note: str


class WeatherProvider(ABC):
    info: ProviderInfo

    @abstractmethod
    def fetch_forecast(self, lat: float, lon: float, days: int) -> list[DailyRecord]: ...

    @abstractmethod
    def fetch_history(self, lat: float, lon: float, start: date, end: date) -> list[DailyRecord]: ...
