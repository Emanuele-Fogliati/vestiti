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


class Step(BaseModel):
    """One moment of the day, as a good local guide would run it (Manu, 2026-11-12: "quasi ora
    per ora, a livello di un tour operator"). `at` is when, as 24-hour HH:MM."""
    at: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    what: str = Field(min_length=3, max_length=140)
    note: str = Field(default="", max_length=240)


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
    # the day hour by hour, and what tour programmes leave out ("i fuori programma")
    steps: list[Step] = Field(default_factory=list, max_length=16)
    extras: list[str] = Field(default_factory=list, max_length=8)
    sights: list[str] = Field(default_factory=list, max_length=8)  # the places of the globe it covers
    arrive: bool = False  # fits the afternoon you arrive
    trail: str | None = None  # the trail page (app.trails) with the map, profile and kit

    @field_validator("steps")
    @classmethod
    def _in_order(cls, v):
        if [x.at for x in v] != sorted(x.at for x in v):
            raise ValueError("steps must be in time order")
        return v

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
    extras: list[str] = Field(default_factory=list, max_length=10)  # off the programme, for the place


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, a)))


@lru_cache
def areas() -> tuple[Area, ...]:
    """todo.json, then one file per country in areas/ (pe.json, cl.json, ar.json, is.json)."""
    files = [HERE / "todo.json", *sorted((HERE / "areas").glob("*.json"))]
    out = [Area.model_validate(a) for f in files
           for a in json.loads(f.read_text(encoding="utf-8"))["areas"]]
    ids = [a.id for a in out]
    if len(ids) != len(set(ids)):
        raise ValueError(f"area written twice: {sorted({i for i in ids if ids.count(i) > 1})}")
    return tuple(out)


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


TRIP_ITEMS_MAX = 8


def from_trips(name: str, country: str | None, lat: float, lon: float) -> list[Item]:
    """The days out organised trips take from this place, each a day of several things seen
    together ("Pisac · Ollantaytambo · Chinchero"), most taken first (tools/guide/build_patterns.py).
    No times: the operators' pages don't give them."""
    from app import globe
    from app.guide import patterns
    outs = patterns.outings()
    P = globe.by_id()
    me = _norm(name or "")
    near = [(km(lat, lon, P[b]["lat"], P[b]["lon"]), b) for b in outs if b in P
            and (country is None or P[b]["country"] == country)]
    near = [x for x in near if x[0] <= 25]
    if not near:
        return []
    named = [x for x in near if _norm(P[x[1]]["name"]) == me]
    base = min(named or near)[1]
    items = []
    for g, _, n in outs[base][:TRIP_ITEMS_MAX]:
        ps = [P[x] for x in g if x in P]
        if not ps:
            continue
        far = max(km(lat, lon, p["lat"], p["lon"]) for p in ps)
        label = " · ".join(p["name"] for p in ps[:4])
        if len(label) > 80:
            label = label[:79].rsplit(" · ", 1)[0]
        items.append(Item(
            id="t-" + ps[0]["id"][:70].lower(), name=label,
            hours=f"{n} days" if n > 1 else ("" if far < 3 else f"up to {round(far)} km away"),
            length="full" if n > 1 or far >= 25 or len(ps) >= 3 else ("half" if far >= 8 or len(ps) == 2 else "short"),
            need="dry" if any(p["kind"] in ("nature", "island") for p in ps) else "any",
            why="", act=None))
    return items


class Todo(BaseModel):
    source: Literal["guide", "trips", "nearby", "none"]
    area: str | None = None
    items: list[Item] = Field(default_factory=list)
    rain: Rain | None = None
    routes: list[Route] = Field(default_factory=list)
    season: str = ""
    sleep: str = ""
    sources: list[str] = Field(default_factory=list)
    extras: list[str] = Field(default_factory=list)


def todo_for(name: str, country: str | None, lat: float, lon: float) -> Todo:
    return with_trails(_todo_for(name, country, lat, lon), name, country, lat, lon)


def _todo_for(name: str, country: str | None, lat: float, lon: float) -> Todo:
    a = area_for(name, country, lat, lon)
    if a:
        return Todo(source="guide", area=a.id, items=a.items, rain=a.rain, routes=a.routes,
                    season=a.season, sleep=a.sleep, sources=[str(s) for s in a.sources],
                    extras=a.extras)
    trips = from_trips(name, country, lat, lon)
    if trips:
        seen = {n for it in trips for n in it.name.split(" · ")}
        rest = [it for it in nearby(name, country, lat, lon) if it.name not in seen]
        return Todo(source="trips", items=trips + rest[:max(0, NEARBY_MAX - len(trips))])
    items = nearby(name, country, lat, lon)
    return Todo(source="nearby" if items else "none", items=items)


# ---------------------------------------------------------------- trekking trails

_SMALL = {"de", "del", "la", "las", "los", "el", "the", "to", "and", "a", "di", "of", "on", "under",
          "lookout", "mirador", "hike", "walk", "trail"}
TRAIL_KM = 40.0


def _words(s: str) -> set[str]:
    return {w for w in _norm(s).split() if w not in _SMALL and len(w) > 1}


def _same_walk(item: Item, trail) -> bool:
    """'Laguna de los Tres, under Fitz Roy' (the guide) is the trail 'Laguna de los Tres...'."""
    a = _words(item.name)
    for b in (_words(trail.name), _words(trail.points[-1].name)):
        if a and b and len(a & b) / min(len(a), len(b)) >= 0.6:
            return True
    return False


def _trail_item(t) -> Item:
    from app import trails
    g = trails.geo(t.id) or {}
    km_ = t.published.km if t.published else g.get("km")
    lo, hi = t.hours
    hours = f"{lo:g}–{hi:g} h" if hi > lo else f"{lo:g} h"
    if km_:
        hours += f" · about {round(km_)} km"
    return Item(id=f"trail-{t.id}"[:80], name=t.name, hours=hours,
                length="full" if hi >= 6 else ("half" if hi >= 3 else "short"),
                effort={"easy": "easy", "moderate": "moderate"}.get(t.difficulty, "hard"),
                need="clear" if t.difficulty in ("hard", "technical") else "dry",
                book=t.book[:120], why=t.why, months=t.months, act=trails.activity(t), trail=t.id)


def with_trails(todo: Todo, name: str, country: str | None, lat: float, lon: float) -> Todo:
    """Link the things to do that are trails to their trail page, and add the day trails of this
    place that the list does not have yet (multi-day treks are a stop of their own, not a thing
    to do on one day)."""
    from app import trails
    near = trails.near(lat, lon, country, name, radius_km=TRAIL_KM)
    if not near:
        return todo
    used: set[str] = set()
    items = []
    for it in todo.items:
        if it.trail is None and (it.act or {}).get("type") in ("hiking", "trek_multiday"):
            t = next((t for t in near if t.id not in used and _same_walk(it, t)), None)
            if t:
                used.add(t.id)
                it = it.model_copy(update={"trail": t.id})
        items.append(it)
    extra = [_trail_item(t) for t in near if t.kind == "day" and t.id not in used]
    return todo.model_copy(update={"items": items + extra})
