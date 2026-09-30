"""Local cache management for weather observations and forecasts.
Handles freshness/TTL policies, failure cooldown to avoid hammering failed APIs,
and validation of cached data before prediction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import DailyRainfall, ForecastRainfall, SyncLog

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class CacheValidity:
    is_valid: bool
    status: str  # "valid" | "no_data" | "too_old" | "insufficient"
    message: str | None = None
    latest_date: date | None = None
    data_age_days: int | None = None
    last_fetched_at: datetime | None = None
    provider: str | None = None


class CacheManager:
    """Manages local SQLite cache policies, TTL, failure cooldown, and health checks."""

    def __init__(self, settings: Settings):
        self.settings = settings
        # In-memory fast cooldown tracker: (location_id, provider) -> failure timestamp
        self._failure_cooldowns: dict[tuple[int, str], float] = {}
        # In-memory last sync attempt tracker: (location_id, provider) -> timestamp
        self._last_sync_attempts: dict[tuple[int, str], float] = {}

    def get_last_observation_sync(self, session: Session, location_id: int) -> tuple[datetime | None, str | None]:
        """Returns (latest_fetched_at, provider) for recent observations of a location."""
        row = session.execute(
            select(DailyRainfall.fetched_at, DailyRainfall.provider)
            .where(DailyRainfall.location_id == location_id)
            .order_by(DailyRainfall.fetched_at.desc())
            .limit(1)
        ).first()
        if row:
            return row[0], row[1]
        return None, None

    def is_cache_fresh(self, session: Session, location_id: int, provider: str,
                       ttl_minutes: float | None = None) -> bool:
        """Checks if local observation cache was refreshed within `ttl_minutes`."""
        ttl = ttl_minutes if ttl_minutes is not None else self.settings.cache_ttl_minutes
        now_ts = utcnow().timestamp()
        key = (location_id, provider)
        if key in self._last_sync_attempts:
            if now_ts - self._last_sync_attempts[key] < (ttl * 60.0):
                return True
        return False

    def record_sync_attempt(self, location_id: int, provider: str) -> None:
        """Records a successful sync attempt time to prevent redundant fetches within TTL."""
        self._last_sync_attempts[(location_id, provider)] = utcnow().timestamp()

    def is_in_failure_cooldown(self, session: Session, location_id: int, provider: str,
                               cooldown_seconds: float | None = None) -> bool:
        """Determines if the API recently failed for this location so we do not repeatedly hammer it."""
        cooldown = cooldown_seconds if cooldown_seconds is not None else self.settings.api_cooldown_seconds
        now_ts = utcnow().timestamp()
        key = (location_id, provider)

        # Check in-memory first
        if key in self._failure_cooldowns:
            fail_ts = self._failure_cooldowns[key]
            if fail_ts == 0.0:  # explicitly cleared
                return False
            if now_ts - fail_ts < cooldown:
                return True
            del self._failure_cooldowns[key]
            return False

        # Check sync_log within the cooldown window
        cutoff = utcnow() - timedelta(seconds=cooldown)
        recent_err = session.scalar(
            select(SyncLog.finished_at).where(
                SyncLog.location_id == location_id,
                SyncLog.provider == provider,
                SyncLog.status == "error",
                SyncLog.finished_at >= cutoff
            ).order_by(SyncLog.id.desc()).limit(1)
        )
        if recent_err is not None:
            last_ok = session.scalar(
                select(func.max(SyncLog.finished_at)).where(
                    SyncLog.location_id == location_id,
                    SyncLog.provider == provider,
                    SyncLog.status == "ok"
                )
            )
            if last_ok and last_ok >= recent_err:
                return False
            self._failure_cooldowns[key] = recent_err.timestamp()
            if now_ts - recent_err.timestamp() < cooldown:
                return True
        return False

    def record_failure(self, location_id: int, provider: str) -> None:
        """Records an API failure timestamp in memory to throttle immediate retry attempts."""
        self._failure_cooldowns[(location_id, provider)] = utcnow().timestamp()

    def clear_failure(self, location_id: int, provider: str) -> None:
        """Clears failure cooldown when API succeeds or recovers."""
        self._failure_cooldowns[(location_id, provider)] = 0.0

    def validate_cache_for_prediction(self, session: Session, location_id: int,
                                      as_of: date | None = None,
                                      max_age_days: int | None = None) -> CacheValidity:
        """Checks if local cached history is present, uncorrupted, and sufficiently fresh for prediction."""
        max_age = max_age_days if max_age_days is not None else self.settings.max_cache_age_days

        try:
            latest_date = session.scalar(
                select(func.max(DailyRainfall.date)).where(DailyRainfall.location_id == location_id)
            )
        except Exception as exc:
            log.error("Failed to query cache for location %s: %s", location_id, exc)
            return CacheValidity(
                is_valid=False, status="corrupted",
                message="Local cache data is corrupted or unreadable."
            )

        if latest_date is None:
            return CacheValidity(
                is_valid=False, status="no_data",
                message="No stored rainfall history for this location."
            )

        target_date = as_of or latest_date
        data_age_days = (date.today() - target_date).days
        last_fetched, provider = self.get_last_observation_sync(session, location_id)

        # If user did not provide an explicit historical as_of and the latest cached data is older than max_age_days
        if as_of is None and data_age_days > max_age:
            return CacheValidity(
                is_valid=False, status="too_old",
                message=f"Cached rainfall data is too old ({data_age_days} days old, max allowed {max_age} days).",
                latest_date=latest_date, data_age_days=data_age_days,
                last_fetched_at=last_fetched, provider=provider
            )

        return CacheValidity(
            is_valid=True, status="valid",
            latest_date=latest_date, data_age_days=data_age_days,
            last_fetched_at=last_fetched, provider=provider
        )
