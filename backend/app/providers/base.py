"""Common provider interface. Swap a provider by implementing WeatherProvider and registering it."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


# Failure categories (Step 25). Kept as plain strings — no error framework.
# network_failure | timeout | http_failure | malformed_response | invalid_data
CATEGORY_NETWORK = "network_failure"
CATEGORY_TIMEOUT = "timeout"
CATEGORY_HTTP = "http_failure"
CATEGORY_MALFORMED = "malformed_response"
CATEGORY_INVALID_DATA = "invalid_data"


class ProviderError(Exception):
    """Provider unreachable, rate-limited, or returned something we cannot trust.

    `category` is a stable machine-readable failure class (Step 25) so callers can
    distinguish network/timeout/HTTP/malformed/invalid without parsing the message.
    It is factual provenance about the *failure* — never about the weather."""

    def __init__(self, message: str, category: str = CATEGORY_HTTP):
        super().__init__(message)
        self.category = category


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
