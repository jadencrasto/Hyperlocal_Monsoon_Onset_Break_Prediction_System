"""Steps 24-25: online provider integration and failure detection.

Provider adapter behavior (categorized failures), structured refresh failures through the
service, cache preservation after every failure class, freshness states, idempotency, and
the mode matrix. Uses the FakeProvider test seam + fixture model; the live open-meteo HTTP
path is unit-tested in test_open_meteo.py and exercised live by scripts/smoke_step24_25.sh.
"""
from __future__ import annotations

import requests
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import DailyRainfall, ForecastRainfall, SyncLog
from app.providers.base import ProviderError
from app.providers.open_meteo import OpenMeteoProvider
from app.services.weather_service import WeatherService, utcnow
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


# ---- helpers -----------------------------------------------------------------------

def _snapshot(session, location):
    """(n_rows, latest_date, per-row provenance) for cache-preservation assertions."""
    rows = session.scalars(select(DailyRainfall).where(
        DailyRainfall.location_id == location.id).order_by(DailyRainfall.date)).all()
    return (len(rows),
            max((r.date for r in rows), default=None),
            [(r.date, r.kind, r.provider, r.precip_mm) for r in rows])


def _assert_cache_intact(session, location, before):
    assert _snapshot(session, location) == before


# ---- Step 24: successful online integration ----------------------------------------

class TestOnlineIntegration:
    def test_provider_called_and_valid_records_stored(self, session, session_factory, settings, location):
        prov = FakeProvider(history=[rec("2026-08-10", 1.5), rec("2026-08-11", None)])
        svc = WeatherService(session_factory, {"fake": prov}, settings, connectivity=lambda h: True)
        res = svc.refresh_history(session, location, "fake", date(2026, 8, 10), date(2026, 8, 11), "online")
        assert res.status == "ok" and res.n_records == 2 and prov.calls == 1
        rows = session.scalars(select(DailyRainfall).where(DailyRainfall.location_id == location.id)).all()
        assert {(r.date, r.precip_mm, r.provider, r.kind) for r in rows} == {
            (date(2026, 8, 10), 1.5, "fake", "reanalysis"),
            (date(2026, 8, 11), None, "fake", "reanalysis"),
        }

    def test_provenance_preserved_per_row(self, session, session_factory, settings, location):
        now = utcnow()
        session.add(DailyRainfall(location_id=location.id, date=date(2020, 6, 1), kind="reanalysis",
                                  provider="open_meteo", precip_mm=2.0, fetched_at=now))
        session.commit()
        prov = FakeProvider(history=[rec("2020-06-02", 3.0)])
        svc = WeatherService(session_factory, {"fake": prov}, settings, connectivity=lambda h: True)
        svc.refresh_history(session, location, "fake", date(2020, 6, 2), date(2020, 6, 2), "online")
        p1 = session.scalar(select(DailyRainfall).where(DailyRainfall.provider == "open_meteo"))
        p2 = session.scalar(select(DailyRainfall).where(DailyRainfall.provider == "fake"))
        assert p1.provider == "open_meteo" and p2.provider == "fake" and p2.precip_mm == 3.0

    def test_repeated_refresh_is_idempotent(self, session, session_factory, settings, location):
        prov = FakeProvider(history=[rec("2026-08-10", 1.5)])
        svc = WeatherService(session_factory, {"fake": prov}, settings, connectivity=lambda h: True)
        svc.refresh_history(session, location, "fake", date(2026, 8, 10), date(2026, 8, 10), "online")
        prov.history = [rec("2026-08-10", 2.5)]  # same day, corrected value
        res = svc.refresh_history(session, location, "fake", date(2026, 8, 10), date(2026, 8, 10), "online")
        assert res.status == "ok"
        assert session.scalar(select(func.count()).select_from(DailyRainfall)) == 1  # upsert, not insert
        assert session.scalar(select(DailyRainfall)).precip_mm == 2.5                # newest wins

    def test_valid_response_with_nulls_is_accepted(self, session, session_factory, settings, location):
        prov = FakeProvider(history=[rec("2026-08-10", None)])
        svc = WeatherService(session_factory, {"fake": prov}, settings, connectivity=lambda h: True)
        res = svc.refresh_history(session, location, "fake", date(2026, 8, 10), date(2026, 8, 10), "online")
        assert res.status == "ok"  # None = missing measurement, stored as NULL, not fabricated


# ---- Step 25: failure detection categories -----------------------------------------

class TestFailureCategories:
    @pytest.mark.parametrize("exc,expected", [
        (ProviderError("conn dropped", "network_failure"), "network_failure"),
        (ProviderError("timed out", "timeout"), "timeout"),
        (ProviderError("HTTP 503", "http_failure"), "http_failure"),
        (ProviderError("missing 'daily'", "malformed_response"), "malformed_response"),
        (ProviderError("negative value", "invalid_data"), "invalid_data"),
        (ProviderError("legacy error"), "http_failure"),  # bare ProviderError default
    ])
    def test_provider_failure_category_reaches_sync_result(self, session, session_factory, settings, location, exc, expected):
        prov = FakeProvider(error="x")
        # inject the exact exception through a stubbed fetch
        prov.fetch_history = lambda *a, **k: (_ for _ in ()).throw(exc)
        svc = WeatherService(session_factory, {"fake": prov}, settings, connectivity=lambda h: True)
        res = svc.refresh_history(session, location, "fake", date(2026, 8, 1), date(2026, 8, 2), "online")
        assert res.status == "error" and res.category == expected
        assert res.message and exc.args[0] in res.message

    def test_structured_502_carries_category(self, make_client, session, location):
        prov = FakeProvider(error="upstream down")
        prov.fetch_history = lambda *a, **k: (_ for _ in ()).throw(
            ProviderError("Open-Meteo timed out", "timeout"))
        c = make_client(prov, online=True)
        r = c.post(f"/api/locations/{location.id}/history/refresh",
                   json={"provider": "fake", "start": "2026-08-01", "end": "2026-08-02"})
        assert r.status_code == 502
        d = r.json()["detail"]
        assert d["error"] == "provider_failure" and d["category"] == "timeout"
        assert d["message"] == "Open-Meteo timed out"

    def test_unknown_provider_is_422_with_hint(self, make_client, location):
        c = make_client(FakeProvider(), online=True)
        r = c.post(f"/api/locations/{location.id}/history/refresh",
                   json={"provider": "nope", "start": "2026-08-01", "end": "2026-08-02"})
        assert r.status_code == 422
        assert "Available" in str(r.json()["detail"])

    def test_offline_mode_makes_no_provider_request(self, session, session_factory, settings, location):
        prov = FakeProvider(history=[rec("2026-08-10", 1.0)])
        svc = WeatherService(session_factory, {"fake": prov}, settings, connectivity=lambda h: True)
        res = svc.refresh_history(session, location, "fake", date(2026, 8, 10), date(2026, 8, 10), "offline")
        assert res.status == "skipped_offline" and prov.calls == 0

    def test_sync_log_rows_expose_category(self, session, session_factory, settings, location):
        prov = FakeProvider(error="x")
        prov.fetch_history = lambda *a, **k: (_ for _ in ()).throw(
            ProviderError("HTTP 503", "http_failure"))
        svc = WeatherService(session_factory, {"fake": prov}, settings, connectivity=lambda h: True)
        svc.refresh_history(session, location, "fake", date(2026, 8, 1), date(2026, 8, 2), "online")
        row = session.scalars(select(SyncLog).order_by(SyncLog.id.desc())).first()
        assert row.status == "error" and "[category: http_failure]" in row.message


# ---- Step 25: cache preservation after every failure class --------------------------

class TestCachePreservation:
    @pytest.mark.parametrize("category", ["network_failure", "timeout", "http_failure",
                                          "malformed_response", "invalid_data"])
    def test_failed_refresh_leaves_cache_and_prediction_untouched(
            self, make_client, session, location, settings, category):
        _install_model(settings)
        _seed_history(session, location, date(2026, 9, 20))
        good = make_client(FakeProvider(), online=True)
        base = good.get(f"/api/locations/{location.id}/prediction/break-risk").json()
        before = _snapshot(session, location)

        bad = FakeProvider(error="boom")
        bad.fetch_history = lambda *a, **k: (_ for _ in ()).throw(
            ProviderError(f"failure of class {category}", category))
        c = make_client(bad, online=True)
        r = c.post(f"/api/locations/{location.id}/history/refresh",
                   json={"provider": "fake", "start": "2026-08-01", "end": "2026-08-31"})
        assert r.status_code == 502 and r.json()["detail"]["category"] == category

        _assert_cache_intact(session, location, before)  # rows, latest date, provenance
        after = c.get(f"/api/locations/{location.id}/prediction/break-risk").json()
        assert after["probability"] == base["probability"]  # same inputs -> same prediction

    def test_negative_precip_batch_rejected_with_no_partial_write(
            self, session, session_factory, settings, location):
        prov = FakeProvider(history=[rec("2026-08-10", 1.0), rec("2026-08-11", -2.0)])
        svc = WeatherService(session_factory, {"fake": prov}, settings, connectivity=lambda h: True)
        res = svc.refresh_history(session, location, "fake", date(2026, 8, 10), date(2026, 8, 11), "online")
        assert res.status == "error" and res.category == "invalid_data"
        assert session.scalar(select(func.count()).select_from(DailyRainfall)) == 0  # no partial batch


# ---- Step 24/25: open-meteo adapter classification (mocked HTTP) --------------------

class Resp:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code, self._body, self._bad = status, body, bad_json
    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._body


class Sess:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def om(sess):
    return OpenMeteoProvider("http://f", "http://a", 5, 2, session=sess, sleep=lambda s: None)


class TestOpenMeteoCategories:
    def test_timeout_category(self):
        with pytest.raises(ProviderError) as ei:
            om(Sess(requests.Timeout("t"), requests.Timeout("t"), requests.Timeout("t"))).fetch_history(
                1, 1, date(2026, 7, 1), date(2026, 7, 2))
        assert ei.value.category == "timeout"

    def test_network_category(self):
        with pytest.raises(ProviderError) as ei:
            om(Sess(requests.ConnectionError("c"), requests.ConnectionError("c"),
                    requests.ConnectionError("c"))).fetch_history(
                1, 1, date(2026, 7, 1), date(2026, 7, 2))
        assert ei.value.category == "network_failure"

    def test_http_category_on_5xx_exhaustion(self):
        with pytest.raises(ProviderError) as ei:
            om(Sess(Resp(503), Resp(503), Resp(503))).fetch_history(
                1, 1, date(2026, 7, 1), date(2026, 7, 2))
        assert ei.value.category == "http_failure"

    def test_malformed_and_invalid_categories(self):
        with pytest.raises(ProviderError) as ei:
            om(Sess(Resp(200, {}))).fetch_history(1, 1, date(2026, 7, 1), date(2026, 7, 2))
        assert ei.value.category == "malformed_response"
        with pytest.raises(ProviderError) as ei:
            om(Sess(Resp(200, {"daily": {"time": ["2026-07-01"], "precipitation_sum": [-1]}}))
               ).fetch_history(1, 1, date(2026, 7, 1), date(2026, 7, 2))
        assert ei.value.category == "invalid_data"

    def test_success_after_retry(self):
        good = {"daily": {"time": ["2026-07-01"], "precipitation_sum": [1.5]}}
        out = om(Sess(Resp(503), Resp(200, good))).fetch_history(1, 1, date(2026, 7, 1), date(2026, 7, 1))
        assert [(r.date, r.precip_mm) for r in out] == [(date(2026, 7, 1), 1.5)]


# ---- Step 25: freshness states ------------------------------------------------------

class TestFreshnessStates:
    def _predict(self, make_client, session, location, settings, end):
        _install_model(settings)
        _seed_history(session, location, end)
        return make_client(FakeProvider(), online=True) \
            .get(f"/api/locations/{location.id}/prediction/break-risk").json()

    def test_current_recent_stale_thresholds(self, make_client, session, location, settings, monkeypatch):
        from app.api.routes import _uncertainty_block
        assert _uncertainty_block({}, {}, 0)["data_caveats"]["freshness"] == "current"
        assert _uncertainty_block({}, {}, 2)["data_caveats"]["freshness"] == "current"
        assert _uncertainty_block({}, {}, 3)["data_caveats"]["freshness"] == "recent"
        assert _uncertainty_block({}, {}, 7)["data_caveats"]["freshness"] == "recent"
        assert _uncertainty_block({}, {}, 8)["data_caveats"]["freshness"] == "stale"

    def test_unavailable_state(self, make_client, session, location, settings):
        _install_model(settings)
        c = make_client(FakeProvider(), online=True)
        r = c.get(f"/api/locations/{location.id}/prediction/break-risk")
        assert r.status_code == 404 and r.json()["detail"]["error"] == "no_stored_history"

    def test_data_status_exposes_full_provenance(self, make_client, session, location, settings):
        _install_model(settings)
        _seed_history(session, location, date(2026, 9, 20))
        c = make_client(FakeProvider(), online=True)
        ds = c.get(f"/api/locations/{location.id}/prediction/break-risk").json()["data_status"]
        for key in ("source", "provider", "latest_rainfall_date", "data_age_days",
                    "freshness", "input_days_used", "input_completeness", "cache_status"):
            assert key in ds, key


# ---- modes (regression) --------------------------------------------------------------

class TestModes:
    @pytest.mark.parametrize("mode_pref,online,expected_cache", [
        ("auto", True, "cached"), ("auto", False, "offline"),
        ("offline", True, "offline"), ("offline", False, "offline"),
        ("online", True, "cached"), ("online", False, "cached"),  # explicit online attempts anyway
    ])
    def test_mode_matrix_cache_status_and_probability(self, make_client, session, location, settings,
                                                      mode_pref, online, expected_cache):
        _install_model(settings)
        _seed_history(session, location, date(2026, 9, 20))
        base = make_client(FakeProvider(), online=True, mode_pref="auto") \
            .get(f"/api/locations/{location.id}/prediction/break-risk").json()
        c = make_client(FakeProvider(), online=online, mode_pref=mode_pref)
        b = c.get(f"/api/locations/{location.id}/prediction/break-risk").json()
        assert b["data_status"]["cache_status"] == expected_cache
        assert b["probability"] == base["probability"]  # mode never touches the math
