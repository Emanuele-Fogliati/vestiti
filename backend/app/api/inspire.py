"""Ready-made itineraries ("Looking for ideas?") and "Pack my bag for this"."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import inspire
from app.guide import ready
from app.inspire import days as day_by_day, wear
from app.db import get_db
from app.deps import current_user
from app.models import Stop, Trip, User
from app.places.verify import mark_ready_made
from app.schemas import TripOut, check_date

router = APIRouter(prefix="/api/inspire", tags=["inspire"])


def _preview(it: inspire.Itinerary, start: date) -> TripOut:
    """The itinerary laid out as a trip that is not saved: same stops, dates and pictures
    (TripOut picks each stop's landmark) as the trip "Pack my bag" will create."""
    now = datetime.now(timezone.utc)
    stops = [dict(s, id=f"{it.slug}-{i}", position=i)
             for i, s in enumerate(inspire.stops_for(it, start))]
    return TripOut(id=it.slug, name=it.title, notes=None, created_at=now, updated_at=now,
                   stops=stops)


def _card(it: inspire.Itinerary) -> dict:
    prev = _preview(it, inspire.default_start(it))
    art = next((s.art for s in prev.stops if s.art), None)
    top = max(max([s.elevation_m] + [a.max_altitude_m or 0 for a in s.activities]) for s in it.stops)
    return {"slug": it.slug, "title": it.title, "countries": it.countries, "summary": it.summary,
            "days": it.total_days, "best_months": it.best_months, "highest_m": top,
            "places": [s.name for s in it.stops], "art": art.model_dump() if art else None,
            # the recommended trips: where, how many weeks, and the months this route is the one for
            "destination": it.destination or None, "weeks": it.weeks, "months": it.months,
            "pace": it.pace, "level": it.level,
            # its travel region (one card each in Recommended), and whether this route is the card
            "journey": it.region or None, "journey_blurb": _blurb(it.region) if it.weeks else None,
            "lead": bool(it.weeks) and getattr(inspire.lead(it.region), "slug", None) == it.slug}


def _blurb(region: str) -> str:
    return next((x.blurb for x in ready.journeys() if x.id == region), "")


def _journey(it: inspire.Itinerary) -> dict | None:
    """The region this route belongs to: every length and season band, for the pickers."""
    if not it.weeks:
        return None
    routes = inspire.journey(it.region)
    return {"id": it.region, "name": it.destination, "blurb": _blurb(it.region),
            # in the order the trips reach them: Peru & Bolivia, not Bolivia & Peru
            "countries": list(dict.fromkeys(s.country_code for r in routes for s in r.stops)),
            "routes": [{"slug": r.slug, "weeks": r.weeks, "days": r.total_days, "months": r.months,
                        "best_months": r.best_months} for r in routes]}


@router.get("")
def list_itineraries():
    return [_card(it) for it in inspire.itineraries() if it.listed]


def _sized(it: inspire.Itinerary, days: int | None, month: int | None) -> inspire.Itinerary:
    """The route of the same region for `days` days (Manu, 2026-11-16: "anche 10 giorni, 17
    giorni"), cut or stretched from the nearest ready one; the route itself when it is that long."""
    if not days or days == it.total_days or not it.weeks:
        return it
    m = month or (it.best_months or it.months)[0]
    out = inspire.custom(it.region, days, m)
    if out is None:
        raise HTTPException(422, f"No {it.destination} trip of {days} days in that month")
    return out


@router.get("/{slug}")
def get_itinerary(slug: str, start: date | None = None, month: int | None = Query(None, ge=1, le=12),
                  days: int | None = Query(None, ge=3, le=35)):
    """month: the trip in that month (Recommended filtered by month), with what to wear then.
    days: the same region for that many days (the nearest route, cut or stretched)."""
    it = inspire.get(slug)
    if it is None:
        raise HTTPException(404, "Itinerary not found")
    it = _sized(it, days, month)
    try:
        start = check_date(start) or inspire.default_start(it, month=month)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    prev = _preview(it, start)
    stops = []
    before = 0
    for i, (s, out) in enumerate(zip(it.stops, prev.stops)):
        stops.append({
            **out.model_dump(mode="json"),
            "plan": s.plan, "do": s.do, "skip": s.skip,
            # each day: what you do hour by hour, its walk on the map, what to wear that day
            "days": day_by_day.for_stop(it, i, before, month or start.month),
            "excursions": [{"title": e.title, "links": [
                {"provider": p, "label": label, "href": f"/api/go/excursion/{it.slug}/{i}/{n}?provider={p}"}
                for p, (label, _) in inspire.EXCURSION_PROVIDERS.items()]}
                for n, e in enumerate(s.excursions)],
        })
        before += s.days
    return {
        **_card(it),
        "season_note": it.season_note,
        "journey": _journey(it),
        "start_date": start.isoformat(),
        # what to wear, worked out by the layer engine from each stop's climate that month
        "wear": wear.for_itinerary(it, month or start.month),
        "stops": stops,
        "group_trips": [{"operator": g.operator, "title": g.title, "days": g.days,
                         "href": f"/api/go/tour/{it.slug}/{n}"} for n, g in enumerate(it.group_trips)],
    }


class PackIn(BaseModel):
    start_date: date | None = None  # none: the next good month, shown as a guess
    month: int | None = Field(default=None, ge=1, le=12)  # no date but a month: its 1st
    days: int | None = Field(default=None, ge=3, le=35)  # another length than the route's own

    _sd = field_validator("start_date")(classmethod(lambda cls, v: check_date(v)))


@router.post("/{slug}/trip", response_model=TripOut, status_code=201)
def pack_for_this(slug: str, body: PackIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """Dress me for this trip: the itinerary becomes the user's own trip, ready for the kit.
    It stays linked to the itinerary (source_itinerary) for the day-by-day guide and tours."""
    it = inspire.get(slug)
    if it is None:
        raise HTTPException(404, "Itinerary not found")
    it = _sized(it, body.days, body.month or (body.start_date.month if body.start_date else None))
    start = body.start_date or inspire.default_start(it, month=body.month)
    trip = Trip(user_id=user.id, name=it.title, notes=f"From the itinerary '{it.title}'.",
                start_estimated=body.start_date is None, source_itinerary=it.slug)
    trip.stops = [Stop(position=i, **s) for i, s in enumerate(inspire.stops_for(it, start))]
    mark_ready_made(trip)
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip
