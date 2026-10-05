"""Step 13: tests for the demo break-risk prediction endpoint.

A tiny real sklearn logistic-regression artifact is dumped into the test models_dir so the
tests exercise the actual inference path (StandardScaler + LogisticRegression) end to end.
"""
import json
from datetime import date, timedelta

import joblib
import numpy as np
import pytest
from sqlalchemy import select

from app.ml.features import FEATURES
from app.ml.train import ARTIFACT, REPORT
from app.models import DailyRainfall, Location
from app.services.weather_service import utcnow
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .conftest import FakeProvider, rec


@pytest.fixture
def make_client(settings):
    """App client on the tmp database. Locations are seeded via the conftest `location`
    fixture (same tmp DB), not here - inserting twice would hit the Location unique key."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    def _make(provider, online=True):
        app = create_app(settings, {"fake": provider}, connectivity=lambda host: online)
        return TestClient(app)
    return _make


def _install_model(settings, with_report=True):
    """Dump a tiny real sklearn model in place; no real artifact is touched (tmp_path)."""
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    X = rng.random((200, len(FEATURES)))
    model = make_pipeline(StandardScaler(), LogisticRegression()).fit(
        X, (X[:, 0] > 0.5).astype(int))
    joblib.dump({"model": model, "features": FEATURES, "target_cfg": {"horizon_days": 7, "dry_len": 5,
                "dry_mm": 2.5, "first_md": [6, 15], "season_end_md": [9, 30]},
                "model_name": "test_logistic", "trained_at_utc": "2026-09-29T00:00:00+00:00"},
                settings.models_dir / ARTIFACT)
    if with_report:
        (settings.models_dir / REPORT).write_text(json.dumps({
            "created_at_utc": "2026-09-29T00:00:00+00:00",
            "intended_use": "test fixture report",
            "data_provenance": {"kind": "test", "location_selection": {"mode": "all_locations",
                                  "selected_location_ids": [1, 2, 3, 4, 5]}},
            "dataset": {"n_rows": 13130, "n_years": 26, "n_locations": 5,
                        "location_ids": [1, 2, 3, 4, 5], "first_date": "2000-06-15",
                        "last_date": "2025-09-23"},
            "split_years": {"test": [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]},
            "selected_model": "logistic_regression", "model_class": "Pipeline",
            "test": {"brier_skill_vs_climatology": 0.067,
                     "brier_skill_ci": {"low": 0.041, "high": 0.096},
                     "baseline_dry_run_conditioned": {"brier": 0.114},
                     "model": {"brier": 0.118}},
            "caveats": ["c1", "c2"]}))
    return model


def _seed_history(session, location, end: date, days: int = 60):
    """Two month-long blocks: wet (>= 2.5mm) then bone dry, so dry_run is high at `end`."""
    rows = []
    for i in range(days):
        d = end - timedelta(days=days - 1 - i)
        v = 10.0 if i < 30 else 0.0
        rows.append(DailyRainfall(location_id=location.id, date=d, kind="reanalysis",
                                  provider="open_meteo", precip_mm=v, fetched_at=utcnow()))
    session.add_all(rows)
    session.commit()


def test_prediction_success_shape_and_provenance(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20))
    c = make_client(FakeProvider())
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 200, r.text
    b = r.json()
    # required schema
    for key in ("type", "location", "prediction_date", "probability", "risk_category",
                "horizon_days", "model", "data_status", "limitations"):
        assert key in b, key
    assert b["model"]["trained_on_locations"] == [1, 2, 3, 4, 5]
    assert b["type"] == "break_risk_prediction"
    assert b["location"]["id"] == location.id and b["location"]["name"] == "Testville"
    assert b["prediction_date"] == "2026-09-20"
    assert 0.0 <= b["probability"] <= 1.0
    assert b["risk_category"] in ("low", "moderate", "high")
    assert b["model"]["name"] == "test_logistic"
    assert b["model"]["trained_on_locations"] == [1, 2, 3, 4, 5]
    assert b["model"]["test_skill"]["brier_skill_vs_climatology"] == 0.067
    assert b["model"]["test_skill"]["brier_skill_ci"] == {"low": 0.041, "high": 0.096}
    assert b["model"]["baselines"]["dry_run_baseline_brier"] == 0.114
    assert b["model"]["baselines"]["model_brier"] == 0.118
    assert b["model"]["trained_through"] == "2025-09-23"
    assert b["model"]["intended_use"] == "test fixture report"
    assert b["data_status"]["source"] == "stored_reanalysis_history"
    assert b["data_status"]["latest_rainfall_date"] == "2026-09-20"
    expected_age = (date.today() - date(2026, 9, 20)).days
    assert b["data_status"]["data_age_days"] == expected_age
    assert b["data_status"]["freshness"] == ("current" if expected_age <= 2 else
                                              "recent" if expected_age <= 7 else "stale")
    assert b["data_status"]["input_days_used"] == 60
    assert b["data_status"]["input_completeness"] == 1.0
    assert isinstance(b["limitations"], list) and b["limitations"]


def test_prediction_future_date_rejected(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20))
    c = make_client(FakeProvider())
    future = (date.today() + timedelta(days=3)).isoformat()
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk?as_of={future}")
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "future_date"


def test_prediction_not_in_monsoon_season_422(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 1, 10))
    c = make_client(FakeProvider())
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 422
    assert "monsoon season" in r.json()["detail"]["hint"]


def test_prediction_without_model_503(make_client, session, location):
    _seed_history(session, location, date(2026, 9, 20))
    c = make_client(FakeProvider())
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "model_unavailable"


def test_prediction_without_history_404(make_client, session, location, settings):
    _install_model(settings)
    c = make_client(FakeProvider())
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "no_stored_history"


def test_prediction_gappy_recent_history_422(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20))
    # remove one interior day inside the trailing 30-day feature window, then ask for a date
    # after the gap - the endpoint must refuse rather than extrapolate across it
    rows = session.scalars(select(DailyRainfall).where(
        DailyRainfall.location_id == location.id)).all()
    session.delete(rows[-15])
    session.commit()
    c = make_client(FakeProvider())
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk?as_of=2026-09-15")
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "insufficient_or_gappy_history"


def test_prediction_unknown_location_404(make_client, settings):
    _install_model(settings)
    c = make_client(FakeProvider())
    assert c.get("/api/locations/999/prediction/break-risk").status_code == 404


def test_prediction_stale_history_flagged_not_blocked(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20))
    c = make_client(FakeProvider())
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk?as_of=2026-09-20")
    assert r.status_code == 200
    # nothing else needed here; freshness semantics covered in the success test


def test_risk_category_boundaries():
    from app.api.routes import _risk_category
    assert _risk_category(0.0) == "low" and _risk_category(0.19) == "low"
    assert _risk_category(0.2) == "moderate" and _risk_category(0.399) == "moderate"
    assert _risk_category(0.4) == "high" and _risk_category(1.0) == "high"


# ---- Step 14: schema stability + uncertainty metadata -------------------------------


def test_response_schema_versioned_and_stable(make_client, session, location, settings):
    """The contract Steps 16-18 will build on: exact top-level keys, versioned, and
    prediction fields unchanged by the uncertainty additions."""
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20))
    c = make_client(FakeProvider())
    b = c.get(f"/api/locations/{location.id}/prediction/break-risk").json()
    assert set(b) == {"type", "schema_version", "location", "prediction_date", "probability",
                      "risk_category", "risk_bands", "horizon_days", "event", "basis",
                      "model", "uncertainty", "data_status", "limitations",
                      "last_sync_failure"}  # Step 25: null unless a recent refresh failed
    assert b["schema_version"] == "1.0" and b["type"] == "break_risk_prediction"
    assert isinstance(b["probability"], float) and 0.0 <= b["probability"] <= 1.0
    assert b["risk_bands"]["note"]  # bands carry the not-calibrated caveat inline
    assert set(b["model"]) == {"name", "class", "trained_on_locations", "trained_period",
                               "trained_through", "test_skill", "baselines", "intended_use", "caveats"}
    assert b["model"]["trained_period"] == {"first_date": "2000-06-15", "last_date": "2025-09-23",
                                             "n_years": 26}


def test_uncertainty_block_honest_and_populated(make_client, session, location, settings):
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20))
    c = make_client(FakeProvider())
    u = c.get(f"/api/locations/{location.id}/prediction/break-risk").json()["uncertainty"]
    assert set(u) == {"individual_prediction_interval", "evaluation_skill", "calibration",
                      "per_year_stability", "evidence_level", "data_caveats"}
    # no invented per-prediction interval: explicit null with a reason
    assert u["individual_prediction_interval"] == {
        "available": False,
        "reason": "The current pipeline fits a single point-probability model; no quantile, "
                  "ensemble or conformal method was trained, so no statistically justified "
                  "per-prediction interval exists. null means 'not provided', not zero."}
    assert u["evaluation_skill"]["brier_skill_vs_climatology"] == 0.067
    assert u["evaluation_skill"]["brier_skill_ci"] == {"low": 0.041, "high": 0.096}
    assert "NOT an interval around this prediction" in u["evaluation_skill"]["ci_interpretation"]
    assert u["evaluation_skill"]["n_test_years"] is None       # fixture CI lacks n_years
    interp = u["calibration"]["interpretation"]              # fixture has no calibration block
    assert interp is None or "over-predict" in interp or "under-predict" in interp
    assert u["per_year_stability"] == {"n_years": None, "bss_min": None, "bss_max": None,
                                       "negative_years": 0, "note": None}
    assert u["evidence_level"] == "modest_positive_skill_vs_climatology_only"
    assert u["data_caveats"]["note"]


def test_evidence_level_logic():
    from app.api.routes import _evidence_level
    both = {"brier_skill_vs_climatology": 0.1, "brier_skill_ci": {"low": 0.02},
            "model": {"brier": 0.10}, "baseline_dry_run_conditioned": {"brier": 0.12}}
    clim_only = {"brier_skill_vs_climatology": 0.1, "brier_skill_ci": {"low": 0.02},
                 "model": {"brier": 0.12}, "baseline_dry_run_conditioned": {"brier": 0.11}}
    no_skill = {"brier_skill_vs_climatology": 0.1, "brier_skill_ci": {"low": -0.01},
                "model": {"brier": 0.12}, "baseline_dry_run_conditioned": {"brier": 0.11}}
    none = {}
    assert _evidence_level(both) == "positive_skill_vs_climatology_and_heuristic"
    assert _evidence_level(clim_only) == "modest_positive_skill_vs_climatology_only"
    assert _evidence_level(no_skill) == "no_skill_demonstrated"
    assert _evidence_level(none) == "no_evaluation_available"


def test_calibration_interpretation_signs():
    from app.api.routes import _uncertainty_block
    mk = lambda d: _uncertainty_block({"calibration": d}, {}, 3)
    assert "over-predicts" in mk({"mean_diff": 0.061})["calibration"]["interpretation"]
    assert "under-predicts" in mk({"mean_diff": -0.028})["calibration"]["interpretation"]
    assert mk({})["calibration"]["interpretation"] is None
    assert mk({"mean_diff": 0.061})["calibration"]["mean_diff"] == 0.061


# ---- Historical Demo Mode & Leakage Validation (SIH26086) --------------------------
def test_demo_mode_current_date_in_october_without_as_of_out_of_season(make_client, session, location, settings):
    """Test 1: When latest stored date is in October, calling without as_of rejects as out_of_season."""
    _install_model(settings)
    _seed_history(session, location, date(2026, 10, 5), days=60)
    c = make_client(FakeProvider())
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "out_of_season"


def test_demo_mode_historical_in_season_date_succeeds(make_client, session, location, settings):
    """Test 2: Explicit historical in-season as_of date succeeds and returns historical_demo mode."""
    _install_model(settings)
    _seed_history(session, location, date(2026, 10, 5), days=60)
    c = make_client(FakeProvider())
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk?as_of=2026-09-25")
    assert r.status_code == 200
    b = r.json()
    assert b["as_of"] == "2026-09-25"
    assert b["prediction_date"] == "2026-09-25"
    assert b["evaluation_mode"] == "historical_demo"
    assert "demo/retrospective" in b["evaluation_mode_note"]
    assert isinstance(b["probability"], float)
    assert 0.0 <= b["probability"] <= 1.0
    assert b["risk_category"] in ("low", "moderate", "high")


def test_demo_mode_historical_out_of_season_date_rejected(make_client, session, location, settings):
    """Test 3: Explicit historical date outside monsoon season is rejected."""
    _install_model(settings)
    _seed_history(session, location, date(2026, 10, 5), days=60)
    c = make_client(FakeProvider())
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk?as_of=2026-10-05")
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "out_of_season"


def test_demo_mode_future_date_rejected(make_client, session, location, settings):
    """Test 4: Explicit future as_of date is rejected."""
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20), days=60)
    c = make_client(FakeProvider())
    future = (date.today() + timedelta(days=10)).isoformat()
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk?as_of={future}")
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "future_date"


def test_demo_mode_invalid_date_rejected(make_client, session, location, settings):
    """Test 5: Malformed as_of date string is rejected with 422 validation error."""
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20), days=60)
    c = make_client(FakeProvider())
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk?as_of=not-a-date")
    assert r.status_code == 422


def test_demo_mode_data_leakage_protection(make_client, session, location, settings):
    """Test 6: Observations after as_of date MUST NOT affect the prediction (zero data leakage)."""
    _install_model(settings)
    ref_date = date(2026, 9, 20)
    _seed_history(session, location, ref_date, days=60)
    c = make_client(FakeProvider())

    # 1. Baseline prediction at ref_date
    r1 = c.get(f"/api/locations/{location.id}/prediction/break-risk?as_of={ref_date.isoformat()}")
    assert r1.status_code == 200
    prob_before = r1.json()["probability"]

    # 2. Add future rainfall after ref_date (massive 100mm deluge on subsequent days)
    for d in range(1, 5):
        fut_date = ref_date + timedelta(days=d)
        session.add(DailyRainfall(
            location_id=location.id, date=fut_date, precip_mm=100.0,
            kind="observation", provider="gauge", fetched_at=utcnow()
        ))
    session.commit()

    # 3. Repeat prediction at ref_date with future data present in database
    r2 = c.get(f"/api/locations/{location.id}/prediction/break-risk?as_of={ref_date.isoformat()}")
    assert r2.status_code == 200
    prob_after = r2.json()["probability"]

    # Zero leakage: probabilities must be strictly identical
    assert prob_before == prob_after


def test_demo_mode_standard_request_preserves_behavior(make_client, session, location, settings):
    """Test 7: Standard request without as_of retains stable schema and standard mode."""
    _install_model(settings)
    _seed_history(session, location, date(2026, 9, 20), days=60)
    c = make_client(FakeProvider())
    r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
    assert r.status_code == 200
    b = r.json()
    assert "evaluation_mode" not in b
    assert b["prediction_date"] == "2026-09-20"
