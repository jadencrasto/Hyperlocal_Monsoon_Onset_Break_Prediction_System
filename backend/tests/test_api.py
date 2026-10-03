from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import DailyRainfall, Location
from app.services.weather_service import utcnow
from tests.conftest import FakeProvider, rec


@pytest.fixture
def make_client(settings):
    def _make(provider, online=True, connectivity=None):
        conn = connectivity or (lambda host: online)
        app = create_app(settings, {"fake": provider}, connectivity=conn)
        with app.state.session_factory() as s:
            s.add(Location(name="Testville", level="district", state="Maharashtra", district="Testville",
                           latitude=18.5, longitude=73.8, coordinate_note="test"))
            s.commit()
        return TestClient(app)
    return _make


def test_health_and_locations(make_client):
    c = make_client(FakeProvider())
    h = c.get("/api/health").json()
    assert h["status"] == "ok" and h["effective_mode"] == "online" and h["model_available"] is False
    assert h["actual_operating_state"] == "online"
    assert c.get("/api/locations").json()[0]["name"] == "Testville"
    assert c.get("/api/locations/999").status_code == 404


def test_mode_switching_and_offline_refresh_is_409(make_client):
    c = make_client(FakeProvider(forecast=[rec("2026-07-01", 1.0)]))
    assert c.put("/api/mode", json={"preference": "offline"}).json()["effective"] == "offline"
    r = c.post("/api/locations/1/forecast/refresh", json={"provider": "fake"})
    assert r.status_code == 409 and r.json()["detail"]["status"] == "skipped_offline"
    assert c.put("/api/mode", json={"preference": "bogus"}).status_code == 422


def test_provider_failure_is_502_and_no_forecast_exists(make_client):
    c = make_client(FakeProvider(error="upstream down"))
    r = c.post("/api/locations/1/forecast/refresh", json={"provider": "fake"})
    assert r.status_code == 502 and "upstream down" in r.json()["detail"]["message"]
    assert c.get("/api/locations/1/forecast").status_code == 404
    last_err = c.get("/api/sources").json()["providers"][0]["last_error"]
    assert last_err["message"] == "upstream down"   # category tag stripped in the API output
    assert last_err["category"] == "http_failure"   # FakeProvider errors default to http_failure


def test_forecast_roundtrip_is_labelled(make_client):
    c = make_client(FakeProvider(forecast=[rec("2026-07-01", 3.0)]))
    assert c.post("/api/locations/1/forecast/refresh", json={"provider": "fake"}).status_code == 200
    f = c.get("/api/locations/1/forecast").json()
    assert f["type"] == "third_party_forecast" and f["freshness"] == "fresh" and f["records"][0]["precip_mm"] == 3.0


def test_validation_errors(make_client):
    c = make_client(FakeProvider())
    bad = c.post("/api/locations/1/history/refresh", json={"provider": "fake", "start": "2020-02-01", "end": "2020-01-01"})
    assert bad.status_code == 422
    assert c.post("/api/locations/1/forecast/refresh", json={"provider": "nope"}).status_code == 422
    assert c.get("/api/locations/1/monsoon/onset?year=1800").status_code == 422


def test_onset_from_stored_history_and_break_risk_without_model(make_client, settings):
    c = make_client(FakeProvider())
    with c.app.state.session_factory() as s:
        d0, now = date(2021, 6, 1), utcnow()
        for i in range(0, 80):
            v = {10: 10.0, 11: 8.0, 12: 7.0}.get(i, 3.0 if i > 12 and i % 3 == 0 else 0.5)
            s.add(DailyRainfall(location_id=1, date=d0 + timedelta(days=i), kind="reanalysis", provider="fake",
                                precip_mm=v, fetched_at=now))
        s.commit()
    o = c.get("/api/locations/1/monsoon/onset?year=2021").json()
    assert o["status"] == "detected" and o["onset_date"] == "2021-06-11" and o["type"] == "observed_onset_detection"
    ds = c.get("/api/locations/1/monsoon/dry-spells?year=2021").json()
    assert all(sp["scope"] == "local_dry_spell" for sp in ds["spells"])
    assert c.get("/api/locations/1/monsoon/break-risk").status_code == 503   # no model trained
    assert c.get("/api/model/evaluation").status_code == 404


# -- Phase 1: same-second refresh collision ------------------------------------------
def test_rapid_double_refresh_returns_200_for_both(make_client, monkeypatch):
    monkeypatch.setattr("app.services.weather_service.utcnow",
                        lambda: datetime(2026, 7, 1, 12, 0, 0, 500000))
    c = make_client(FakeProvider(forecast=[rec("2026-07-01", 3.0)]))
    payload = {"provider": "fake"}
    r1 = c.post("/api/locations/1/forecast/refresh", json=payload)
    r2 = c.post("/api/locations/1/forecast/refresh", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200  # no same-second 500
    f = c.get("/api/locations/1/forecast").json()
    assert len(f["records"]) == 1 and f["records"][0]["precip_mm"] == 3.0  # one clean batch
    logs = c.get("/api/sync-log").json()
    assert [e["status"] for e in logs if e["kind"] == "forecast"] == ["ok", "ok"]


# -- Phase 1: connectivity covers both hosts ----------------------------------------
def _archive_unreachable(settings):
    return lambda host: host != settings.connectivity_archive_host


def test_mode_offline_when_archive_host_unreachable(make_client, settings):
    c = make_client(FakeProvider(forecast=[rec("2026-07-01", 1.0)]),
                    connectivity=_archive_unreachable(settings))
    m = c.get("/api/mode").json()
    assert m["effective"] == "offline" and m["internet_reachable"] is False
    r = c.post("/api/locations/1/forecast/refresh", json={"provider": "fake"})
    assert r.status_code == 409 and r.json()["detail"]["status"] == "skipped_offline"


def test_explicit_online_bypasses_connectivity(make_client, settings):
    c = make_client(FakeProvider(forecast=[rec("2026-07-01", 1.0)]),
                    connectivity=_archive_unreachable(settings))
    assert c.put("/api/mode", json={"preference": "online"}).json()["effective"] == "online"
    r = c.post("/api/locations/1/forecast/refresh", json={"provider": "fake"})
    assert r.status_code == 200 and r.json()["status"] == "ok"


# -- Phase 2: future-date validation ------------------------------------------------
def test_history_refresh_with_future_end_date_is_422(make_client):
    prov = FakeProvider(history=[rec("2026-09-01", 1.0)])
    c = make_client(prov)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    r = c.post("/api/locations/1/history/refresh",
               json={"provider": "fake", "start": "2026-09-01", "end": tomorrow})
    assert r.status_code == 422
    assert prov.calls == 0  # schema rejects before any provider call
