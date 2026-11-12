"""Start a trip from a sentence, a region or a list of stops (Manu, 2026-11-12).

POST /api/plan/understand  "Patagonia a gennaio, tre settimane" -> what it says, and for a
                           region the proposed route
POST /api/plan/propose     the route again after a change (days, month, keep, drop)
POST /api/plan/trip        the stops (proposed, read, or typed as rows) become a trip
GET  /api/plan/suggest     regions and countries for what is typed
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import travel
from app.api.trips import _stop_from, _verify
from app.db import get_db
from app.deps import current_user, rate_limit
from app.models import Trip, User
from app.schemas import MAX_STOPS, StopIn, TripOut, check_date
from app.services import explore, understand

router = APIRouter(prefix="/api/plan", tags=["plan"])
plan_limit = rate_limit("plan", "ai_rate_limit_per_minute")
MAX_TRIP_DAYS = 120


class TextIn(BaseModel):
    text: str = Field(min_length=2, max_length=1500)


class ProposeIn(BaseModel):
    area: str = Field(max_length=60)
    only: list[str] = Field(default_factory=list, max_length=40)
    days: int | None = Field(default=None, ge=1, le=MAX_TRIP_DAYS)
    month: int | None = Field(default=None, ge=1, le=12)
    keep: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=30)
    drop: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=60)
    last: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=5)


def _date(d) -> str | None:
    return d.isoformat() if isinstance(d, date) else d


def _proposal(a: dict, only: list[str], days: int | None, month: int | None,
              keep: list[str] | None = None, drop: list[str] | None = None,
              last: list[str] | None = None) -> dict:
    p = explore.propose(a, only, days, month, keep, drop, last)
    return {**p, "last": last or [], "area": {"id": a["id"], "name": a["name"], "kind": a["kind"]}, "only": only,
            "suggested_start": explore.start_for(month, p["best_months"]).isoformat()}


def _geocoded(text: str) -> list[dict]:
    """Names written with a capital that the globe does not know ("Matera"), from the place
    search. No network: nothing."""
    import re

    from app.weather import geocode
    out = []
    short = len(text.split()) <= 3  # "Matera": the first word is the place
    for m in re.finditer(r"\b([A-ZÀ-Ý][\wà-ÿ'’]+(?:\s+(?:de|del|di|da|la|le|los|las|di|y)?\s*[A-ZÀ-Ý][\wà-ÿ'’]+)*)",
                         text):
        name = m.group(1)
        at_start = m.start() == 0 or text[:m.start()].rstrip()[-1:] in ".!?"
        if name.lower() in understand.STOP or len(name) < 4 or (at_start and not short):
            continue
        try:
            hits = geocode.search(name, limit=1)
        except Exception:  # noqa: BLE001
            return out
        if hits:
            h = hits[0]
            out.append({"key": f"g-{h['latitude']:.3f},{h['longitude']:.3f}", "place_id": None,
                        "name": h["name"], "country": h.get("country_code"), "lat": h["latitude"],
                        "lon": h["longitude"], "kind": "town", "days": 2, "start_date": None,
                        "fixed_dates": False, "elevation_m": h.get("elevation_m"), "activities": None,
                        "sights": []})
        if len(out) >= 8:
            break
    return out


@router.post("/understand", dependencies=[Depends(plan_limit)])
def understand_text(body: TextIn, _user: User = Depends(current_user)):
    r = understand.read(body.text)
    if r["mode"] == "open":
        found = _geocoded(body.text)
        if found:
            r["mode"], r["stops"] = "stops", found
            r["missing"] = [m for m in r["missing"] if m != "where"]
            if r["days"]:
                each = max(1, r["days"] // len(found))
                for s in found:
                    s["days"] = each
    out = {**r, "start_date": _date(r["start_date"]), "proposal": None, "ideas": []}
    if r["mode"] == "open":
        out["ideas"] = explore.ideas(r["month"], r["days"], r["wishes"])
    if r["mode"] == "region":
        a = explore.area(r["area"]["id"])
        out["proposal"] = _proposal(a, r["only"], r["days"], r["month"], r.get("keep"),
                                    last=r.get("last"))
    return out


@router.post("/propose")
def propose(body: ProposeIn, _user: User = Depends(current_user)):
    a = explore.area(body.area)
    if a is None:
        raise HTTPException(404, "Unknown region")
    only = [c for c in body.only if c in a["countries"]] or list(a["countries"])
    return _proposal(a, only, body.days, body.month, body.keep, body.drop, body.last)


@router.get("/suggest")
def suggest(q: str = "", _user: User = Depends(current_user)):
    return explore.suggest(q[:60])


class PlanStopIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    country: str | None = Field(default=None, max_length=2)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    kind: str | None = Field(default=None, max_length=20)
    days: int = Field(ge=1, le=60)
    start_date: date | None = None  # a date the traveller gave for this stop
    place_id: str | None = Field(default=None, max_length=80)
    elevation_m: float | None = Field(default=None, ge=-500, le=9000)
    activities: list[dict] | None = Field(default=None, max_length=20)
    sights: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=12)

    _sd = field_validator("start_date")(classmethod(lambda cls, v: check_date(v) if v else v))


class PlanTripIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    stops: list[PlanStopIn] = Field(min_length=1, max_length=MAX_STOPS)
    home: dict | None = None  # {lat, lon, country} of where the traveller leaves from
    area: str | None = Field(default=None, max_length=60)

    _sd = field_validator("start_date")(classmethod(lambda cls, v: check_date(v) if v else v))


def _elevation(s: PlanStopIn) -> float:
    if s.elevation_m is not None:
        return s.elevation_m
    if s.place_id:
        from app import globe
        p = globe.by_id().get(s.place_id)
        if p:
            return explore_elevation(p)
    return 0.0


def explore_elevation(p: dict) -> float:
    from app import globe
    try:
        return float(globe.elevation(p))
    except Exception:  # noqa: BLE001 - no network: the trip page lets you correct it
        return 0.0


@router.post("/trip", response_model=TripOut, status_code=201)
def make_trip(body: PlanTripIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The stops become a trip, back to back from the start. A stop with its own date starts
    then (the days in between stay free)."""
    if sum(s.days for s in body.stops) > MAX_TRIP_DAYS:
        raise HTTPException(422, f"A trip can be up to {MAX_TRIP_DAYS} days")
    first_dated = next((s.start_date for s in body.stops if s.start_date), None)
    estimated = body.start_date is None and first_dated is None
    if body.start_date:
        cur = body.start_date
    elif first_dated:
        before = 0
        for s in body.stops:
            if s.start_date:
                break
            before += s.days
        cur = first_dated - timedelta(days=before)
    else:
        cur = explore.start_for(body.month, [])
    stops = []
    for i, s in enumerate(body.stops):
        if s.start_date and s.start_date > cur:
            cur = s.start_date
        end = cur + timedelta(days=s.days - 1)
        acts = s.activities or ([{"type": "city"}] if s.kind in ("city", "town") else [{"type": "unknown"}])
        stops.append(_stop_from(StopIn(
            name=s.name[:200], country_code=s.country, latitude=s.lat, longitude=s.lon,
            elevation_m=_elevation(s), start_date=cur, end_date=end, activities=acts,
            visits=[{"name": n} for n in s.sights[:12]], days_estimated=False,
            place_confirmed=bool(s.place_id)), i))
        cur = end + timedelta(days=1)
    a = explore.area(body.area) if body.area else None
    name = body.name or (a["name"] if a else " · ".join(s.name for s in body.stops[:3])
                         + (" …" if len(body.stops) > 3 else ""))
    countries = sorted({s.country for s in body.stops if s.country})
    trip = Trip(user_id=user.id, name=name[:200], notes=None, start_estimated=estimated, countries=countries)
    if body.home and isinstance(body.home.get("lat"), (int, float)) and isinstance(body.home.get("lon"), (int, float)):
        ap = travel.nearest_airport(body.home["lat"], body.home["lon"], body.home.get("country"))
        trip.home_airport = ap["iata"] if ap else None
    trip.stops = stops
    _verify(trip)
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip
