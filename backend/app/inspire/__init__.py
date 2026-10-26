"""Ready-made itineraries to browse when you don't have a trip yet ("Looking for ideas").

Each itinerary is a JSON file in itineraries/: stops in order, days per stop, what you do on
each day, what is worth it and what to skip, tours to book at each stop and similar organised
group trips. The stops are the places the organised trips we read visit most often
("programs" = how many of those trips include the place).

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

# Organised trips read for the place inventory (10 tour-operator sites, October 2026).
INVENTORY_TRIPS = 4916

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

    @model_validator(mode="after")
    def _days(self):
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
    best_months: list[int] = Field(min_length=1)
    season_note: str
    stops: list[ItineraryStop] = Field(min_length=1, max_length=30)
    group_trips: list[GroupTrip] = Field(default_factory=list)

    @field_validator("best_months")
    @classmethod
    def _months(cls, v):
        if any(m < 1 or m > 12 for m in v):
            raise ValueError("months are 1..12")
        return v

    @model_validator(mode="after")
    def _countries(self):
        for s in self.stops:
            if s.country_code not in self.countries:
                raise ValueError(f"{s.name} is in {s.country_code}, not in {self.countries}")
        return self

    @property
    def total_days(self) -> int:
        return sum(s.days for s in self.stops)


@lru_cache
def itineraries() -> tuple[Itinerary, ...]:
    out = [Itinerary.model_validate(json.loads(f.read_text(encoding="utf-8")))
           for f in sorted(DATA_DIR.glob("*.json"))]
    slugs = [i.slug for i in out]
    if len(set(slugs)) != len(slugs):
        raise ValueError("duplicate itinerary slug")
    return tuple(out)


def get(slug: str) -> Itinerary | None:
    return next((i for i in itineraries() if i.slug == slug), None)


def default_start(it: Itinerary, today: date | None = None) -> date:
    """The first day of the next good month, at least two weeks away."""
    d = (today or date.today()) + timedelta(days=14)
    for k in range(13):
        y, m = divmod(d.month - 1 + k, 12)
        first = date(d.year + y, m + 1, 1)
        if first.month in it.best_months and first >= d:
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
