"""Ready-made trips of a region for one, two and three weeks (Manu, 2026-11-14).

"Uno va in Patagonia una settimana e fa il viaggio per una settimana, due settimane fa il viaggio
di due settimane..." Written by hand in trips.json: the zones you sleep in (globe place ids,
each with a hand-written area in app.guide.todo) and the nights in each, in travel order. They
make the trip predictable; the days inside each zone are then filled by the zone's ranking
(app.guide.rank) for what the traveller likes.

When the traveller says what they like, the nights move: a zone that gives little of it
(El Chaltén for someone who wants no treks) drops to its least nights and the nights go to the
zone that gives the most, up to its most nights. Nothing else is invented.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from app.guide import rank

HERE = Path(__file__).resolve().parent
MATCH_DAYS = 2  # a ready trip of 14 days answers a request of 12 to 16
LOW_FIT = 0.35  # a zone whose best things give less than this of what you like gets its least nights
TOP_THINGS = 3


class ReadyStop(BaseModel):
    place: str  # globe place id ("ar-el-chalten")
    nights: int = Field(ge=1, le=10)


class ReadyTrip(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    region: str  # app/guide/regions.json id, or "c-xx" for a whole country
    title: str = Field(min_length=5, max_length=80)
    pace: str = Field(pattern=r"^(relaxed|normal|intense)$")
    level: int = Field(ge=1, le=5)  # the highest effort of the trip's things not to miss
    months: list[int] = Field(min_length=1)
    why: str = Field(default="", max_length=240)
    stops: list[ReadyStop] = Field(min_length=1)

    @property
    def days(self) -> int:
        return sum(s.nights for s in self.stops)

    @model_validator(mode="after")
    def _ok(self):
        if any(not 1 <= m <= 12 for m in self.months):
            raise ValueError(f"{self.id}: months are 1-12")
        return self


@lru_cache
def trips() -> tuple[ReadyTrip, ...]:
    doc = json.loads((HERE / "trips.json").read_text(encoding="utf-8"))
    out = tuple(ReadyTrip.model_validate(t) for t in doc["trips"])
    ids = [t.id for t in out]
    if len(ids) != len(set(ids)):
        raise ValueError("ready trip written twice")
    return out


def for_region(region: str, days: int | None, countries: list[str] | None = None) -> ReadyTrip | None:
    """The ready trip of this region nearest to the days asked (within MATCH_DAYS), or the
    two-week one when no length is given."""
    want = days or 14
    cands = [t for t in trips() if t.region == region
             and (not countries or all(s.place[:2].upper() in countries for s in t.stops))]
    cands = [t for t in cands if abs(t.days - want) <= MATCH_DAYS]
    return min(cands, key=lambda t: (abs(t.days - want), t.days)) if cands else None


def _area(place: dict):
    from app.guide.todo import area_for
    return area_for(place["name"], place["country"], place["lat"], place["lon"])


def fit(area, prefs: rank.Prefs) -> float:
    """How much of what the traveller likes the zone's best things give, 0..1."""
    keep, _ = rank.ordered(area.items, prefs)
    top = keep[:TOP_THINGS]
    return sum(rank.interest(it, prefs) for it in top) / len(top) if top else 0.0


def nights(t: ReadyTrip, places: dict, prefs: rank.Prefs | None) -> list[int]:
    """The nights of each stop, moved for what the traveller likes."""
    out = [s.nights for s in t.stops]
    if prefs is None or prefs.empty():
        return out
    areas = [_area(places[s.place]) if s.place in places else None for s in t.stops]
    fits = [fit(a, prefs) if a else None for a in areas]
    freed = 0
    for i, a in enumerate(areas):
        if a and a.nights and fits[i] is not None and fits[i] < LOW_FIT and out[i] > a.nights[0]:
            freed += out[i] - a.nights[0]
            out[i] = a.nights[0]
    order = sorted((i for i, f in enumerate(fits) if f is not None and f >= LOW_FIT), key=lambda i: -fits[i])
    for i in order:
        if not freed:
            break
        most = areas[i].nights[2] if areas[i].nights else out[i] + 2
        add = min(freed, max(0, most - out[i]))
        out[i] += add
        freed -= add
    if freed:  # nowhere to put them: back where they were
        for i, s in enumerate(t.stops):
            give = min(freed, s.nights - out[i])
            if give > 0:
                out[i] += give
                freed -= give
    return out
