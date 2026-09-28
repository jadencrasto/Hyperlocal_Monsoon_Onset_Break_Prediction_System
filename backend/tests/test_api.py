from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import DailyRainfall, Location
from app.services.weather_service import utcnow
from tests.conftest import FakeProvider, rec


@pytest.fixture
def make_client(settings):
    def _make(provider, online=True):
        app = create_app(settings, {"fake": provider}, connectivity=lambda host: online)
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
    assert c.get("/api/sources").json()["providers"][0]["last_error"]["message"] == "upstream down"


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
    assert o["status"] == "detected" and o["onset_date"] == "2021-06-11" and o["type"] == "historical_analysis"
    ds = c.get("/api/locations/1/monsoon/dry-spells?year=2021").json()
    assert all(sp["scope"] == "local_dry_spell" for sp in ds["spells"])
    assert c.get("/api/locations/1/monsoon/break-risk").status_code == 503   # no model trained
    assert c.get("/api/model/evaluation").status_code == 404
