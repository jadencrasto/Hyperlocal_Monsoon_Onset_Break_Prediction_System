"""Fetching, caching, offline fallback and freshness. Never substitutes synthetic data on failure."""
from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..models import DailyRainfall, ForecastRainfall, Location, SyncLog
from ..providers.base import ProviderError, WeatherProvider

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def tcp_connectivity(host: str, port: int = 443, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class SyncResult:
    status: str                # ok | error | skipped_offline
    provider: str
    kind: str                  # forecast | history
    n_records: int
    message: str | None
    finished_at: datetime


@dataclass
class ForecastSnapshot:
    provider: str
    retrieved_at: datetime
    age_hours: float
    stale: bool
    records: list[tuple[date, float | None]]


class WeatherService:
    FORECAST_DAYS = 16

    def __init__(self, session_factory: sessionmaker, providers: dict[str, WeatherProvider],
                 settings: Settings, connectivity: Callable[[str], bool] = tcp_connectivity):
        self.session_factory, self.providers, self.settings = session_factory, providers, settings
        self._connectivity = connectivity
        self._conn_cache: tuple[float, bool] | None = None

    # -- mode ----------------------------------------------------------------------
    def is_online(self) -> bool:
        now = time.monotonic()
        if self._conn_cache and now - self._conn_cache[0] < 15:
            return self._conn_cache[1]
        hosts = (self.settings.connectivity_host, self.settings.connectivity_archive_host)
        ok = all(bool(self._connectivity(host)) for host in hosts)
        self._conn_cache = (now, ok)
        return ok

    def effective_mode(self, preference: str) -> str:
        if preference in ("online", "offline"):
            return preference
        return "online" if self.is_online() else "offline"

    # -- refresh -------------------------------------------------------------------
    def _provider(self, name: str) -> WeatherProvider:
        try:
            return self.providers[name]
        except KeyError:
            raise ValueError(f"Unknown provider '{name}'. Available: {sorted(self.providers)}") from None

    def _log(self, session: Session, loc: Location, provider: str, kind: str, started: datetime,
             status: str, n: int, message: str | None) -> SyncResult:
        finished = utcnow()
        session.add(SyncLog(location_id=loc.id, provider=provider, kind=kind, started_at=started,
                            finished_at=finished, status=status, n_records=n, message=message))
        session.commit()
        return SyncResult(status, provider, kind, n, message, finished)

    def refresh_forecast(self, session: Session, loc: Location, provider_name: str,
                         mode_preference: str = "auto") -> SyncResult:
        prov, started = self._provider(provider_name), utcnow()
        if self.effective_mode(mode_preference) == "offline":
            return self._log(session, loc, provider_name, "forecast", started, "skipped_offline", 0,
                             "Offline mode: showing cached forecast only.")
        try:
            records = prov.fetch_forecast(loc.latitude, loc.longitude, self.FORECAST_DAYS)
        except ProviderError as exc:
            log.error("forecast refresh failed for %s: %s", loc.name, exc)
            return self._log(session, loc, provider_name, "forecast", started, "error", 0, str(exc))
        try:
            retrieved = utcnow().replace(microsecond=0)
            if records:
                stmt = sqlite_insert(ForecastRainfall).values([
                    dict(location_id=loc.id, provider=provider_name, retrieved_at=retrieved,
                         date=r.date, precip_mm=r.precip_mm) for r in records])
                stmt = stmt.on_conflict_do_update(
                    index_elements=["location_id", "provider", "retrieved_at", "date"],
                    set_={"precip_mm": stmt.excluded.precip_mm})
                session.execute(stmt)
            session.flush()
        except Exception:
            session.rollback()
            raise
        return self._log(session, loc, provider_name, "forecast", started, "ok", len(records), None)

    def refresh_history(self, session: Session, loc: Location, provider_name: str, start: date,
                        end: date, mode_preference: str = "auto") -> SyncResult:
        prov, started = self._provider(provider_name), utcnow()
        kind = prov.info.history_kind
        if kind is None:
            return self._log(session, loc, provider_name, "history", started, "error", 0,
                             "Provider has no history capability.")
        if self.effective_mode(mode_preference) == "offline":
            return self._log(session, loc, provider_name, "history", started, "skipped_offline", 0,
                             "Offline mode: history not refreshed.")
        try:
            records = prov.fetch_history(loc.latitude, loc.longitude, start, end)
        except ProviderError as exc:
            log.error("history refresh failed for %s: %s", loc.name, exc)
            return self._log(session, loc, provider_name, "history", started, "error", 0, str(exc))
        try:
            fetched = utcnow()
            if records:
                stmt = sqlite_insert(DailyRainfall).values([
                    dict(location_id=loc.id, date=r.date, kind=kind, provider=provider_name,
                         precip_mm=r.precip_mm, fetched_at=fetched) for r in records])
                stmt = stmt.on_conflict_do_update(
                    index_elements=["location_id", "date", "kind", "provider"],
                    set_={"precip_mm": stmt.excluded.precip_mm, "fetched_at": stmt.excluded.fetched_at})
                session.execute(stmt)
            session.flush()
        except Exception:
            session.rollback()
            raise
        return self._log(session, loc, provider_name, "history", started, "ok", len(records), None)

    # -- reads ---------------------------------------------------------------------
    def latest_forecast(self, session: Session, location_id: int,
                        provider_name: str | None = None) -> ForecastSnapshot | None:
        q = select(ForecastRainfall.provider, func.max(ForecastRainfall.retrieved_at)).where(
            ForecastRainfall.location_id == location_id)
        if provider_name:
            q = q.where(ForecastRainfall.provider == provider_name)
        row = session.execute(q.group_by(ForecastRainfall.provider)
                              .order_by(func.max(ForecastRainfall.retrieved_at).desc())).first()
        if row is None:
            return None
        provider, retrieved = row
        rows = session.execute(select(ForecastRainfall.date, ForecastRainfall.precip_mm).where(
            ForecastRainfall.location_id == location_id, ForecastRainfall.provider == provider,
            ForecastRainfall.retrieved_at == retrieved).order_by(ForecastRainfall.date)).all()
        age = (utcnow() - retrieved).total_seconds() / 3600
        return ForecastSnapshot(provider, retrieved, age, age > self.settings.forecast_stale_hours,
                                [(d, v) for d, v in rows])

    def history_series(self, session: Session, location_id: int, start: date, end: date) -> pd.Series:
        """Daily series; where both kinds exist for a day, observations win over reanalysis."""
        rows = session.execute(select(DailyRainfall).where(
            DailyRainfall.location_id == location_id, DailyRainfall.date >= start,
            DailyRainfall.date <= end)).scalars().all()
        priority = {"observation": 0, "reanalysis": 1}
        best: dict[date, DailyRainfall] = {}
        for r in rows:
            if r.precip_mm is None:
                continue
            cur = best.get(r.date)
            if cur is None or priority.get(r.kind, 9) < priority.get(cur.kind, 9):
                best[r.date] = r
        if not best:
            return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
        return pd.Series({pd.Timestamp(d): r.precip_mm for d, r in best.items()}, dtype=float).sort_index()
