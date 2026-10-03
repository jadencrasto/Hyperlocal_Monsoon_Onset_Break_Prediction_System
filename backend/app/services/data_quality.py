"""Data quality validation for weather observations and forecasts.

Checks for missing dates, duplicate dates, impossible rainfall values,
date continuity, location coverage, and training period coverage.
Does NOT silently repair data — flags issues for callers to handle.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..models import DailyRainfall, ForecastRainfall, Location

log = logging.getLogger(__name__)

# Valid status values for data quality assessments
DataStatus = Literal["valid", "incomplete", "stale", "insufficient_data", "no_data"]

# Physical bounds for daily precipitation (mm)
MAX_REASONABLE_PRECIP_MM = 1000.0  # world record ~1825 mm; 1000 is a generous bound


@dataclass
class DataQualityReport:
    """Comprehensive data quality assessment for a location's rainfall data."""
    location_id: int
    status: DataStatus
    issues: list[str] = field(default_factory=list)
    total_records: int = 0
    first_date: date | None = None
    last_date: date | None = None
    expected_days: int = 0
    actual_days: int = 0
    missing_days: int = 0
    duplicate_count: int = 0
    null_precip_count: int = 0
    impossible_values: int = 0
    continuity_ratio: float | None = None
    providers: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)


def validate_location_data(session: Session, location_id: int,
                           min_days: int = 30,
                           max_age_days: int = 30) -> DataQualityReport:
    """Run all data quality checks for a location's rainfall history.

    Returns a DataQualityReport with status:
      - valid: data passes all checks
      - incomplete: data exists but has gaps or missing values
      - stale: most recent data is older than max_age_days
      - insufficient_data: fewer than min_days of records
      - no_data: no records at all
    """
    report = DataQualityReport(location_id=location_id, status="no_data")

    # Basic counts
    report.total_records = session.scalar(
        select(func.count()).select_from(DailyRainfall)
        .where(DailyRainfall.location_id == location_id)
    ) or 0

    if report.total_records == 0:
        report.status = "no_data"
        report.issues.append("No rainfall records exist for this location.")
        return report

    # Date range
    row = session.execute(
        select(func.min(DailyRainfall.date), func.max(DailyRainfall.date))
        .where(DailyRainfall.location_id == location_id)
    ).one()
    report.first_date, report.last_date = row[0], row[1]

    # Distinct dates (actual days with data)
    report.actual_days = session.scalar(
        select(func.count(func.distinct(DailyRainfall.date)))
        .where(DailyRainfall.location_id == location_id)
    ) or 0

    # Expected days in the range
    if report.first_date and report.last_date:
        report.expected_days = (report.last_date - report.first_date).days + 1
        report.missing_days = report.expected_days - report.actual_days
        report.continuity_ratio = (
            report.actual_days / report.expected_days
            if report.expected_days > 0 else None
        )

    # Duplicate date+kind+provider combos (should be 0 due to unique constraint, but check)
    dup_q = (
        select(DailyRainfall.date, DailyRainfall.kind, DailyRainfall.provider,
               func.count().label("cnt"))
        .where(DailyRainfall.location_id == location_id)
        .group_by(DailyRainfall.date, DailyRainfall.kind, DailyRainfall.provider)
        .having(func.count() > 1)
    )
    report.duplicate_count = len(session.execute(dup_q).all())

    # Null precipitation values
    report.null_precip_count = session.scalar(
        select(func.count()).select_from(DailyRainfall)
        .where(DailyRainfall.location_id == location_id,
               DailyRainfall.precip_mm.is_(None))
    ) or 0

    # Impossible values (negative or unreasonably large)
    report.impossible_values = session.scalar(
        select(func.count()).select_from(DailyRainfall)
        .where(DailyRainfall.location_id == location_id,
               DailyRainfall.precip_mm.isnot(None),
               ((DailyRainfall.precip_mm < 0) |
                (DailyRainfall.precip_mm > MAX_REASONABLE_PRECIP_MM)))
    ) or 0

    # Providers and kinds present
    report.providers = sorted(
        session.scalars(
            select(func.distinct(DailyRainfall.provider))
            .where(DailyRainfall.location_id == location_id)
        ).all()
    )
    report.kinds = sorted(
        session.scalars(
            select(func.distinct(DailyRainfall.kind))
            .where(DailyRainfall.location_id == location_id)
        ).all()
    )

    # Build issues list and determine status
    issues = []

    if report.impossible_values > 0:
        issues.append(f"{report.impossible_values} records have impossible rainfall values "
                      f"(negative or > {MAX_REASONABLE_PRECIP_MM} mm).")

    if report.duplicate_count > 0:
        issues.append(f"{report.duplicate_count} duplicate date/kind/provider combinations found.")

    if report.null_precip_count > 0:
        issues.append(f"{report.null_precip_count} records have null precipitation values.")

    if report.missing_days > 0:
        issues.append(f"{report.missing_days} days missing in the date range "
                      f"({report.first_date} to {report.last_date}).")

    # Determine status
    if report.actual_days < min_days:
        report.status = "insufficient_data"
        issues.append(f"Only {report.actual_days} days of data; minimum required is {min_days}.")
    elif report.last_date and (date.today() - report.last_date).days > max_age_days:
        report.status = "stale"
        age = (date.today() - report.last_date).days
        issues.append(f"Most recent data is {age} days old (max allowed: {max_age_days}).")
    elif report.missing_days > 0 or report.null_precip_count > 0 or report.impossible_values > 0:
        report.status = "incomplete"
    else:
        report.status = "valid"

    report.issues = issues
    return report


def validate_forecast_freshness(session: Session, location_id: int,
                                 stale_hours: float = 12.0) -> dict:
    """Check forecast data freshness for a location.

    Returns a dict with status, age, and whether forecast data exists.
    """
    from ..services.weather_service import utcnow
    row = session.execute(
        select(ForecastRainfall.provider, func.max(ForecastRainfall.retrieved_at))
        .where(ForecastRainfall.location_id == location_id)
        .group_by(ForecastRainfall.provider)
        .order_by(func.max(ForecastRainfall.retrieved_at).desc())
    ).first()

    if row is None:
        return {"status": "no_data", "age_hours": None, "stale": None,
                "provider": None, "message": "No forecast data cached for this location."}

    provider, retrieved_at = row
    age_hours = (utcnow() - retrieved_at).total_seconds() / 3600
    stale = age_hours > stale_hours

    status = "stale" if stale else "valid"
    return {"status": status, "age_hours": round(age_hours, 2), "stale": stale,
            "provider": provider, "stale_after_hours": stale_hours}


def coverage_summary(session: Session) -> dict:
    """Summary of data coverage across all locations."""
    locations = session.scalars(
        select(Location).where(Location.level == "district")
    ).all()

    loc_reports = []
    for loc in locations:
        row = session.execute(
            select(func.count(), func.min(DailyRainfall.date), func.max(DailyRainfall.date))
            .where(DailyRainfall.location_id == loc.id)
        ).one()
        n_records, first_date, last_date = row
        loc_reports.append({
            "location_id": loc.id,
            "name": loc.name,
            "n_records": int(n_records or 0),
            "first_date": first_date.isoformat() if first_date else None,
            "last_date": last_date.isoformat() if last_date else None,
            "has_data": (n_records or 0) > 0,
        })

    return {
        "n_locations": len(locations),
        "locations_with_data": sum(1 for r in loc_reports if r["has_data"]),
        "locations": loc_reports,
    }
