from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.models import Base, Location  # noqa: E402
from app.providers.base import DailyRecord, ProviderError, ProviderInfo, WeatherProvider  # noqa: E402


class FakeProvider(WeatherProvider):
    """Test double. Test data only - never used by the running application."""
    info = ProviderInfo("fake", "test double", "reanalysis", True, 16, "n/a", False, "test only")

    def __init__(self, forecast=None, history=None, error: str | None = None):
        self.forecast, self.history, self.error = forecast or [], history or [], error
        self.calls = 0

    def fetch_forecast(self, lat, lon, days):
        self.calls += 1
        if self.error:
            raise ProviderError(self.error)
        return list(self.forecast)

    def fetch_history(self, lat, lon, start, end):
        self.calls += 1
        if self.error:
            raise ProviderError(self.error)
        return [r for r in self.history if start <= r.date <= end]


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models", forecast_stale_hours=12)


@pytest.fixture
def session_factory(settings):
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture
def location(session):
    loc = Location(name="Testville", level="district", state="Maharashtra", district="Testville",
                   latitude=18.5, longitude=73.8, coordinate_note="test")
    session.add(loc)
    session.commit()
    return loc


def rec(d: str, v):
    return DailyRecord(date.fromisoformat(d), v)
