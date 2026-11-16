"""Ready-made itineraries to browse when you don't have a trip yet ("Looking for ideas").

Each itinerary is a JSON file in itineraries/: stops in order, days per stop, what you do on
each day, what is worth it and what to skip, tours to book at each stop and similar organised
group trips. The stops are the places the organised trips we read visit most often
("programs" = how many of those trips include the place). The counts are internal only: the
API never sends them and the app never says how many trips include a place.

"Pack my bag for this" turns an itinerary into a normal trip (stops with dates and
activities), so the existing weather -> layers -> kit flow runs on it unchanged.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.schemas import ActivityIn

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "itineraries"

# Search pages of the tour marketplaces; the query comes from our data files only.
EXCURSION_PROVIDERS = {
    "getyourguide": ("GetYourGuide", "https://www.getyourguide.com/s/?q={q}"),
    "viator": ("Viator", "https://www.viator.com/searchResults/all?text={q}"),
}


class VisitDay(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    day: int = Field(ge=1)  # day of the stop, from 1


class Excursion(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=2, max_length=120)  # what we search on the marketplaces


class DayPlan(BaseModel):
    """One day at a stop, as the zone's guide plans it (app.guide.todo): its things by id, so the
    page can show each one hour by hour, its walk on the map and what to wear that day."""
    kind: str = Field(pattern=r"^(arrive|day|free)$")
    things: list[str] = Field(default_factory=list, max_length=4)  # item ids of the stop's area
    spare: str | None = None  # a free day: the thing to do if the weather is good


class ItineraryStop(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    country_code: str = Field(min_length=2, max_length=2)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    elevation_m: float = Field(ge=-500, le=9000)
    days: int = Field(ge=1, le=30)
    activities: list[ActivityIn] = Field(min_length=1)
    visits: list[VisitDay] = Field(default_factory=list)
    plan: list[str] = Field(min_length=1)  # one line per day
    do: list[str] = Field(default_factory=list)
    skip: list[str] = Field(default_factory=list)
    excursions: list[Excursion] = Field(default_factory=list)
    programs: int | None = Field(default=None, ge=0)
    area: str | None = None  # the hand-written zone guide (app.guide.todo) the days come from
    day_plans: list[DayPlan] = Field(default_factory=list)

    @model_validator(mode="after")
    def _days(self):
        if self.day_plans and len(self.day_plans) != self.days:
            raise ValueError(f"{self.name}: {self.days} days but {len(self.day_plans)} day plans")
        if len(self.plan) != self.days:
            raise ValueError(f"{self.name}: {self.days} days but {len(self.plan)} plan lines")
        for v in self.visits:
            if v.day > self.days:
                raise ValueError(f"{self.name}: visit {v.name} on day {v.day} of {self.days}")
        return self


class GroupTrip(BaseModel):
    operator: str
    title: str
    days: int = Field(ge=1)
    url: HttpUrl
    network: str = "direct"  # affiliate network key (app.affiliates.networks)
    program_id: str | None = None  # merchant/advertiser id on that network


class Itinerary(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str
    countries: list[str] = Field(min_length=1)
    summary: str
    best_months: list[int] = Field(default_factory=list)  # [] = an off-season route
    season_note: str
    stops: list[ItineraryStop] = Field(min_length=1, max_length=30)
    group_trips: list[GroupTrip] = Field(default_factory=list)
    # the recommended trips (recommended.json): a destination, its length in weeks, and the season
    # band this route is the one for; the hand-written ones above are older, kept for their links
    destination: str = ""
    region: str = ""
    weeks: int | None = Field(default=None, ge=1, le=4)
    months: list[int] = Field(default_factory=list)  # [] = best_months
    pace: str | None = None
    level: int | None = Field(default=None, ge=1, le=5)
    listed: bool = True  # shown in Recommended

    @field_validator("best_months", "months")
    @classmethod
    def _months(cls, v):
        if any(m < 1 or m > 12 for m in v):
            raise ValueError("months are 1..12")
        return v

    @model_validator(mode="after")
    def _band(self):
        if not self.months:
            if not self.best_months:
                raise ValueError(f"{self.slug}: no months")
            self.months = list(self.best_months)
        return self

    @model_validator(mode="after")
    def _countries(self):
        for s in self.stops:
            if s.country_code not in self.countries:
                raise ValueError(f"{s.name} is in {s.country_code}, not in {self.countries}")
        return self

    @property
    def total_days(self) -> int:
        return sum(s.days for s in self.stops)


RECOMMENDED = HERE / "recommended.json"  # built by tools/guide/build_recommended.py


@lru_cache
def itineraries() -> tuple[Itinerary, ...]:
    out = [Itinerary.model_validate(json.loads(f.read_text(encoding="utf-8")))
           for f in sorted(DATA_DIR.glob("*.json"))]
    if RECOMMENDED.exists():
        out += [Itinerary.model_validate(x)
                for x in json.loads(RECOMMENDED.read_text(encoding="utf-8"))["itineraries"]]
    slugs = [i.slug for i in out]
    if len(set(slugs)) != len(slugs):
        raise ValueError("duplicate itinerary slug")
    return tuple(out)


def journey(region: str) -> list[Itinerary]:
    """The routes of one travel region of Recommended: its lengths and season bands."""
    return sorted((i for i in itineraries() if i.listed and i.weeks and i.region == region),
                  key=lambda i: (i.weeks, min(i.months)))


def lead(region: str) -> Itinerary | None:
    """The route a region's card opens on: two weeks, the band with the best weather."""
    its = journey(region)
    return min(its, key=lambda i: (abs((i.weeks or 2) - 2), -len(i.best_months)), default=None)


@lru_cache(maxsize=256)
def custom(region: str, days: int, month: int) -> Itinerary | None:
    """The trip of a travel region for any number of days in a month (Manu, 2026-11-16: "anche
    volendo 10 giorni, 17 giorni"): built on the fly from the nearest ready route (app.inspire.build)."""
    from app.inspire import build
    t = build.fitted(region, days, month)
    return Itinerary.model_validate(build.build(t)) if t else None


def get(slug: str) -> Itinerary | None:
    return next((i for i in itineraries() if i.slug == slug), None)


def default_start(it: Itinerary, today: date | None = None, month: int | None = None) -> date:
    """The first day of the next good month (or of `month`), at least two weeks away."""
    d = (today or date.today()) + timedelta(days=14)
    want = [month] if month else (it.best_months or it.months)
    for k in range(13):
        y, m = divmod(d.month - 1 + k, 12)
        first = date(d.year + y, m + 1, 1)
        if first.month in want and first >= d:
            return first
    return d


def stops_for(it: Itinerary, start: date) -> list[dict]:
    """The itinerary as trip stops (StopIn fields), back to back from `start`."""
    out, cur = [], start
    for s in it.stops:
        end = cur + timedelta(days=s.days - 1)
        out.append({
            "name": s.name, "country_code": s.country_code, "latitude": s.lat, "longitude": s.lon,
            "elevation_m": s.elevation_m, "start_date": cur, "end_date": end,
            "activities": [a.model_dump() for a in s.activities],
            "notes": None,
            "visits": [{"name": v.name, "date": (cur + timedelta(days=v.day - 1)).isoformat()}
                       for v in s.visits],
            "days_estimated": False,
        })
        cur = end + timedelta(days=1)
    return out


def excursion_url(provider: str, query: str) -> str:
    from urllib.parse import quote
    return EXCURSION_PROVIDERS[provider][1].format(q=quote(query))
