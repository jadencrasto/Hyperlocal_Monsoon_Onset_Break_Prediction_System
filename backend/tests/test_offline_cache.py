"""Step 23: offline/cache architecture — cache provenance, non-destructive refresh, and
prediction consistency. Reuses the Step 13 fixture model + conftest FakeProvider; no real
artifact or network is touched."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.models import DailyRainfall, ForecastRainfall, SyncLog
from app.services.weather_service import utcnow
from tests.conftest import FakeProvider, rec

from .test_prediction_api import _install_model, _seed_history


@pytest.fixture
def make_client(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    def _make(provider, online=True, mode_pref="auto"):
        app = create_app(settings, {"fake": provider}, connectivity=lambda host: online)
        app.state.mode_pref = mode_pref
        return TestClient(app)
    return _make


def _seeded(client, location, session):
    """Seed 60 days of rainfall and return the prediction body."""
    _seed_history(session, location, date(2026, 9, 20))
    r = client.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 200, r.text
    return r.json()


# 1. valid local cached data remains usable ----------------------------------------
def test_local_cached_data_remains_usable_online(make_client, session, location, settings):
    _install_model(settings)
    c = make_client(FakeProvider(), online=True)
    b = _seeded(c, location, session)
    ds = b["data_status"]
    assert ds["cache_status"] == "cached"          # online: same local store, not "live"
    assert ds["provider"] == "open_meteo"          # provenance of the newest stored row
    assert ds["input_days_used"] == 60 and ds["input_completeness"] == 1.0


def test_local_cached_data_remains_usable_offline(make_client, session, location, settings):
    _install_model(settings)
    c = make_client(FakeProvider(), online=False)
    b = _seeded(c, location, session)
    assert b["data_status"]["cache_status"] == "offline"
    assert 0.0 <= b["probability"] <= 1.0          # prediction still produced from local data


# 2. failed external refresh does not destroy existing local data -------------------
def test_failed_history_refresh_preserves_local_data(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20))
    c = make_client(FakeProvider(), online=True)
    base = c.get(f"/api/locations/{location.id}/prediction/break-risk").json()
    before = session.scalar(select(func.count()).select_from(DailyRainfall))
    latest_before = session.scalar(
        select(func.max(DailyRainfall.date)).where(DailyRainfall.location_id == location.id))
    bad = make_client(FakeProvider(error="upstream timeout"), online=True)
    r = bad.post(f"/api/locations/{location.id}/history/refresh",
                 json={"provider": "fake", "start": "2026-08-01", "end": "2026-08-31"})
    assert r.status_code == 502
    # local rows survive untouched
    after = session.scalar(select(func.count()).select_from(DailyRainfall))
    latest_after = session.scalar(
        select(func.max(DailyRainfall.date)).where(DailyRainfall.location_id == location.id))
    assert after == before and latest_after == latest_before
    # and the prediction is unchanged
    b = c.get(f"/api/locations/{location.id}/prediction/break-risk").json()
    assert b["probability"] == base["probability"]


def test_failed_forecast_refresh_preserves_cached_forecast(make_client, session, location, settings):
    c = make_client(FakeProvider(forecast=[rec("2026-07-01", 2.0)]), online=True)
    assert c.post(f"/api/locations/{location.id}/forecast/refresh",
                  json={"provider": "fake"}).status_code == 200
    prov = FakeProvider(error="upstream down")
    c2 = make_client.__wrapped__(c) if False else c  # clarity: same client
    # switch the app's provider for a failing refresh by re-creating the client on the same DB
    app_client = make_client(prov, online=True)
    r = app_client.post(f"/api/locations/{location.id}/forecast/refresh", json={"provider": "fake"})
    assert r.status_code == 502
    f = app_client.get(f"/api/locations/{location.id}/forecast").json()  # cached batch still served
    assert f["records"] and f["records"][0]["precip_mm"] == 2.0


# 3. cache/freshness metadata is correctly reported ---------------------------------
def test_cache_metadata_reported(make_client, session, location, settings):
    _install_model(settings)
    c = make_client(FakeProvider(), online=False, mode_pref="offline")
    b = _seeded(c, location, session)
    ds = b["data_status"]
    assert set(ds) >= {"source", "provider", "latest_rainfall_date", "data_age_days",
                       "freshness", "input_days_used", "input_completeness", "cache_status"}
    assert ds["freshness"] == ("current" if ds["data_age_days"] <= 2 else
                               "recent" if ds["data_age_days"] <= 7 else "stale")
    assert ds["cache_status"] == "offline"


# 4. unavailable/incomplete local data produces an appropriate failure --------------
def test_no_local_history_fails_cleanly_offline(make_client, session, location, settings):
    _install_model(settings)
    c = make_client(FakeProvider(), online=False)
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "no_stored_history"


def test_gappy_local_history_fails_cleanly_offline(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20))
    rows = session.scalars(select(DailyRainfall).where(DailyRainfall.location_id == location.id)).all()
    session.delete(rows[-15])
    session.commit()
    c = make_client(FakeProvider(), online=False)
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk?as_of=2026-09-15")
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "insufficient_or_gappy_history"


# 5. offline mode does not change prediction probability ----------------------------
@pytest.mark.parametrize("mode_pref,online", [("auto", True), ("auto", False),
                                              ("offline", False), ("offline", True),
                                              ("online", True)])
def test_probability_identical_across_modes(make_client, session, location, settings,
                                            mode_pref, online):
    """The same local input must yield the same probability in every mode. The baseline is
    computed in auto/online mode on the shared tmp DB, then compared per mode/client."""
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20))
    base = make_client(FakeProvider(), online=True, mode_pref="auto") \
        .get(f"/api/locations/{location.id}/prediction/break-risk").json()
    c = make_client(FakeProvider(), online=online, mode_pref=mode_pref)
    b = c.get(f"/api/locations/{location.id}/prediction/break-risk").json()
    assert b["probability"] == base["probability"]
    # mode is visible in cache_status but never affects the math
    expected_cache = "offline" if mode_pref == "offline" or (mode_pref == "auto" and not online) \
        else "cached"
    assert b["data_status"]["cache_status"] == expected_cache


# 6. successful refresh preserves provenance ----------------------------------------
def test_successful_refresh_preserves_provenance_and_data(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20))  # covers ~Jul 22..Sep 20 (open_meteo)
    c = make_client(FakeProvider(history=[rec("2026-06-10", 1.5), rec("2026-06-11", 0.0)]),
                    online=True)
    r = c.post(f"/api/locations/{location.id}/history/refresh",
               json={"provider": "fake", "start": "2026-06-10", "end": "2026-06-11"})
    assert r.status_code == 200 and r.json()["status"] == "ok"
    rows = session.execute(select(DailyRainfall).where(
        DailyRainfall.location_id == location.id, DailyRainfall.date == date(2026, 6, 10))).scalars().all()
    assert len(rows) == 1 and rows[0].provider == "fake" and rows[0].precip_mm == 1.5
    assert rows[0].fetched_at is not None
    # original seeded rows (open_meteo) are untouched — provenance is per-row
    om = session.scalar(select(func.count()).select_from(DailyRainfall).where(
        DailyRainfall.location_id == location.id, DailyRainfall.provider == "open_meteo"))
    assert om == 60
    # prediction provenance reports the provider of the NEWEST row (still the seed)
    b = c.get(f"/api/locations/{location.id}/prediction/break-risk").json()
    assert b["data_status"]["provider"] == "open_meteo"
    assert b["data_status"]["latest_rainfall_date"] == "2026-09-20"  # backfill doesn't move it


# 7. malformed/invalid external data is rejected without corrupting local data ------
def test_invalid_external_values_rejected_without_write(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20))
    before = session.scalar(select(func.count()).select_from(DailyRainfall))
    c = make_client(FakeProvider(history=[rec("2026-08-10", -3.0)]), online=True)
    r = c.post(f"/api/locations/{location.id}/history/refresh",
               json={"provider": "fake", "start": "2026-08-10", "end": "2026-08-10"})
    assert r.status_code == 502
    assert "Rejected invalid external data" in r.json()["detail"]["message"]
    assert session.scalar(select(func.count()).select_from(DailyRainfall)) == before
    assert session.scalar(select(func.count()).select_from(DailyRainfall).where(
        DailyRainfall.provider == "fake")) == 0


def test_malformed_history_refresh_does_not_write_partial_batch(make_client, session, location, settings):
    """A valid day followed by an invalid one must not leave a partial write behind."""
    _install_model(settings)
    c = make_client(FakeProvider(history=[rec("2026-08-10", 1.0), rec("2026-08-11", -1.0)]),
                    online=True)
    r = c.post(f"/api/locations/{location.id}/history/refresh",
               json={"provider": "fake", "start": "2026-08-10", "end": "2026-08-11"})
    assert r.status_code == 502
    assert session.scalar(select(func.count()).select_from(DailyRainfall).where(
        DailyRainfall.provider == "fake")) == 0
