"""What to do at a stop, in order (Manu, 2026-11-12).

Two sources, never invented:
1. todo.json: areas written by hand with sources (Patagonia first). Each thing to do says how
   long it takes, how hard it is, what weather it needs, when to go and what to book.
2. Everywhere else: the most visited sights near the stop, from the places of the globe
   (app.globe), in order of how many organised trips go there. The counts stay on the server:
   the traveller sees the order, never the numbers (Manu, 2026-10-26). These carry no times,
   so the page says so.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.guide import _norm

HERE = Path(__file__).resolve().parent

Need = Literal["clear", "dry", "calm", "any"]
Length = Literal["full", "half", "short"]

NEED_TEXT = {
    "clear": "Needs a clear day",
    "dry": "Better on a dry day",
    "calm": "Off in strong wind",
    "any": "Any weather",
}


class Item(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=3, max_length=80)
    hours: str = ""
    length: Length = "short"
    effort: Literal["easy", "moderate", "hard"] = "easy"
    need: Need = "any"
    best: str = ""
    book: str = ""
    why: str = ""
    months: list[int] = Field(default_factory=list)  # empty = all year
    weekdays: list[int] = Field(default_factory=list)  # 0 Monday .. 6 Sunday; empty = any day
    act: dict | None = None  # what it means for the clothes (an ActivityIn)

    @field_validator("act")
    @classmethod
    def _act(cls, v):
        if v is not None:
            from app.schemas import ActivityIn
            ActivityIn.model_validate(v)
        return v


class Rain(BaseModel):
    name: str
    hours: str = ""
    why: str = ""


class RouteDay(BaseModel):
    title: str
    note: str = ""
    rain: str = ""


class Route(BaseModel):
    """A fixed route with its nights booked (the W Trek): the days follow it whatever the sky."""
    id: str
    name: str
    summary: str = ""
    book: str = ""
    days: list[RouteDay] = Field(min_length=1)


class Area(BaseModel):
    id: str
    names: list[str] = Field(min_length=1)
    country: str = Field(min_length=2, max_length=2)
    lat: float
    lon: float
    radius_km: float = Field(gt=0, le=150)
    season: str = ""
    sleep: str = ""
    sources: list[HttpUrl] = Field(min_length=1)
    items: list[Item] = Field(min_length=1)
    rain: Rain | None = None
    routes: list[Route] = Field(default_factory=list)


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, a)))


@lru_cache
def areas() -> tuple[Area, ...]:
    doc = json.loads((HERE / "todo.json").read_text(encoding="utf-8"))
    return tuple(Area.model_validate(a) for a in doc["areas"])


def area_for(name: str, country: str | None, lat: float | None, lon: float | None) -> Area | None:
    """The hand-written area for a stop: by name first (in the same country when we know it),
    else the nearest area whose radius covers the stop."""
    n = _norm(name or "")
    for a in areas():
        if (country is None or a.country == country) and any(_norm(x) == n for x in a.names):
            return a
    if lat is None or lon is None:
        return None
    near = [(km(lat, lon, a.lat, a.lon), a) for a in areas()
            if country is None or a.country == country]
    near = [x for x in near if x[0] <= x[1].radius_km]
    return min(near, key=lambda x: x[0])[1] if near else None


# how far around a stop we look for sights when no area is written for it
NEAR_KM = {"city": 15.0, "town": 12.0}
NEAR_KM_DEFAULT = 30.0
NEARBY_MAX = 8
KIND_NEED: dict[str, Need] = {"nature": "dry", "island": "calm", "landmark": "any"}


def nearby(name: str, country: str | None, lat: float, lon: float) -> list[Item]:
    """The most visited sights near a stop, most visited first. No times: we don't know them."""
    from app import globe
    places = globe.by_id()
    me = _norm(name or "")
    here = min(((km(lat, lon, p["lat"], p["lon"]), p) for p in places.values()
                if (country is None or p["country"] == country) and _norm(p["name"]) == me),
               key=lambda x: x[0], default=(None, None))[1]
    radius = NEAR_KM.get(here["kind"], NEAR_KM_DEFAULT) if here else NEAR_KM_DEFAULT
    rows = globe._rows()  # with the trip counts, which never leave the server
    trips = {r[0]: r[6] for r in rows}
    out = []
    for p in places.values():
        if p["kind"] in ("city", "town", "region") or (here and p["id"] == here["id"]):
            continue
        if country and p["country"] != country:
            continue
        if _norm(p["name"]) == me:
            continue
        d = km(lat, lon, p["lat"], p["lon"])
        if d <= radius:
            out.append((trips.get(p["id"], 0), -d, p))
    out.sort(key=lambda x: (x[0], x[1]), reverse=True)
    items = []
    for _, d, p in out[:NEARBY_MAX]:
        dist = -d
        items.append(Item(
            id="g-" + p["id"][:70].lower(), name=p["name"][:80],
            hours="" if dist < 3 else f"{round(dist)} km away",
            length="half" if dist >= 10 else "short",
            need=KIND_NEED.get(p["kind"], "any"),
            why="", act=None))
    return items


class Todo(BaseModel):
    source: Literal["guide", "nearby", "none"]
    area: str | None = None
    items: list[Item] = Field(default_factory=list)
    rain: Rain | None = None
    routes: list[Route] = Field(default_factory=list)
    season: str = ""
    sleep: str = ""
    sources: list[str] = Field(default_factory=list)


def todo_for(name: str, country: str | None, lat: float, lon: float) -> Todo:
    a = area_for(name, country, lat, lon)
    if a:
        return Todo(source="guide", area=a.id, items=a.items, rain=a.rain, routes=a.routes,
                    season=a.season, sleep=a.sleep, sources=[str(s) for s in a.sources])
    items = nearby(name, country, lat, lon)
    return Todo(source="nearby" if items else "none", items=items)
