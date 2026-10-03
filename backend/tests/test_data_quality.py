"""Tests for data quality validation: missing dates, duplicates, impossible values,
date continuity, staleness, and coverage summary."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import DailyRainfall, ForecastRainfall, Location
from app.services.data_quality import (
    MAX_REASONABLE_PRECIP_MM, coverage_summary, validate_forecast_freshness,
    validate_location_data,
)
from app.services.weather_service import utcnow


def _seed(session, location, days, start=None, precip=5.0, gaps=None, nulls=None, impossible=None):
    """Seed rainfall data with optional gaps (set of day offsets to skip),
    nulls (set of day offsets with null precip), impossible (set of day offsets with bad values)."""
    gaps = gaps or set()
    nulls = nulls or set()
    impossible = impossible or set()
    start = start or (date.today() - timedelta(days=days))
    for i in range(days):
        if i in gaps:
            continue
        d = start + timedelta(days=i)
        v = precip
        if i in nulls:
            v = None
        elif i in impossible:
            v = -5.0
        session.add(DailyRainfall(location_id=location.id, date=d, kind="reanalysis",
                                   provider="fake", precip_mm=v, fetched_at=utcnow()))
    session.commit()


def test_no_data_returns_no_data_status(session, location):
    report = validate_location_data(session, location.id)
    assert report.status == "no_data"
    assert report.total_records == 0
    assert len(report.issues) > 0


def test_valid_data_returns_valid_status(session, location):
    _seed(session, location, 60)
    report = validate_location_data(session, location.id)
    assert report.status == "valid"
    assert report.total_records == 60
    assert report.missing_days == 0
    assert report.impossible_values == 0
    assert report.null_precip_count == 0
    assert report.continuity_ratio == 1.0


def test_insufficient_data_detected(session, location):
    _seed(session, location, 10)
    report = validate_location_data(session, location.id, min_days=30)
    assert report.status == "insufficient_data"
    assert any("minimum required" in issue for issue in report.issues)


def test_stale_data_detected(session, location):
    old_start = date.today() - timedelta(days=100)
    _seed(session, location, 50, start=old_start)
    report = validate_location_data(session, location.id, max_age_days=30)
    assert report.status == "stale"
    assert any("days old" in issue for issue in report.issues)


def test_gaps_detected_as_incomplete(session, location):
    _seed(session, location, 60, gaps={10, 20, 30})
    report = validate_location_data(session, location.id)
    assert report.status == "incomplete"
    assert report.missing_days == 3
    assert any("missing" in issue.lower() for issue in report.issues)


def test_null_precip_detected(session, location):
    _seed(session, location, 60, nulls={5, 15, 25})
    report = validate_location_data(session, location.id)
    assert report.null_precip_count == 3
    assert any("null" in issue.lower() for issue in report.issues)


def test_impossible_values_detected(session, location):
    _seed(session, location, 60, impossible={7})
    report = validate_location_data(session, location.id)
    assert report.impossible_values == 1
    assert any("impossible" in issue.lower() for issue in report.issues)


def test_providers_and_kinds_reported(session, location):
    _seed(session, location, 60)
    report = validate_location_data(session, location.id)
    assert "fake" in report.providers
    assert "reanalysis" in report.kinds


def test_continuity_ratio_correct(session, location):
    # 60 days with 5 gaps = 55 actual / 60 expected
    _seed(session, location, 60, gaps={5, 15, 25, 35, 45})
    report = validate_location_data(session, location.id)
    assert report.continuity_ratio == pytest.approx(55 / 60, rel=0.01)


def test_forecast_freshness_no_data(session, location):
    result = validate_forecast_freshness(session, location.id)
    assert result["status"] == "no_data"
    assert result["age_hours"] is None


def test_forecast_freshness_valid(session, location):
    session.add(ForecastRainfall(
        location_id=location.id, provider="fake",
        retrieved_at=utcnow(), date=date.today(), precip_mm=5.0
    ))
    session.commit()
    result = validate_forecast_freshness(session, location.id, stale_hours=12.0)
    assert result["status"] == "valid"
    assert result["stale"] is False


def test_forecast_freshness_stale(session, location):
    session.add(ForecastRainfall(
        location_id=location.id, provider="fake",
        retrieved_at=utcnow() - timedelta(hours=24), date=date.today(), precip_mm=5.0
    ))
    session.commit()
    result = validate_forecast_freshness(session, location.id, stale_hours=12.0)
    assert result["status"] == "stale"
    assert result["stale"] is True


def test_coverage_summary(session, location):
    _seed(session, location, 30)
    summary = coverage_summary(session)
    assert summary["n_locations"] == 1
    assert summary["locations_with_data"] == 1
    assert summary["locations"][0]["has_data"] is True
