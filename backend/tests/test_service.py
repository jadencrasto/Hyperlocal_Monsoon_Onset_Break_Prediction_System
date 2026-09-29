from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import DailyRainfall, ForecastRainfall, SyncLog
from app.services.weather_service import WeatherService, utcnow
from tests.conftest import FakeProvider, rec


def make(session_factory, settings, provider, online=True):
    return WeatherService(session_factory, {"fake": provider}, settings, connectivity=lambda host: online)


def test_forecast_refresh_stores_rows_and_logs_ok(session, session_factory, settings, location):
    prov = FakeProvider(forecast=[rec("2026-07-01", 1.0), rec("2026-07-02", None)])
    res = make(session_factory, settings, prov).refresh_forecast(session, location, "fake")
    assert res.status == "ok" and res.n_records == 2
    assert session.scalar(select(func.count()).select_from(ForecastRainfall)) == 2
    assert session.scalar(select(SyncLog.status)) == "ok"


def test_provider_failure_logs_error_and_stores_nothing(session, session_factory, settings, location):
    prov = FakeProvider(error="boom")
    res = make(session_factory, settings, prov).refresh_forecast(session, location, "fake")
    assert res.status == "error" and "boom" in res.message
    assert session.scalar(select(func.count()).select_from(ForecastRainfall)) == 0  # no synthetic fallback


def test_offline_mode_never_calls_provider(session, session_factory, settings, location):
    prov = FakeProvider(forecast=[rec("2026-07-01", 1.0)])
    svc = make(session_factory, settings, prov, online=True)
    res = svc.refresh_forecast(session, location, "fake", mode_preference="offline")
    assert res.status == "skipped_offline" and prov.calls == 0


def test_auto_mode_follows_connectivity(session_factory, settings):
    assert make(session_factory, settings, FakeProvider(), online=False).effective_mode("auto") == "offline"
    assert make(session_factory, settings, FakeProvider(), online=True).effective_mode("auto") == "online"


def test_latest_forecast_freshness_and_staleness(session, session_factory, settings, location):
    svc = make(session_factory, settings, FakeProvider())
    session.add_all([ForecastRainfall(location_id=location.id, provider="fake",
                                      retrieved_at=utcnow() - timedelta(hours=30), date=date(2026, 7, 1), precip_mm=2.0)])
    session.commit()
    snap = svc.latest_forecast(session, location.id)
    assert snap.stale is True and snap.age_hours > 29
    session.add(ForecastRainfall(location_id=location.id, provider="fake", retrieved_at=utcnow(),
                                 date=date(2026, 7, 1), precip_mm=5.0))
    session.commit()
    snap = svc.latest_forecast(session, location.id)
    assert snap.stale is False and snap.records == [(date(2026, 7, 1), 5.0)]


def test_history_refresh_is_idempotent_and_updates(session, session_factory, settings, location):
    prov = FakeProvider(history=[rec("2020-06-01", 1.0), rec("2020-06-02", 2.0)])
    svc = make(session_factory, settings, prov)
    svc.refresh_history(session, location, "fake", date(2020, 6, 1), date(2020, 6, 2))
    prov.history = [rec("2020-06-01", 9.0), rec("2020-06-02", 2.0)]
    svc.refresh_history(session, location, "fake", date(2020, 6, 1), date(2020, 6, 2))
    assert session.scalar(select(func.count()).select_from(DailyRainfall)) == 2
    s = svc.history_series(session, location.id, date(2020, 6, 1), date(2020, 6, 2))
    assert s.iloc[0] == 9.0


def test_observation_preferred_over_reanalysis(session, session_factory, settings, location):
    now = utcnow()
    session.add_all([
        DailyRainfall(location_id=location.id, date=date(2020, 6, 1), kind="reanalysis", provider="a", precip_mm=1.0, fetched_at=now),
        DailyRainfall(location_id=location.id, date=date(2020, 6, 1), kind="observation", provider="b", precip_mm=7.0, fetched_at=now)])
    session.commit()
    s = make(session_factory, settings, FakeProvider()).history_series(session, location.id, date(2020, 6, 1), date(2020, 6, 1))
    assert s.iloc[0] == 7.0


def test_unknown_provider_raises(session, session_factory, settings, location):
    with pytest.raises(ValueError):
        make(session_factory, settings, FakeProvider()).refresh_forecast(session, location, "nope")


# -- Phase 1: same-second refresh collision ------------------------------------------
def test_same_second_repeat_refresh_does_not_conflict(session, session_factory, settings, location, monkeypatch):
    monkeypatch.setattr("app.services.weather_service.utcnow",
                        lambda: datetime(2026, 7, 1, 12, 0, 0, 123456))
    prov = FakeProvider(forecast=[rec("2026-07-01", 1.0), rec("2026-07-02", 2.0)])
    svc = make(session_factory, settings, prov)
    first = svc.refresh_forecast(session, location, "fake")
    second = svc.refresh_forecast(session, location, "fake")  # same truncated second
    assert first.status == "ok" and second.status == "ok"
    assert second.n_records == 2
    assert session.scalar(select(func.count()).select_from(ForecastRainfall)) == 2  # no duplicates
    logs = session.scalars(select(SyncLog).where(SyncLog.kind == "forecast")
                           .order_by(SyncLog.id)).all()
    assert [l.status for l in logs] == ["ok", "ok"]  # one successful sync log per refresh


def test_same_second_refresh_updates_to_latest_values(session, session_factory, settings, location, monkeypatch):
    monkeypatch.setattr("app.services.weather_service.utcnow",
                        lambda: datetime(2026, 7, 1, 12, 0, 0, 123456))
    prov = FakeProvider(forecast=[rec("2026-07-01", 1.0), rec("2026-07-02", 2.0)])
    svc = make(session_factory, settings, prov)
    svc.refresh_forecast(session, location, "fake")
    prov.forecast = [rec("2026-07-01", 9.0), rec("2026-07-02", 8.0)]
    svc.refresh_forecast(session, location, "fake")  # same second, newer values
    assert session.scalar(select(func.count()).select_from(ForecastRainfall)) == 2
    snap = svc.latest_forecast(session, location.id)
    assert snap.records == [(date(2026, 7, 1), 9.0), (date(2026, 7, 2), 8.0)]  # newest wins


def test_distinct_seconds_retain_distinct_batches(session, session_factory, settings, location, monkeypatch):
    clock = {"now": datetime(2026, 7, 1, 12, 0, 0)}
    monkeypatch.setattr("app.services.weather_service.utcnow", lambda: clock["now"])
    prov = FakeProvider(forecast=[rec("2026-07-01", 1.0)])
    svc = make(session_factory, settings, prov)
    svc.refresh_forecast(session, location, "fake")
    clock["now"] = datetime(2026, 7, 1, 12, 0, 5)  # a later retrieval second
    prov.forecast = [rec("2026-07-01", 5.0), rec("2026-07-02", 2.0)]
    svc.refresh_forecast(session, location, "fake")
    assert session.scalar(select(func.count()).select_from(ForecastRainfall)) == 3  # both batches kept
    snap = svc.latest_forecast(session, location.id)
    assert snap.records == [(date(2026, 7, 1), 5.0), (date(2026, 7, 2), 2.0)]  # newest batch selected


# -- Phase 1: connectivity covers both hosts ----------------------------------------
def test_auto_mode_online_only_when_both_hosts_reachable(session_factory, settings):
    def svc(forecast_ok: bool, archive_ok: bool) -> WeatherService:
        reach = {settings.connectivity_host: forecast_ok,
                 settings.connectivity_archive_host: archive_ok}
        return WeatherService(session_factory, {"fake": FakeProvider()}, settings,
                              connectivity=lambda host: reach[host])
    assert svc(True, True).effective_mode("auto") == "online"
    assert svc(True, False).effective_mode("auto") == "offline"  # archive down
    assert svc(False, True).effective_mode("auto") == "offline"  # forecast down
    assert svc(False, False).effective_mode("auto") == "offline"


def test_connectivity_result_is_cached(session_factory, settings):
    calls: list[str] = []

    def conn(host: str) -> bool:
        calls.append(host)
        return True

    svc = WeatherService(session_factory, {"fake": FakeProvider()}, settings, connectivity=conn)
    assert svc.is_online() is True
    assert calls == [settings.connectivity_host, settings.connectivity_archive_host]
    assert svc.is_online() is True
    assert svc.effective_mode("auto") == "online"
    assert len(calls) == 2  # repeated checks inside the 15s window make no new calls


# -- Phase 2: history sync log -------------------------------------------------------
def test_history_refresh_writes_ok_sync_log(session, session_factory, settings, location):
    prov = FakeProvider(history=[rec("2020-06-01", 1.0), rec("2020-06-02", 2.0)])
    res = make(session_factory, settings, prov).refresh_history(
        session, location, "fake", date(2020, 6, 1), date(2020, 6, 2))
    assert res.status == "ok"
    log = session.scalar(select(SyncLog).where(SyncLog.kind == "history"))
    assert log is not None and log.status == "ok"
