"""Ready-made itineraries ("Looking for ideas?") and "Pack my bag for this"."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import inspire
from app.db import get_db
from app.deps import current_user
from app.models import Stop, Trip, User
from app.schemas import TripOut

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
            "places": [s.name for s in it.stops], "art": art.model_dump() if art else None}


@router.get("")
def list_itineraries():
    return [_card(it) for it in inspire.itineraries()]


@router.get("/{slug}")
def get_itinerary(slug: str, start: date | None = None):
    it = inspire.get(slug)
    if it is None:
        raise HTTPException(404, "Itinerary not found")
    start = start or inspire.default_start(it)
    prev = _preview(it, start)
    stops = []
    for i, (s, out) in enumerate(zip(it.stops, prev.stops)):
        stops.append({
            **out.model_dump(mode="json"),
            "plan": s.plan, "do": s.do, "skip": s.skip, "programs": s.programs,
            "excursions": [{"title": e.title, "links": [
                {"provider": p, "label": label, "href": f"/api/go/excursion/{it.slug}/{i}/{n}?provider={p}"}
                for p, (label, _) in inspire.EXCURSION_PROVIDERS.items()]}
                for n, e in enumerate(s.excursions)],
        })
    return {
        **_card(it),
        "season_note": it.season_note,
        "start_date": start.isoformat(),
        "inventory_trips": inspire.INVENTORY_TRIPS,
        "stops": stops,
        "group_trips": [{"operator": g.operator, "title": g.title, "days": g.days,
                         "href": f"/api/go/tour/{it.slug}/{n}"} for n, g in enumerate(it.group_trips)],
    }


class PackIn(BaseModel):
    start_date: date | None = None  # none: the next good month, shown as a guess


@router.post("/{slug}/trip", response_model=TripOut, status_code=201)
def pack_for_this(slug: str, body: PackIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """Pack my bag for this: the itinerary becomes the user's own trip, ready for the kit."""
    it = inspire.get(slug)
    if it is None:
        raise HTTPException(404, "Itinerary not found")
    start = body.start_date or inspire.default_start(it)
    trip = Trip(user_id=user.id, name=it.title, notes=f"From the itinerary '{it.title}'.",
                start_estimated=body.start_date is None)
    trip.stops = [Stop(position=i, **s) for i, s in enumerate(inspire.stops_for(it, start))]
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip
