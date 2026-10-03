"""Tests for onset detection vs prediction separation, forecast contract,
spatial ML status, and updated health endpoint."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import DailyRainfall, ForecastRainfall, Location
from app.services.weather_service import utcnow
from tests.conftest import FakeProvider, rec


@pytest.fixture
def make_client(settings):
    def _make(provider, online=True):
        app = create_app(settings, {"fake": provider}, connectivity=lambda host: online)
        with app.state.session_factory() as s:
            existing = s.query(Location).filter_by(name="Testville", level="district",
                                                    state="Maharashtra").first()
            if not existing:
                s.add(Location(name="Testville", level="district", state="Maharashtra",
                               district="Testville", latitude=18.5, longitude=73.8,
                               coordinate_note="test"))
                s.commit()
        return TestClient(app)
    return _make


# ---- Onset detection vs prediction separation ----------------------------------------

class TestOnsetSeparation:
    def test_onset_endpoint_returns_observed_onset_detection_type(self, make_client):
        c = make_client(FakeProvider())
        with c.app.state.session_factory() as s:
            d0 = date(2021, 6, 1)
            now = utcnow()
            for i in range(80):
                v = {10: 10.0, 11: 8.0, 12: 7.0}.get(i, 3.0 if i > 12 and i % 3 == 0 else 0.5)
                s.add(DailyRainfall(location_id=1, date=d0 + timedelta(days=i), kind="reanalysis",
                                    provider="fake", precip_mm=v, fetched_at=now))
            s.commit()
        r = c.get("/api/locations/1/monsoon/onset?year=2021")
        assert r.status_code == 200
        b = r.json()
        assert b["type"] == "observed_onset_detection"
        assert b["analysis_kind"] == "retrospective"
        assert b["observed_onset"] is not None
        # Backward compat: onset_date still present
        assert b["onset_date"] == b["observed_onset"]
        assert "retrospective" in b["note"].lower()

    def test_onset_prediction_endpoint_returns_not_implemented(self, make_client):
        c = make_client(FakeProvider())
        r = c.get("/api/locations/1/monsoon/onset-prediction")
        assert r.status_code == 200
        b = r.json()
        assert b["type"] == "onset_prediction"
        assert b["prediction_status"] == "not_implemented"
        assert b["predicted_onset"] is None
        assert b["confidence"] is None
        assert "not yet implemented" in b["note"].lower()
        assert isinstance(b["requirements"], list)

    def test_onset_prediction_unknown_location_404(self, make_client):
        c = make_client(FakeProvider())
        r = c.get("/api/locations/999/monsoon/onset-prediction")
        assert r.status_code == 404

    def test_onset_detection_and_prediction_are_distinct_endpoints(self, make_client):
        """The two endpoints must be different and not confused."""
        c = make_client(FakeProvider())
        detection = c.get("/api/locations/1/monsoon/onset?year=2021")
        prediction = c.get("/api/locations/1/monsoon/onset-prediction")
        assert detection.json()["type"] != prediction.json()["type"]


# ---- Forecast contract ---------------------------------------------------------------

class TestForecastContract:
    def test_forecast_status_no_data(self, make_client):
        c = make_client(FakeProvider())
        r = c.get("/api/locations/1/forecast/status")
        assert r.status_code == 200
        b = r.json()
        assert b["forecast_available"] is False
        assert b["prediction_integration"]["integrated"] is False
        assert b["n_forecast_days"] == 0

    def test_forecast_status_with_data(self, make_client):
        c = make_client(FakeProvider(forecast=[rec("2026-07-01", 3.0), rec("2026-07-02", 5.0)]))
        assert c.post("/api/locations/1/forecast/refresh", json={"provider": "fake"}).status_code == 200
        r = c.get("/api/locations/1/forecast/status")
        assert r.status_code == 200
        b = r.json()
        assert b["forecast_available"] is True
        assert b["n_forecast_days"] == 2
        assert b["prediction_integration"]["integrated"] is False
        assert b["provider_info"]["name"] == "fake"
        assert b["offline_usable"] is True

    def test_forecast_status_unknown_location_404(self, make_client):
        c = make_client(FakeProvider())
        r = c.get("/api/locations/999/forecast/status")
        assert r.status_code == 404

    def test_forecast_not_integrated_in_predictions(self, make_client):
        """Forecast data exists but model does not use it."""
        c = make_client(FakeProvider(forecast=[rec("2026-07-01", 3.0)]))
        c.post("/api/locations/1/forecast/refresh", json={"provider": "fake"})
        status = c.get("/api/locations/1/forecast/status").json()
        assert status["prediction_integration"]["integrated"] is False
        assert "historical rainfall" in status["prediction_integration"]["reason"].lower()


# ---- Spatial ML status ---------------------------------------------------------------

class TestSpatialStatus:
    def test_spatial_status_reports_not_aware(self, make_client):
        c = make_client(FakeProvider())
        r = c.get("/api/model/spatial-status")
        assert r.status_code == 200
        b = r.json()
        assert b["is_spatially_aware"] is False
        assert b["spatial_features_in_model"] is False
        assert b["location_treatment"] == "pooled_identical"
        assert isinstance(b["candidate_approaches"], list)
        assert len(b["candidate_approaches"]) > 0
        assert all(a["status"] == "not_implemented" for a in b["candidate_approaches"])

    def test_spatial_status_lists_correct_features(self, make_client):
        c = make_client(FakeProvider())
        b = c.get("/api/model/spatial-status").json()
        expected = ["r1", "sum3", "sum7", "sum14", "sum30", "rainy_frac14", "dry_run", "doy_sin", "doy_cos"]
        assert b["current_features"] == expected
        assert b["n_features"] == 9


# ---- Health endpoint enhancements ---------------------------------------------------

class TestHealthEnhancements:
    def test_health_reports_geographic_scope(self, make_client):
        c = make_client(FakeProvider())
        b = c.get("/api/health").json()
        assert "geographic_scope" in b
        assert b["geographic_scope"]["current"] == "district_hq_coordinate_points"
        assert b["geographic_scope"]["target"] == "block_village_target_coordinates"

    def test_health_reports_spatial_awareness(self, make_client):
        c = make_client(FakeProvider())
        b = c.get("/api/health").json()
        assert b["spatial_awareness"] is False

    def test_health_reports_actual_operating_state(self, make_client):
        # Online mode with internet
        c_online = make_client(FakeProvider(), online=True)
        b = c_online.get("/api/health").json()
        assert b["actual_operating_state"] == "online"

        # Offline mode
        c_offline = make_client(FakeProvider(), online=False)
        b = c_offline.get("/api/health").json()
        assert b["actual_operating_state"] == "offline"

    def test_health_version_updated(self, make_client):
        c = make_client(FakeProvider())
        b = c.get("/api/health").json()
        assert b["version"] == "0.2.0"


# ---- Data quality endpoint -----------------------------------------------------------

class TestDataQualityEndpoint:
    def test_data_quality_no_data(self, make_client):
        c = make_client(FakeProvider())
        r = c.get("/api/locations/1/data-quality")
        assert r.status_code == 200
        b = r.json()
        assert b["status"] == "no_data"
        assert b["total_records"] == 0

    def test_data_quality_with_data(self, make_client):
        c = make_client(FakeProvider())
        with c.app.state.session_factory() as s:
            now = utcnow()
            for i in range(30):
                d = date.today() - timedelta(days=29 - i)
                s.add(DailyRainfall(location_id=1, date=d, kind="reanalysis",
                                    provider="fake", precip_mm=5.0, fetched_at=now))
            s.commit()
        r = c.get("/api/locations/1/data-quality")
        assert r.status_code == 200
        b = r.json()
        assert b["status"] in ("valid", "incomplete")
        assert b["total_records"] == 30

    def test_data_quality_unknown_location_404(self, make_client):
        c = make_client(FakeProvider())
        r = c.get("/api/locations/999/data-quality")
        assert r.status_code == 404

    def test_coverage_endpoint(self, make_client):
        c = make_client(FakeProvider())
        r = c.get("/api/data-quality/coverage")
        assert r.status_code == 200
        b = r.json()
        assert "n_locations" in b
        assert "locations" in b
