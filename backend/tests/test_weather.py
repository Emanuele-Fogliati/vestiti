"""Weather fetching against a fake Open-Meteo: small per-year climate windows, one retry on
rate limit, and a slow answer does not switch the network off for everyone."""
from datetime import date

import httpx
import pytest

from app.config import get_settings
from app.weather import service
from app.weather.service import WeatherService


def _daily(a: date, b: date, tmax=25.0, tmin=19.0):
    days = [date.fromordinal(o).isoformat() for o in range(a.toordinal(), b.toordinal() + 1)]
    n = len(days)
    return {"daily": {"time": days, "temperature_2m_max": [tmax] * n, "temperature_2m_min": [tmin] * n,
                      "precipitation_sum": [0.0] * n, "wind_speed_10m_max": [12.0] * n}}


@pytest.fixture
def settings():
    return get_settings().model_copy(update={"weather_enabled": True, "climate_years": 4})


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(service, "_RETRY_429_S", 0)
    monkeypatch.setattr(service, "_NETWORK_DOWN_UNTIL", 0.0)


def test_climate_uses_one_small_window_per_year(settings):
    calls = []

    def handle(req):
        a, b = (date.fromisoformat(req.url.params[k]) for k in ("start_date", "end_date"))
        calls.append((a, b))
        return httpx.Response(200, json=_daily(a, b))

    with httpx.Client(transport=httpx.MockTransport(handle)) as c:
        ws = WeatherService(None, settings, client=c, today=date(2026, 10, 25))
        days = ws.days_for(-12.04, -77.03, 150, date(2026, 12, 5), date(2026, 12, 6))
    assert len(calls) == 4
    assert all((b - a).days <= 10 for a, b in calls)
    assert sorted(a.year for a, _ in calls) == [2022, 2023, 2024, 2025]
    assert {d.source for d in days} == {"climate"}
    assert days[0].tmax == 25.0 and days[0].tmin == 19.0


def test_rate_limit_is_retried_once(settings):
    hits = {"n": 0}

    def handle(req):
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(429, json={"error": True, "reason": "Minutely API request limit exceeded"})
        a, b = (date.fromisoformat(req.url.params[k]) for k in ("start_date", "end_date"))
        return httpx.Response(200, json=_daily(a, b))

    one_year = settings.model_copy(update={"climate_years": 1})
    with httpx.Client(transport=httpx.MockTransport(handle)) as c:
        ws = WeatherService(None, one_year, client=c, today=date(2026, 10, 25))
        days = ws.days_for(-12.04, -77.03, 150, date(2026, 12, 5), date(2026, 12, 5))
    assert days[0].source == "climate"


def test_one_failed_year_still_gives_an_average(settings):
    def handle(req):
        a, b = (date.fromisoformat(req.url.params[k]) for k in ("start_date", "end_date"))
        if a.year == 2023:
            return httpx.Response(500)
        return httpx.Response(200, json=_daily(a, b))

    with httpx.Client(transport=httpx.MockTransport(handle)) as c:
        ws = WeatherService(None, settings, client=c, today=date(2026, 10, 25))
        days = ws.days_for(-12.04, -77.03, 150, date(2026, 12, 5), date(2026, 12, 5))
    assert days[0].source == "climate"


def test_estimate_is_plausible_for_high_andes():
    cusco = service.estimate_day(-13.53, 3400, date(2026, 11, 25))
    assert 8 <= (cusco.tmax + cusco.tmin) / 2 <= 16  # Cusco averages ~12 C
