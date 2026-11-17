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
    # app/guide/regions.json id, or "c-xx" for a whole country; None: a route across regions and
    # borders (Atacama to Uyuni), only in Recommended, never proposed by app.services.explore
    region: str | None
    title: str = Field(min_length=5, max_length=80)
    pace: str = Field(pattern=r"^(relaxed|normal|intense)$")
    level: int = Field(ge=1, le=5)  # the highest effort of the trip's things not to miss
    months: list[int] = Field(min_length=1)  # the season band this route is the one for
    best: list[int] = Field(default_factory=list)  # best weather inside the band; [] = off season
    why: str = Field(default="", max_length=240)
    note: str = Field(default="", max_length=400)  # the honest season note
    stops: list[ReadyStop] = Field(min_length=1)
    # the travel region of Recommended this route is one length/season of (Manu, 2026-11-16: "viaggi
    # che possono andare su più nazioni", as tour operators cut them); None: only for app.services.explore
    journey: str | None = None

    @property
    def days(self) -> int:
        return sum(s.nights for s in self.stops)

    @model_validator(mode="after")
    def _ok(self):
        if any(not 1 <= m <= 12 for m in self.months + self.best):
            raise ValueError(f"{self.id}: months are 1-12")
        if not set(self.best) <= set(self.months):
            raise ValueError(f"{self.id}: best months outside the band")
        places = [s.place for s in self.stops]
        if len(places) > 1 and places[-1] == places[0]:
            places = places[:-1]  # a round trip ends where it began
        if len(places) != len(set(places)):
            raise ValueError(f"{self.id}: a place written twice")
        return self


def _docs() -> list[dict]:
    """trips.json, then one file per travel area in trips/ (us-west.json, ca.json, ...), so that
    threads writing different regions never edit the same file (2026-11-17)."""
    files = [HERE / "trips.json", *sorted((HERE / "trips").glob("*.json"))]
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


@lru_cache
def trips() -> tuple[ReadyTrip, ...]:
    out = tuple(ReadyTrip.model_validate(t) for doc in _docs() for t in doc.get("trips", []))
    ids = [t.id for t in out]
    if len(ids) != len(set(ids)):
        raise ValueError("ready trip written twice")
    return out


class Journey(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=3, max_length=60)
    blurb: str = Field(min_length=20, max_length=200)


@lru_cache
def journeys() -> tuple[Journey, ...]:
    out = tuple(Journey.model_validate(j) for doc in _docs() for j in doc.get("journeys", []))
    known = {j.id for j in out}
    if len(known) != len(out):
        raise ValueError("journey written twice")
    for t in trips():
        if t.journey and t.journey not in known:
            raise ValueError(f"{t.id}: no journey {t.journey}")
    return out


def for_region(region: str, days: int | None, countries: list[str] | None = None,
               month: int | None = None) -> ReadyTrip | None:
    """The ready trip of this region nearest to the days asked (within MATCH_DAYS), or the
    two-week one when no length is given. With a month, the route of that month's season band
    (the winter route of Iceland in January); without, the main route (the most best months)."""
    want = days or 14
    cands = [t for t in trips() if t.region == region
             and (not countries or all(s.place[:2].upper() in countries for s in t.stops))]
    cands = [t for t in cands if abs(t.days - want) <= MATCH_DAYS]
    if month:
        cands = [t for t in cands if month in t.months]
    return min(cands, key=lambda t: (abs(t.days - want), t.days, -len(t.best))) if cands else None


def season_bands() -> dict[tuple[str, int], list[ReadyTrip]]:
    """(region, weeks) -> its routes, one for each season band."""
    out: dict[tuple[str, int], list[ReadyTrip]] = {}
    for t in trips():
        out.setdefault((t.region, round(t.days / 7)), []).append(t)
    return out


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
