"""The way between two stops of a trip, as it is really travelled (Manu, 2026-11-14: "follow the
road, like Google Maps"): by road from OpenStreetMap through the public OSRM car router of
FOSSGIS (routing.openstreetmap.de), or as a flight arc when the stops are far apart or no road
joins them (an ocean, another island). Only trip maps and trek pages draw it; the home globe
never shows trip routes (rule of 2026-10-30).

GET /api/roads?pts=lat,lon;lat,lon;...   one leg per pair of consecutive stops
"""
from __future__ import annotations

import math

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.weather.service import WeatherService

router = APIRouter(prefix="/api/roads", tags=["roads"])

OSRM = "https://routing.openstreetmap.de/routed-car/route/v1/driving/"
FLY_KM = 1200  # farther than this: a flight
DETOUR = 3.0  # a road this many times longer than the straight line is a road around a sea
MAX_STOPS = 40
CACHE_HOURS = 24 * 60


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, h)))


def arc(a: tuple[float, float], b: tuple[float, float], n: int = 32) -> list[list[float]]:
    """The great circle from a to b, as [lon, lat] points (a flight)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = 2 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2
                                + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))
    if d == 0:
        return [[a[1], a[0]], [b[1], b[0]]]
    out = []
    for i in range(n + 1):
        f = i / n
        A, B = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
        x = A * math.cos(la1) * math.cos(lo1) + B * math.cos(la2) * math.cos(lo2)
        y = A * math.cos(la1) * math.sin(lo1) + B * math.cos(la2) * math.sin(lo2)
        z = A * math.sin(la1) + B * math.sin(la2)
        out.append([round(math.degrees(math.atan2(y, x)), 5),
                    round(math.degrees(math.atan2(z, math.hypot(x, y))), 5)])
    return out


def leg(a: tuple[float, float], b: tuple[float, float], cache: WeatherService | None) -> dict:
    straight = km(a, b)
    fly = {"mode": "air", "km": round(straight), "hours": None, "line": arc(a, b)}
    if straight > FLY_KM:
        return fly
    if straight < 0.5:
        return {"mode": "road", "km": 0, "hours": 0, "line": [[a[1], a[0]], [b[1], b[0]]]}
    key = f"road:{a[0]:.3f},{a[1]:.3f}>{b[0]:.3f},{b[1]:.3f}"
    hit = cache._cache_get(key) if cache else None
    if hit:
        return hit
    if not get_settings().roads_enabled:
        return {"mode": "line", "km": round(straight), "hours": None, "line": [[a[1], a[0]], [b[1], b[0]]]}
    try:
        r = httpx.get(f"{OSRM}{a[1]:.5f},{a[0]:.5f};{b[1]:.5f},{b[0]:.5f}",
                      params={"overview": "simplified", "geometries": "geojson"},
                      headers={"User-Agent": "trip-planner/1.0 (open data routes)"}, timeout=20)
        d = r.json()
        route = d["routes"][0] if d.get("code") == "Ok" and d.get("routes") else None
    except Exception:
        return {"mode": "line", "km": round(straight), "hours": None, "line": [[a[1], a[0]], [b[1], b[0]]]}
    if not route or route["distance"] / 1000 > DETOUR * straight + 30:
        out = fly
    else:
        out = {"mode": "road", "km": round(route["distance"] / 1000),
               "hours": round(route["duration"] / 3600, 1),
               "line": [[round(x, 5), round(y, 5)] for x, y in route["geometry"]["coordinates"]]}
    if cache:
        cache._cache_put(key, "osrm", out, CACHE_HOURS)
    return out


def parse(pts: str) -> list[tuple[float, float]]:
    out = []
    for p in pts.split(";"):
        try:
            la, lo = (float(x) for x in p.split(","))
        except ValueError:
            raise HTTPException(422, "pts: lat,lon;lat,lon;...")
        if not (-90 <= la <= 90 and -180 <= lo <= 180):
            raise HTTPException(422, "pts out of range")
        out.append((la, lo))
    if not 2 <= len(out) <= MAX_STOPS:
        raise HTTPException(422, f"2 to {MAX_STOPS} stops")
    return out


@router.get("")
def roads(pts: str = Query(..., max_length=MAX_STOPS * 26), db: Session = Depends(get_db)):
    stops = parse(pts)
    cache = WeatherService(db)
    return {"legs": [leg(a, b, cache) for a, b in zip(stops, stops[1:])],
            "attribution": "Roads © OpenStreetMap contributors (ODbL), routing OSRM / FOSSGIS"}
