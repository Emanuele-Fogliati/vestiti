"""Routes for the home globe: "find your trip".

routes.json (tools/globe/build_routes.py) holds, for each country and trip length, the shapes
most of the organised trips we read share: where you sleep, for how many days, and what you
see each day. The ready-made itineraries with a full day-by-day guide (app.inspire) are routes
too and take the place of a read route of the same countries, length and shape.

"Dress me for this trip" turns a route into the user's own trip. A route only knows places, not
what you do there, so a town stop is a city day and anything else is "don't know yet" (we
dress for both easy and harder days) until the user says more on the trip page.
"""
from __future__ import annotations

import gzip
import json
import math
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from app import inspire

HERE = Path(__file__).resolve().parent

# (key, label, shortest, longest): the lengths you pick on the globe
BUCKETS = [("1w", "1 week", 5, 8), ("10d", "10 days", 9, 12), ("2w", "2 weeks", 13, 17), ("3w", "3 weeks", 18, 25)]
TOWNS = ("city", "town")


def bucket_of(days: int) -> str | None:
    return next((k for k, _, lo, hi in BUCKETS if lo <= days <= hi), None)


def _overlap(a: list[str], b: list[str]) -> float:
    x, y = {n.casefold() for n in a}, {n.casefold() for n in b}
    return len(x & y) / max(1, len(x | y))


def _from_itinerary(it: inspire.Itinerary) -> dict:
    return {
        "id": f"it-{it.slug}", "guide": it.slug, "countries": it.countries, "bucket": bucket_of(it.total_days),
        "days": it.total_days, "title": it.title, "best_months": it.best_months,
        "stops": [{"place": None, "name": s.name, "country": s.country_code, "kind": "city",
                   "lat": s.lat, "lon": s.lon, "elevation_m": s.elevation_m, "days": s.days,
                   "visits": [[v.day, [v.name]] for v in s.visits],
                   "activities": [a.model_dump() for a in s.activities]} for s in it.stops],
    }


@lru_cache
def routes() -> tuple[dict, ...]:
    read = json.loads((HERE / "routes.json").read_text(encoding="utf-8"))["routes"]
    guided = [_from_itinerary(it) for it in inspire.itineraries() if bucket_of(it.total_days)]
    keep = []
    for r in read:
        names = [s["name"] for s in r["stops"]]
        twin = any(g["bucket"] == r["bucket"] and sorted(g["countries"]) == sorted(r["countries"])
                   and _overlap(names, [s["name"] for s in g["stops"]]) >= 0.3 for g in guided)
        if not twin:
            keep.append({**r, "guide": None})
    out = []
    for r in guided + keep:
        months = months_of(r)
        # a ready-made itinerary keeps the months its guide was written for
        out.append({**r, "months": months, "best_months": r.get("best_months") or best_months(months)})
    return tuple(out)


# ---- weather by month (climate.json: TerraClimate normals per stop, tools/globe/build_climate.py)

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]
GOOD, SO_SO, BAD = 2, 1, 0


@lru_cache
def _climate() -> dict[str, list[list[float]]]:
    path = HERE / "climate.json"
    return json.loads(path.read_text(encoding="utf-8"))["stops"] if path.exists() else {}


def feels_like(t: float, vap: float) -> float:
    """Heat index (NOAA, Rothfusz) of the afternoon: the day's high with the day's humidity.
    Below about 27 °C, or in dry air, it is just the temperature."""
    es = 0.6108 * math.exp(17.27 * t / (t + 237.3))  # saturation vapour pressure, kPa
    rh = max(0.0, min(100.0, 100 * vap / es))
    f = t * 9 / 5 + 32
    if f < 80:
        return t
    hi = (-42.379 + 2.04901523 * f + 10.14333127 * rh - 0.22475541 * f * rh - 6.83783e-3 * f * f
          - 5.481717e-2 * rh * rh + 1.22874e-3 * f * f * rh + 8.5282e-4 * f * rh * rh - 1.99e-6 * f * f * rh * rh)
    return max(t, (hi - 32) * 5 / 9)


def stop_month(lo: float, hi: float, rain: float, mean_rain: float, vap: float = 0.0) -> tuple[int, str | None]:
    """How good a month is at one stop, and why not: rain, heat or cold, the worst wins.
    Rain counts both as an amount (a monsoon month) and against the place's own year: Cusco's
    150 mm in January is its rainy season, Kyoto's 150 mm in October is just Kyoto. Heat counts
    how hot it feels: Tokyo's 31 °C in August with its humidity is a sticky 36."""
    wet = BAD if rain > 250 or (rain > 100 and rain > 2 * mean_rain) else \
        SO_SO if rain > 200 or (rain > 60 and rain > 1.6 * mean_rain) else GOOD
    feel = feels_like(hi, vap)
    humid = feel - hi >= 2
    hot = BAD if hi >= 36 or feel >= 41 else SO_SO if hi >= 33 or feel >= 35 else GOOD
    checks = [
        (wet, "rainy season"),
        (hot, "hot and humid" if humid else "very hot"),
        (BAD if hi <= 0 else SO_SO if hi <= 13 else GOOD, "cold"),
    ]
    score, why = min(checks, key=lambda c: c[0])
    return score, (None if score == GOOD else why)


def months_of(r: dict) -> list[dict] | None:
    """Each month on the route: coldest night, warmest day, good / so-so / poor weather overall
    (days at each stop weigh) and the main reason when it is not good. None without climate."""
    clim = _climate()
    rows = [(s, clim.get(f"{s['lat']:.3f},{s['lon']:.3f}")) for s in r["stops"]]
    if any(c is None for _, c in rows):
        return None
    total = sum(s["days"] for s, _ in rows)
    out = []
    for m in range(12):
        scores = [(s, *stop_month(*c[m][:3], sum(x[2] for x in c) / 12, *c[m][3:])) for s, c in rows]
        avg = sum(s["days"] * sc for s, sc, _ in scores) / total
        bad_days = sum(s["days"] for s, sc, _ in scores if sc == BAD)
        level = GOOD if avg >= 1.5 and bad_days <= 0.25 * total else SO_SO if avg >= 1.0 else BAD
        worst = min(scores, key=lambda x: (x[1], -x[0]["days"]))
        note = f"{worst[2]} in {worst[0]['name']}" if worst[2] and level != GOOD else None
        out.append({"lo": round(min(c[m][0] for _, c in rows)), "hi": round(max(c[m][1] for _, c in rows)),
                    "level": level, "note": note})
    return out


def best_months(months: list[dict] | None) -> list[int]:
    """Months with good weather on the route; if none, the least bad ones."""
    if not months:
        return []
    good = [m + 1 for m, x in enumerate(months) if x["level"] == GOOD]
    if good:
        return good
    top = max(x["level"] for x in months)
    return [m + 1 for m, x in enumerate(months) if x["level"] == top] if top > BAD else []


def get(route_id: str) -> dict | None:
    return next((r for r in routes() if r["id"] == route_id), None)


def start_in(months: list[int], today: date | None = None) -> date:
    """The first day, at least two weeks away, that falls in one of these months (a guess the
    trip page asks to confirm): November picked on 26 October starts on 9 November, not a year
    later. No months: the first day of a month, two weeks away or more."""
    d = (today or date.today()) + timedelta(days=14)
    if months and d.month in months:
        return d
    for k in range(1, 13):
        y, m = divmod(d.month - 1 + k, 12)
        first = date(d.year + y, m + 1, 1)
        if not months or first.month in months:
            return first
    return d


def stops_for(r: dict, start: date) -> list[dict]:
    """The route as trip stops (StopIn fields), back to back from `start`."""
    out, cur = [], start
    for s in r["stops"]:
        end = cur + timedelta(days=s["days"] - 1)
        acts = s.get("activities")
        if not acts:
            acts = [{"type": "city"}] if s["kind"] in TOWNS else []
            if s.get("outdoors") or not acts:
                acts.append({"type": "unknown"})
        visits = [{"name": n, "date": (cur + timedelta(days=d - 1)).isoformat()}
                  for d, names in s["visits"] for n in names if 1 <= d <= s["days"]]
        out.append({
            "name": s["name"], "country_code": s["country"], "latitude": s["lat"], "longitude": s["lon"],
            "elevation_m": s["elevation_m"], "start_date": cur, "end_date": end,
            "activities": acts, "notes": None, "visits": visits, "days_estimated": False,
        })
        cur = end + timedelta(days=1)
    return out


@lru_cache
def payload() -> dict:
    return {
        "buckets": [{"key": k, "label": label} for k, label, _, _ in BUCKETS],
        "routes": list(routes()),
    }


@lru_cache
def payload_bytes() -> tuple[bytes, bytes]:
    raw = json.dumps(payload(), ensure_ascii=False, separators=(",", ":")).encode()
    return raw, gzip.compress(raw, 9)
