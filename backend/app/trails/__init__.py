"""Trekking trails (Manu, 2026-11-13): where exactly to walk, trail by trail, and what to wear on it.

A curated set of the best trails of each country, never copied from AllTrails, Komoot, Wikiloc or
Outdooractive (their data is proprietary). Two files per trail:

  data/<cc>/<trail id>.json   written by hand from the park, hut and tourist-board pages (sources)
  geo/<trail id>.json         computed by tools/trails/build_trails.py from OpenStreetMap paths and
                              the Copernicus DEM: the line, distance, climb, profile, stretch times

list.json is the plan: every trail we are making, who makes it (slot) and its scenes to draw.
README.md says how to write a trail. Each key point of a trail can carry the id of its drawing
(a landmark scene of app.art); a trail shows 3-4 of them (Manu, 2026-11-13).
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
GEO = HERE / "geo"

Difficulty = Literal["easy", "moderate", "hard", "technical"]
SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class Published(BaseModel):
    """The distance and climb the park or hut publishes, to check ours against. Both are for the
    WHOLE walk (there and back for out_and_back). gain_m is the total climb; when the source only
    gives the net height difference (top minus start), leave gain_m null: ours is shown."""
    km: float = Field(gt=0, le=400)
    gain_m: float | None = Field(default=None, ge=0, le=15000)
    source: HttpUrl


class Point(BaseModel):
    """A key point of the trail, in walking order: where you start, what you pass, where you arrive."""
    id: str = Field(pattern=SLUG, max_length=30)
    name: str = Field(min_length=3, max_length=90)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    role: Literal["start", "point", "goal"] = "point"
    note: str = Field(default="", max_length=260)
    night: bool = False  # multi-day: you sleep here
    scene: str | None = Field(default=None, pattern=r"^[a-z]{2}-[a-z0-9-]+$")  # its drawing (app.art id)


class Trail(BaseModel):
    id: str = Field(pattern=r"^[a-z]{2}-[a-z0-9]+(-[a-z0-9]+)*$", max_length=60)
    name: str = Field(min_length=3, max_length=80)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    base: str = Field(min_length=2, max_length=60)  # the town you sleep in (matches trip stops)
    region: str = Field(default="", max_length=100)
    kind: Literal["day", "multiday"]
    days: int = Field(default=1, ge=1, le=21)
    shape: Literal["out_and_back", "loop", "one_way"]
    difficulty: Difficulty
    glacier: bool = False  # on ice with crampons
    months: list[int] = Field(min_length=1, max_length=12)  # best months, 1-12
    hours: tuple[float, float]  # walking time, published or guide's, low-high (total for multiday)
    start_by: str = Field(default="", pattern=r"^$|^([01][0-9]|2[0-3]):[0-5][0-9]$")
    published: Published | None = None
    why: str = Field(min_length=10, max_length=300)
    book: str = Field(default="", max_length=400)
    water: str = Field(default="", max_length=200)
    dangers: list[str] = Field(default_factory=list, max_length=6)
    turnaround: str = Field(default="", max_length=260)
    sources: list[HttpUrl] = Field(min_length=1, max_length=8)
    osm: int | None = None  # OpenStreetMap hiking relation, when there is one for this exact trail
    osm_ways: list[int] = Field(default_factory=list, max_length=200)  # OSM ways in walking order
    router: Literal["auto", "local", "osrm"] = "auto"  # how build_trails routes when no OSM line
    points: list[Point] = Field(min_length=2, max_length=8)
    via: list[tuple[float, float]] = Field(default_factory=list, max_length=12)  # routing only

    @field_validator("months")
    @classmethod
    def _months(cls, v):
        if any(m < 1 or m > 12 for m in v) or len(set(v)) != len(v):
            raise ValueError("months are 1-12, each once")
        return v

    @model_validator(mode="after")
    def _shape(self):
        if self.hours[0] <= 0 or self.hours[1] < self.hours[0]:
            raise ValueError("hours must be (low, high), low > 0")
        if self.points[0].role != "start" and self.kind == "day":
            raise ValueError("a day trail's first point is its start")
        if self.points[-1].role != "goal" and not any(p.role == "goal" for p in self.points):
            raise ValueError("a trail needs a goal point")
        ids = [p.id for p in self.points]
        if len(ids) != len(set(ids)):
            raise ValueError("point ids must be unique")
        if self.kind == "multiday" and self.days < 2:
            raise ValueError("a multiday trail lasts 2 days or more")
        if self.kind == "day" and self.days != 1:
            raise ValueError("a day trail lasts 1 day")
        if not self.id.startswith(self.country.lower() + "-"):
            raise ValueError("the id starts with the country code")
        return self


@lru_cache
def trails() -> tuple[Trail, ...]:
    out = [Trail.model_validate(json.loads(f.read_text(encoding="utf-8")))
           for f in sorted(DATA.glob("*/*.json"))]
    ids = [t.id for t in out]
    if len(ids) != len(set(ids)):
        raise ValueError(f"trail written twice: {sorted({i for i in ids if ids.count(i) > 1})}")
    return tuple(out)


@lru_cache
def by_id() -> dict[str, Trail]:
    return {t.id: t for t in trails()}


@lru_cache
def geo(trail_id: str) -> dict | None:
    f = GEO / f"{trail_id}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


@lru_cache
def plan() -> list[dict]:
    """list.json: every trail planned, with its slot and scenes."""
    return json.loads((HERE / "list.json").read_text(encoding="utf-8"))["trails"]


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, a)))


def activity(t: Trail) -> dict:
    """What the trail means for the clothes (an app.schemas.ActivityIn)."""
    g = geo(t.id) or {}
    alt = g.get("max_m") or max((0,), default=0)
    return {"type": "trek_multiday" if t.kind == "multiday" else "hiking",
            "difficulty": t.difficulty, "max_altitude_m": float(alt) if alt else None,
            "glacier": t.glacier}


NEAR_KM = 60.0


def near(lat: float, lon: float, country: str | None = None, name: str | None = None,
         radius_km: float = NEAR_KM) -> list[Trail]:
    """The trails you can walk from a stop: the stop is their base town, or their start is close."""
    from app.guide import _norm
    n = _norm(name or "")
    out = []
    for t in trails():
        if country and t.country != country:
            continue
        s = t.points[0]
        d = km(lat, lon, s.lat, s.lon)
        if (n and _norm(t.base) == n) or d <= radius_km:
            out.append((d, t))
    return [t for _, t in sorted(out, key=lambda x: x[0])]
