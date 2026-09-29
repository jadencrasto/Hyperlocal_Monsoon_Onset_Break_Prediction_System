"""Open-Meteo provider (no API key; free for non-commercial use, CC BY 4.0 attribution required).

Forecast endpoint : /v1/forecast  (daily=precipitation_sum, up to 16 days)
History endpoint  : archive API   (ERA5-family reanalysis; NOT gauge observations)
Both return a model grid-cell value (roughly 10-25 km), not a village-scale measurement.
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Callable

import requests

from .base import (
    CATEGORY_HTTP, CATEGORY_INVALID_DATA, CATEGORY_MALFORMED, CATEGORY_NETWORK,
    CATEGORY_TIMEOUT, DailyRecord, ProviderError, ProviderInfo, WeatherProvider,
)

log = logging.getLogger(__name__)
TZ = "Asia/Kolkata"
MAX_FORECAST_DAYS = 16


class OpenMeteoProvider(WeatherProvider):
    info = ProviderInfo(
        name="open_meteo",
        description="Open-Meteo: global model forecast + ERA5-based reanalysis history",
        history_kind="reanalysis",
        provides_forecast=True,
        forecast_horizon_days=MAX_FORECAST_DAYS,
        spatial_note="Model grid cell (~10-25 km). Not a block/village measurement.",
        requires_key=False,
        usage_note="Free for non-commercial use, attribution CC BY 4.0. Daily request cap applies "
                   "(documented as ~10,000/day; verify at open-meteo.com/en/terms).",
    )

    def __init__(self, forecast_url: str, archive_url: str, timeout_s: float = 10.0,
                 max_retries: int = 2, session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.forecast_url, self.archive_url = forecast_url, archive_url
        self.timeout_s, self.max_retries = timeout_s, max_retries
        self.session = session or requests.Session()
        self._sleep = sleep

    # -- HTTP with bounded retries -------------------------------------------------
    def _get(self, url: str, params: dict) -> dict:
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout_s)
            except requests.Timeout as exc:
                last = exc
                log.warning("open_meteo timeout (attempt %d): %s", attempt + 1, exc)
            except requests.ConnectionError as exc:
                last = exc
                log.warning("open_meteo network error (attempt %d): %s", attempt + 1, exc)
            else:
                if resp.status_code == 429:
                    raise ProviderError(
                        "Open-Meteo rate limit reached (HTTP 429); try again later",
                        CATEGORY_HTTP)
                if 500 <= resp.status_code < 600:
                    last = ProviderError(f"HTTP {resp.status_code}", CATEGORY_HTTP)
                    log.warning("open_meteo server error %s (attempt %d)", resp.status_code, attempt + 1)
                elif resp.status_code >= 400:
                    raise ProviderError(
                        f"Open-Meteo rejected request: HTTP {resp.status_code}", CATEGORY_HTTP)
                else:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise ProviderError(
                            "Open-Meteo returned non-JSON body", CATEGORY_MALFORMED) from exc
            if attempt < self.max_retries:
                self._sleep(0.5 * 2 ** attempt)
        # Exhausted retries: classify what finally went wrong (timeout vs network vs HTTP).
        if isinstance(last, requests.Timeout):
            raise ProviderError(
                f"Open-Meteo timed out after {self.max_retries + 1} attempts", CATEGORY_TIMEOUT)
        if isinstance(last, requests.ConnectionError):
            raise ProviderError(
                f"Open-Meteo unreachable after {self.max_retries + 1} attempts: {last}",
                CATEGORY_NETWORK)
        raise last if isinstance(last, ProviderError) else ProviderError(str(last), CATEGORY_HTTP)

    @staticmethod
    def _parse_daily(payload: dict) -> list[DailyRecord]:
        daily = payload.get("daily") if isinstance(payload, dict) else None
        if not isinstance(daily, dict):
            raise ProviderError("Malformed Open-Meteo response: missing 'daily'", CATEGORY_MALFORMED)
        times, vals = daily.get("time"), daily.get("precipitation_sum")
        if not isinstance(times, list) or not isinstance(vals, list) or len(times) != len(vals):
            raise ProviderError(
                "Malformed Open-Meteo response: 'time'/'precipitation_sum' mismatch",
                CATEGORY_MALFORMED)
        out = []
        for t, v in zip(times, vals):
            try:
                d = date.fromisoformat(t)
            except (TypeError, ValueError) as exc:
                raise ProviderError(
                    f"Malformed date in Open-Meteo response: {t!r}", CATEGORY_MALFORMED) from exc
            if v is not None and (not isinstance(v, (int, float)) or v < 0):
                raise ProviderError(f"Invalid precipitation value: {v!r}", CATEGORY_INVALID_DATA)
            out.append(DailyRecord(d, None if v is None else float(v)))
        return out

    # -- interface -----------------------------------------------------------------
    def fetch_forecast(self, lat: float, lon: float, days: int) -> list[DailyRecord]:
        days = max(1, min(days, MAX_FORECAST_DAYS))
        payload = self._get(self.forecast_url, {
            "latitude": lat, "longitude": lon, "daily": "precipitation_sum",
            "forecast_days": days, "timezone": TZ})
        return self._parse_daily(payload)

    def fetch_history(self, lat: float, lon: float, start: date, end: date) -> list[DailyRecord]:
        if start > end:
            raise ProviderError("start date after end date")
        payload = self._get(self.archive_url, {
            "latitude": lat, "longitude": lon, "daily": "precipitation_sum",
            "start_date": start.isoformat(), "end_date": end.isoformat(), "timezone": TZ})
        return self._parse_daily(payload)
