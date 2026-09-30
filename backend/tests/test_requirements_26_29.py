"""Tests for project requirements 26-29:
26. Local caching of recent observations/forecasts
27. Offline prediction using cached/local data
28. Automatic Online -> Offline fallback
29. Data freshness/status indicators and error states
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.models import DailyRainfall
from app.providers.base import CATEGORY_NETWORK, CATEGORY_TIMEOUT, DailyRecord, ProviderError
from app.services.weather_service import utcnow
from tests.conftest import FakeProvider, rec
from tests.test_prediction_api import _install_model, _seed_history


@pytest.fixture
def make_client(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    def _make(provider, online=True, mode_pref="auto"):
        app = create_app(settings, {"fake": provider}, connectivity=lambda host: online)
        app.state.mode_pref = mode_pref
        return TestClient(app)
    return _make


# 1. Live API succeeds -> live data is used -------------------------------------------
def test_live_api_succeeds_uses_live_data(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20), days=60)
    # Provider has a new observation for consecutive day 2026-09-21
    new_record = DailyRecord(date(2026, 9, 21), 5.5)
    prov = FakeProvider(history=[new_record])
    c = make_client(prov, online=True)

    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 200, r.text
    b = r.json()
    ds = b["data_status"]

    assert ds["cache_status"] == "live"
    assert ds["is_live"] is True
    assert ds["data_source"] == "live"
    assert ds["latest_rainfall_date"] == "2026-09-21"
    assert b["prediction_date"] == "2026-09-21"
    assert b["last_sync_failure"] is None


# 2. Live API succeeds -> cache is updated --------------------------------------------
def test_live_api_succeeds_updates_cache(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20), days=60)
    new_record = DailyRecord(date(2026, 9, 23), 12.0)
    prov = FakeProvider(history=[new_record])
    c = make_client(prov, online=True)

    c.get(f"/api/locations/{location.id}/prediction/break-risk")
    session.expire_all()

    # Verify SQLite row was added
    row = session.execute(
        select(DailyRainfall).where(
            DailyRainfall.location_id == location.id,
            DailyRainfall.date == date(2026, 9, 23)
        )
    ).scalar_one_or_none()
    assert row is not None
    assert row.precip_mm == 12.0
    assert row.provider == "fake"
    assert row.fetched_at is not None


# 3. Live API fails -> valid cache is used ---------------------------------------------
def test_live_api_fails_uses_valid_cache(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20), days=60)
    # Provider fails with timeout
    prov = FakeProvider(error="Open-Meteo connection timed out")
    c = make_client(prov, online=True)

    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 200, r.text
    b = r.json()
    ds = b["data_status"]

    assert ds["cache_status"] == "cached"
    assert ds["is_live"] is False
    assert ds["data_source"] == "cache"
    assert ds["latest_rainfall_date"] == "2026-09-20"
    assert b["prediction_date"] == "2026-09-20"
    assert 0.0 <= b["probability"] <= 1.0
    # Fallback failure signal is present
    assert b["last_sync_failure"] is not None
    assert "timed out" in b["last_sync_failure"]["message"]


# 4. Live API fails -> stale/invalid cache is rejected --------------------------------
def test_live_api_fails_too_old_cache_rejected(make_client, session, location, settings):
    _install_model(settings)
    # Seed data ending 45 days ago (older than max_cache_age_days = 30)
    old_date = date.today() - timedelta(days=45)
    _seed_history(session, location, old_date, days=60)
    prov = FakeProvider(error="upstream failure")
    c = make_client(prov, online=True)

    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 422
    err = r.json()["detail"]
    assert err["error"] == "cached_data_too_old"
    assert "too old" in err["hint"]


def test_live_api_fails_gappy_cache_rejected(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20), days=60)
    # Create gap in recent history
    rows = session.scalars(select(DailyRainfall).where(DailyRainfall.location_id == location.id)).all()
    session.delete(rows[-5])
    session.commit()

    prov = FakeProvider(error="upstream failure")
    c = make_client(prov, online=True)

    r = c.get(f"/api/locations/{location.id}/prediction/break-risk?as_of=2026-09-20")
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "insufficient_or_gappy_history"


# 5. No live data + no cache -> prediction unavailable --------------------------------
def test_no_live_data_and_no_cache_returns_404(make_client, settings, location):
    _install_model(settings)
    # Empty database, provider fails
    prov = FakeProvider(error="network failure")
    c = make_client(prov, online=True)

    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "no_stored_history"


# 6. API recovers -> online data is used again ----------------------------------------
def test_api_recovers_resumes_online_data(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20), days=60)

    # 1. Failing provider
    bad_prov = FakeProvider(error="temporary server error")
    c_bad = make_client(bad_prov, online=True)
    r1 = c_bad.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r1.status_code == 200
    assert r1.json()["data_status"]["cache_status"] == "cached"
    assert r1.json()["last_sync_failure"] is not None

    # Clear cooldown on the service cache manager to simulate time passing / recovery
    # 2. Recovered provider with fresh data
    fresh_rec = DailyRecord(date(2026, 9, 21), 8.0)
    good_prov = FakeProvider(history=[fresh_rec])
    c_good = make_client(good_prov, online=True)
    c_good.app.state.service.cache_manager.clear_failure(location.id, "fake")

    r2 = c_good.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["data_status"]["cache_status"] == "live"
    assert b2["data_status"]["is_live"] is True
    assert b2["data_status"]["latest_rainfall_date"] == "2026-09-21"
    assert b2["last_sync_failure"] is None


# 7. Do not repeatedly hammer failed API (Cooldown) -----------------------------------
def test_failure_cooldown_prevents_hammering_failed_api(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20), days=60)
    prov = FakeProvider(error="repeated error")
    c = make_client(prov, online=True)

    # First call: attempts provider, records failure
    c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert prov.calls == 1

    # Second immediate call: should NOT call provider again (in cooldown)
    c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert prov.calls == 1  # calls did not increment!


# 8. Cache TTL avoids unnecessary repeated API calls -----------------------------------
def test_cache_ttl_avoids_repeated_calls(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20), days=60)
    new_rec = DailyRecord(date(2026, 9, 21), 3.0)
    prov = FakeProvider(history=[new_rec])
    c = make_client(prov, online=True)

    # First call fetches live data
    r1 = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r1.status_code == 200
    assert prov.calls == 1

    # Second call within TTL window
    r2 = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r2.status_code == 200
    assert prov.calls == 1  # Still 1, cache was fresh!


# 9. Offline mode explicitly skips provider --------------------------------------------
def test_offline_mode_skips_provider_calls(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20), days=60)
    prov = FakeProvider(history=[DailyRecord(date(2026, 9, 25), 1.0)])
    c = make_client(prov, online=False, mode_pref="offline")

    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 200
    assert prov.calls == 0
    assert r.json()["data_status"]["cache_status"] == "offline"
