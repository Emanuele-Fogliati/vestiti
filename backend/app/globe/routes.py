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
            keep.append({**r, "guide": None, "best_months": []})
    return tuple(guided + keep)


def get(route_id: str) -> dict | None:
    return next((r for r in routes() if r["id"] == route_id), None)


def default_start(today: date | None = None) -> date:
    """The first day of the month after next: a placeholder the trip page asks to change."""
    d = (today or date.today()) + timedelta(days=30)
    y, m = divmod(d.month, 12)
    return date(d.year + y, m + 1, 1)


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
