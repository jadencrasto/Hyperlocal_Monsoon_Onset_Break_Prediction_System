from datetime import date, timedelta

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
