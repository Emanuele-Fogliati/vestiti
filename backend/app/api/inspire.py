"""Ready-made itineraries ("Looking for ideas?") and "Pack my bag for this"."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import inspire
from app.inspire import wear
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
            "pace": it.pace, "level": it.level}


@router.get("")
def list_itineraries():
    return [_card(it) for it in inspire.itineraries() if it.listed]


@router.get("/{slug}")
def get_itinerary(slug: str, start: date | None = None, month: int | None = Query(None, ge=1, le=12)):
    """month: the trip in that month (Recommended filtered by month), with what to wear then."""
    it = inspire.get(slug)
    if it is None:
        raise HTTPException(404, "Itinerary not found")
    try:
        start = check_date(start) or inspire.default_start(it, month=month)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    prev = _preview(it, start)
    stops = []
    for i, (s, out) in enumerate(zip(it.stops, prev.stops)):
        stops.append({
            **out.model_dump(mode="json"),
            "plan": s.plan, "do": s.do, "skip": s.skip,
            "excursions": [{"title": e.title, "links": [
                {"provider": p, "label": label, "href": f"/api/go/excursion/{it.slug}/{i}/{n}?provider={p}"}
                for p, (label, _) in inspire.EXCURSION_PROVIDERS.items()]}
                for n, e in enumerate(s.excursions)],
        })
    return {
        **_card(it),
        "season_note": it.season_note,
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

    _sd = field_validator("start_date")(classmethod(lambda cls, v: check_date(v)))


@router.post("/{slug}/trip", response_model=TripOut, status_code=201)
def pack_for_this(slug: str, body: PackIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """Dress me for this trip: the itinerary becomes the user's own trip, ready for the kit.
    It stays linked to the itinerary (source_itinerary) for the day-by-day guide and tours."""
    it = inspire.get(slug)
    if it is None:
        raise HTTPException(404, "Itinerary not found")
    start = body.start_date or inspire.default_start(it, month=body.month)
    trip = Trip(user_id=user.id, name=it.title, notes=f"From the itinerary '{it.title}'.",
                start_estimated=body.start_date is None, source_itinerary=it.slug)
    trip.stops = [Stop(position=i, **s) for i, s in enumerate(inspire.stops_for(it, start))]
    mark_ready_made(trip)
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip
