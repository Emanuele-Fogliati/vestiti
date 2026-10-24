"""Daily weather per stop.

Sources, in order:
1. Open-Meteo forecast (up to 16 days ahead)            -> source "forecast"
2. Open-Meteo historical archive, same dates of the last N years -> source "climate"
3. Rough latitude/season estimate when the network is down -> source "estimate"

Open-Meteo is free and needs no key. Its free tier is for non-commercial use: a
commercial launch needs their paid API plan (see docs/LAUNCH_CHECKLIST.md).
"""
from __future__ import annotations

import logging
import math
import time
from datetime import date, datetime, timedelta, timezone
from statistics import mean

import httpx
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.engine.strategy import DayWeather
from app.models import WeatherCache

log = logging.getLogger(__name__)
FORECAST_DAYS = 15


def _daterange(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


# When Open-Meteo is unreachable, skip the network for a while instead of making every
# stop of every request wait for a timeout. Process-local, which is fine for one API node.
_NETWORK_DOWN_UNTIL = 0.0
_NETWORK_BACKOFF_S = 120.0


class WeatherService:
    def __init__(self, db: Session | None, settings: Settings | None = None,
                 client: httpx.Client | None = None, today: date | None = None):
        self.db = db
        self.s = settings or get_settings()
        self.client = client
        self.today = today or date.today()

    # ------------------------------------------------------------ cache
    def _cache_get(self, key: str):
        if self.db is None:
            return None
        row = self.db.get(WeatherCache, key)
        if row and row.expires_at.replace(tzinfo=row.expires_at.tzinfo or timezone.utc) > datetime.now(timezone.utc):
            return row.payload
        return None

    def _cache_put(self, key: str, source: str, payload, hours: float):
        if self.db is None:
            return
        now = datetime.now(timezone.utc)
        row = self.db.get(WeatherCache, key)
        if row is None:
            row = WeatherCache(key=key, source=source, payload=payload, fetched_at=now,
                               expires_at=now + timedelta(hours=hours))
            self.db.add(row)
        else:
            row.payload, row.source, row.fetched_at = payload, source, now
            row.expires_at = now + timedelta(hours=hours)
        try:
            self.db.commit()
        except Exception:  # cache must never break a request
            self.db.rollback()

    def _get_json(self, url: str, params: dict) -> dict:
        if not self.s.weather_enabled:
            raise RuntimeError("weather disabled")
        global _NETWORK_DOWN_UNTIL
        if self.client is None and time.monotonic() < _NETWORK_DOWN_UNTIL:
            raise RuntimeError("weather network marked down, using fallback")
        client = self.client or httpx.Client(timeout=self.s.weather_timeout_s)
        try:
            try:
                r = client.get(url, params=params)
            except (httpx.TimeoutException, httpx.NetworkError):
                if self.client is None:
                    _NETWORK_DOWN_UNTIL = time.monotonic() + _NETWORK_BACKOFF_S
                raise
            r.raise_for_status()
            data = r.json()
            if data.get("error"):
                raise RuntimeError(data.get("reason", "open-meteo error"))
            return data
        finally:
            if self.client is None:
                client.close()

    # ------------------------------------------------------------ public
    def days_for(self, lat: float, lon: float, elevation: float, start: date, end: date
                 ) -> list[DayWeather]:
        horizon = self.today + timedelta(days=FORECAST_DAYS)
        archive_edge = self.today - timedelta(days=6)
        out: dict[date, DayWeather] = {}
        fc_dates = [d for d in _daterange(start, end) if archive_edge < d <= horizon]
        past_dates = [d for d in _daterange(start, end) if d <= archive_edge]
        far_dates = [d for d in _daterange(start, end) if d > horizon]
        if fc_dates:
            for d in self._forecast(lat, lon, elevation, fc_dates[0], fc_dates[-1]):
                out[d.date] = d
        if past_dates:
            for d in self._observed(lat, lon, elevation, past_dates[0], past_dates[-1]):
                out[d.date] = d
        if far_dates:
            for d in self._climate(lat, lon, elevation, far_dates[0], far_dates[-1]):
                out[d.date] = d
        missing = [d for d in _daterange(start, end) if d not in out]
        for d in missing:
            out[d] = estimate_day(lat, elevation, d)
        return [out[d] for d in sorted(out)]

    # ------------------------------------------------------------ sources
    def _forecast(self, lat, lon, elev, start, end) -> list[DayWeather]:
        key = f"fc:{lat:.2f}:{lon:.2f}:{elev:.0f}:{start}:{end}"
        cached = self._cache_get(key)
        if cached is None:
            try:
                data = self._get_json(self.s.openmeteo_forecast_url, {
                    "latitude": lat, "longitude": lon, "elevation": elev,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                             "precipitation_probability_max,wind_speed_10m_max,"
                             "wind_gusts_10m_max,uv_index_max",
                    "start_date": start.isoformat(), "end_date": end.isoformat(),
                    "timezone": "auto", "wind_speed_unit": "kmh",
                })
                cached = data["daily"]
                self._cache_put(key, "forecast", cached, self.s.weather_cache_hours)
            except Exception as e:
                log.warning("forecast failed, falling back to climate: %s", e)
                return self._climate(lat, lon, elev, start, end)
        out = []
        for i, t in enumerate(cached["time"]):
            def v(k, default=0.0):
                arr = cached.get(k) or []
                x = arr[i] if i < len(arr) else None
                return default if x is None else x
            prob = cached.get("precipitation_probability_max")
            precip = v("precipitation_sum")
            out.append(DayWeather(
                date=date.fromisoformat(t), tmax=round(v("temperature_2m_max"), 1),
                tmin=round(v("temperature_2m_min"), 1), precip_mm=round(precip, 1),
                precip_prob=float(v("precipitation_probability_max", 80 if precip >= 1 else 10))
                if prob else (80.0 if precip >= 1 else 10.0),
                wind_kmh=round(v("wind_speed_10m_max"), 0),
                gust_kmh=v("wind_gusts_10m_max", None), uv=v("uv_index_max", None),
                source="forecast"))
        return out

    def _archive(self, lat, lon, elev, start: date, end: date) -> dict:
        key = f"ar:{lat:.2f}:{lon:.2f}:{elev:.0f}:{start}:{end}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        data = self._get_json(self.s.openmeteo_archive_url, {
            "latitude": lat, "longitude": lon, "elevation": elev,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "timezone": "auto", "wind_speed_unit": "kmh",
        })
        daily = data["daily"]
        self._cache_put(key, "archive", daily, 24 * 30)
        return daily

    def _observed(self, lat, lon, elev, start, end) -> list[DayWeather]:
        try:
            daily = self._archive(lat, lon, elev, start, end)
        except Exception as e:
            log.warning("archive failed: %s", e)
            return []
        out = []
        for i, t in enumerate(daily["time"]):
            tmax, tmin = daily["temperature_2m_max"][i], daily["temperature_2m_min"][i]
            if tmax is None or tmin is None:
                continue
            p = daily["precipitation_sum"][i] or 0.0
            out.append(DayWeather(date.fromisoformat(t), round(tmax, 1), round(tmin, 1),
                                  round(p, 1), 90.0 if p >= 1 else 5.0,
                                  round(daily["wind_speed_10m_max"][i] or 0), source="observed"))
        return out

    def _climate(self, lat, lon, elev, start, end) -> list[DayWeather]:
        """Average of the same calendar window (+-3 days) over the last N full years."""
        years = self.s.climate_years
        last_year = self.today.year - 1
        first_year = last_year - years + 1
        w0 = _safe_date(first_year, start.month, start.day) - timedelta(days=3)
        span = (end - start).days
        w1 = _safe_date(last_year, start.month, start.day) + timedelta(days=span + 3)
        if w1 >= self.today - timedelta(days=6):
            w1 = self.today - timedelta(days=6)
        try:
            daily = self._archive(lat, lon, elev, w0, w1)
        except Exception as e:
            log.warning("climate archive failed, using estimate: %s", e)
            return [estimate_day(lat, elev, d) for d in _daterange(start, end)]
        by_md: dict[tuple[int, int], list[int]] = {}
        times = [date.fromisoformat(t) for t in daily["time"]]
        for i, t in enumerate(times):
            by_md.setdefault((t.month, min(t.day, 28) if t.month == 2 else t.day), []).append(i)
        out = []
        for d in _daterange(start, end):
            idx = []
            for k in range(-3, 4):
                dd = d + timedelta(days=k)
                idx += by_md.get((dd.month, min(dd.day, 28) if dd.month == 2 else dd.day), [])
            vals = [(daily["temperature_2m_max"][i], daily["temperature_2m_min"][i],
                     daily["precipitation_sum"][i] or 0.0, daily["wind_speed_10m_max"][i] or 0.0)
                    for i in idx if daily["temperature_2m_max"][i] is not None
                    and daily["temperature_2m_min"][i] is not None]
            if not vals:
                out.append(estimate_day(lat, elev, d))
                continue
            mins = sorted(v[1] for v in vals)
            out.append(DayWeather(
                date=d, tmax=round(mean(v[0] for v in vals), 1),
                tmin=round(mean(v[1] for v in vals), 1),
                precip_mm=round(mean(v[2] for v in vals), 1),
                precip_prob=round(100 * sum(1 for v in vals if v[2] >= 1.0) / len(vals)),
                wind_kmh=round(mean(v[3] for v in vals)),
                tmin_p10=round(mins[max(0, int(len(mins) * 0.1) - 0)], 1),
                source="climate"))
        return out


def _safe_date(y: int, m: int, d: int) -> date:
    if m == 2 and d == 29:
        d = 28
    return date(y, m, d)


def estimate_day(lat: float, elev: float, d: date) -> DayWeather:
    """Very rough climate guess (no network). Clearly labelled as an estimate."""
    annual = 27.0 - 0.0066 * lat * lat - 0.0065 * (elev or 0)
    amp = 0.22 * abs(lat)
    peak = 200 if lat >= 0 else 17  # day of year of the warmest period
    doy = d.timetuple().tm_yday
    seasonal = amp * math.cos(2 * math.pi * (doy - peak) / 365.25)
    mean_t = annual + seasonal
    return DayWeather(date=d, tmax=round(mean_t + 4.5, 1), tmin=round(mean_t - 4.5, 1),
                      precip_mm=2.0, precip_prob=35.0, wind_kmh=15.0, source="estimate")
