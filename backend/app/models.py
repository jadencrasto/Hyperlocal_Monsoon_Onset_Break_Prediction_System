from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# All datetimes are stored as naive UTC.


class Base(DeclarativeBase):
    pass


class Location(Base):
    """Administrative unit: 'state' | 'district' | 'block' | 'panchayat'.

    Districts carry coordinates (pilot analysis points). Higher-level grouping nodes (state,
    and later block/panchayat when authoritative data is added) have parent_id set instead;
    they have no coordinates and exist for hierarchy/navigation only."""
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    level: Mapped[str] = mapped_column(String(20))  # state | district | block | panchayat
    state: Mapped[str] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(80), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    coordinate_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("name", "level", "state", "district"),
                      UniqueConstraint("parent_id", "name", "level"),)


class DailyRainfall(Base):
    """Historical daily rainfall. `kind` is 'observation' (gauge/gridded obs) or 'reanalysis' (e.g. ERA5)."""
    __tablename__ = "daily_rainfall"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(40))
    precip_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("location_id", "date", "kind", "provider"),)


class ForecastRainfall(Base):
    """Third-party forecasts. Every retrieval is kept (keyed by retrieved_at) so forecasts can be
    evaluated later against what actually happened. `retrieved_at` is when WE fetched it; the
    providers used here do not report the model-run time in the response."""
    __tablename__ = "forecast_rainfall"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime)
    date: Mapped[date] = mapped_column(Date)
    precip_mm: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (UniqueConstraint("location_id", "provider", "retrieved_at", "date"),)


class SyncLog(Base):
    __tablename__ = "sync_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(16))  # forecast | history
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(24))  # ok | error | skipped_offline
    n_records: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
