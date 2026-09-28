from datetime import date

import pytest
import requests

from app.providers.base import ProviderError
from app.providers.open_meteo import OpenMeteoProvider


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


def prov(sess, retries=2):
    return OpenMeteoProvider("http://f", "http://a", 5, retries, session=sess, sleep=lambda s: None)


GOOD = {"daily": {"time": ["2026-07-01", "2026-07-02"], "precipitation_sum": [1.5, None]}}


def test_parses_forecast_and_sends_expected_params():
    s = Sess(Resp(200, GOOD))
    out = prov(s).fetch_forecast(18.5, 73.8, 99)
    assert [(r.date, r.precip_mm) for r in out] == [(date(2026, 7, 1), 1.5), (date(2026, 7, 2), None)]
    url, params, timeout = s.calls[0]
    assert params["forecast_days"] == 16 and params["daily"] == "precipitation_sum" and timeout == 5


def test_retries_on_5xx_then_succeeds():
    s = Sess(Resp(503), Resp(200, GOOD))
    assert len(prov(s).fetch_forecast(1, 1, 3)) == 2 and len(s.calls) == 2


def test_gives_up_after_retries_on_timeout():
    s = Sess(*[requests.Timeout("t")] * 3)
    with pytest.raises(ProviderError, match="unreachable"):
        prov(s).fetch_forecast(1, 1, 3)
    assert len(s.calls) == 3


def test_rate_limit_is_not_retried():
    s = Sess(Resp(429))
    with pytest.raises(ProviderError, match="rate limit"):
        prov(s).fetch_forecast(1, 1, 3)
    assert len(s.calls) == 1


@pytest.mark.parametrize("body", [
    {}, {"daily": {"time": ["2026-07-01"], "precipitation_sum": []}},
    {"daily": {"time": ["not-a-date"], "precipitation_sum": [1]}},
    {"daily": {"time": ["2026-07-01"], "precipitation_sum": [-3]}},
    {"daily": {"time": ["2026-07-01"], "precipitation_sum": ["x"]}}])
def test_malformed_payloads_rejected(body):
    with pytest.raises(ProviderError):
        prov(Sess(Resp(200, body))).fetch_history(1, 1, date(2026, 7, 1), date(2026, 7, 1))


def test_non_json_and_4xx_rejected():
    with pytest.raises(ProviderError):
        prov(Sess(Resp(200, bad_json=True))).fetch_forecast(1, 1, 3)
    with pytest.raises(ProviderError, match="400"):
        prov(Sess(Resp(400))).fetch_forecast(1, 1, 3)
