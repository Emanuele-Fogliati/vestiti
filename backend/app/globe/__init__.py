"""Places for the home globe and the trip maps.

places.json comes from the reading of organised trips (tools/globe/build_places.py): every place
with its country, kind, coordinates (checked against the country's borders) and how many of the
trips we read visit it. The more trips visit a place, the further out on the globe it shows.

The counts stay on the server: users never see how many trips include a place (Manu, 2026-10-26).
The payload carries only a popularity level from 1 (rare) to 6 (the most visited), enough for the
map to size dots and decide when a place appears.

Each place gets its landmark scene only when the library has one named after it (Cusco gets the
cathedral; a village near Cusco gets none), and the ready-made itineraries that stop there.

A sight inside a city carries the city's id as its parent (hierarchy.py): from far away the
globe shows Florence, zoomed on Florence it shows the Uffizi and Ponte Vecchio, and a trip can
take the whole city or single sights in it.
"""
from __future__ import annotations

import gzip
import json
from functools import lru_cache
from pathlib import Path

from app import art, inspire
from app.globe import hierarchy

HERE = Path(__file__).resolve().parent


def _norm(s: str) -> str:
    return art._norm(s)


# trips needed for each popularity level, from the top (level 6) down; under the last one: level 1
LEVELS = (60, 30, 15, 8, 5)


def level(trips: int) -> int:
    """Popularity level 1..6 shown to the map instead of the trip count."""
    return next((len(LEVELS) + 1 - i for i, t in enumerate(LEVELS) if trips >= t), 1)


@lru_cache
def _exact() -> dict[str, list]:
    """Exact positions of places inside cities (tools/globe/refine_coords.py), when built."""
    f = HERE / "coords.json"
    return json.loads(f.read_text(encoding="utf-8"))["places"] if f.is_file() else {}


@lru_cache
def payload() -> dict:
    doc = json.loads((HERE / "places.json").read_text(encoding="utf-8"))
    its = list(inspire.itineraries())
    # place names each itinerary passes through (stops and the places visited from them)
    in_it: list[set[str]] = [
        {_norm(n) for s in it.stops for n in [s.name, *(v.name for v in s.visits)]} for it in its]
    parent = hierarchy.parents([dict(zip(doc["fields"], r)) for r in doc["places"]])
    exact = _exact()
    places = []
    for pid, name, cc, kind, lat, lon, trips in doc["places"]:
        if pid in exact:  # the Uffizi and the Duomo on their own spots, not on one 1 km dot
            lat, lon = exact[pid][0], exact[pid][1]
        lm = next((m for m in art._named(name)
                   if m.country == cc and art._km(lat, lon, m.lat, m.lon) <= art.NAMESAKE_KM), None)
        hits = [i for i, names in enumerate(in_it) if cc in its[i].countries and _norm(name) in names]
        places.append([pid, name, cc, kind, lat, lon, level(trips), lm.id if lm else None,
                       lm.label if lm else None, hits, parent.get(pid)])
    return {
        "fields": ["id", "name", "country", "kind", "lat", "lon", "level", "art", "art_label", "itineraries",
                   "parent"],
        "itineraries": [{"slug": it.slug, "title": it.title} for it in its],
        "places": places,
    }


@lru_cache
def payload_bytes() -> tuple[bytes, bytes]:
    raw = json.dumps(payload(), ensure_ascii=False, separators=(",", ":")).encode()
    return raw, gzip.compress(raw, 9)


@lru_cache
def by_id() -> dict[str, dict]:
    """Every place by id, as a dict of the payload's fields."""
    d = payload()
    return {r[0]: dict(zip(d["fields"], r)) for r in d["places"]}


@lru_cache
def _route_elevations() -> dict[str, float]:
    """Altitude of the places the routes stop at, read when the routes were built."""
    from app.globe import routes as globe_routes
    return {s["place"]: s["elevation_m"] for r in globe_routes.routes() for s in r["stops"]
            if s.get("place") and s.get("elevation_m") is not None}


def elevation(p: dict) -> float:
    """Altitude of a place for its weather and kit: Cusco is at 3,400 m, not at sea level.
    From the routes when one stops there, else the place search (nearest result within 30 km),
    else 0."""
    known = _route_elevations().get(p["id"])
    if known is not None:
        return float(known)
    from app.weather import geocode
    try:
        hits = geocode.search(p["name"], limit=5, country=p["country"])
    except Exception:  # noqa: BLE001 - no network: the trip page lets you correct it
        hits = []
    near = [(art._km(p["lat"], p["lon"], h["latitude"], h["longitude"]), h) for h in hits]
    near = [x for x in near if x[0] <= 30]
    return float(min(near, key=lambda x: x[0])[1].get("elevation_m") or 0) if near else 0.0


MAX_DAYS_PER_STOP = 5


def trip_stops(ids: list[str], start) -> list[dict]:
    """The places picked on the globe as trip stops (StopIn fields), back to back from `start`.

    A sight becomes a visit of the city it is in (you sleep in Florence and see the Uffizi);
    the city alone is the whole city. Stops keep the order of the first pick; days are a guess
    (2 per stop; with many sights a day for every 3, up to 5) that the trip page asks to
    confirm."""
    from datetime import timedelta

    from app.globe.routes import TOWNS
    from app.services.dates import DEFAULT_DAYS
    places = by_id()
    order: list[str] = []
    visits: dict[str, list[str]] = {}
    for pid in ids:
        p = places[pid]
        root = p["parent"] or pid
        if root not in visits:
            order.append(root)
            visits[root] = []
        if root != pid and p["name"] not in visits[root]:
            visits[root].append(p["name"])
    out, cur = [], start
    for root in order:
        p = places[root]
        days = min(MAX_DAYS_PER_STOP, max(DEFAULT_DAYS, -(-len(visits[root]) // 3)))
        end = cur + timedelta(days=days - 1)
        out.append({
            "name": p["name"], "country_code": p["country"], "latitude": p["lat"], "longitude": p["lon"],
            "elevation_m": elevation(p), "start_date": cur, "end_date": end,
            "activities": [{"type": "city"}] if p["kind"] in TOWNS else [{"type": "unknown"}],
            "notes": None, "visits": [{"name": n, "date": None} for n in visits[root]],
            "days_estimated": True,
        })
        cur = end + timedelta(days=1)
    return out
