import hashlib
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import globe, inspire
from app.db import get_db
from app.deps import current_user
from app.globe import routes as globe_routes
from app.models import Stop, Trip, User
from app.places.verify import mark_ready_made
from app.schemas import TripOut, check_date

router = APIRouter(prefix="/api/globe", tags=["globe"])


def _revalidated(request: Request, raw: bytes, gz: bytes) -> Response:
    """Revalidated on every load, so new landmark scenes and rebuilt routes reach the globe at
    once (304 when unchanged)."""
    tag = '"' + hashlib.sha1(raw).hexdigest()[:16] + '"'
    headers = {"Cache-Control": "no-cache", "ETag": tag, "Vary": "Accept-Encoding"}
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=headers)
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(gz, media_type="application/json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(raw, media_type="application/json", headers=headers)


@router.get("/places")
def places(request: Request):
    """Every place for the globe in one compact response (rows, not objects)."""
    return _revalidated(request, *globe.payload_bytes())


@router.get("/routes")
def routes(request: Request):
    """The routes you can pick on the globe, by trip length, in one response."""
    return _revalidated(request, *globe_routes.payload_bytes())


class RouteTripIn(BaseModel):
    start_date: date | None = None  # none: a guess the trip page asks to confirm...
    month: int | None = Field(default=None, ge=1, le=12)  # ...in this month, else a good one

    _sd = field_validator("start_date")(classmethod(lambda cls, v: check_date(v)))


@router.post("/routes/{route_id}/trip", response_model=TripOut, status_code=201)
def dress_me(route_id: str, body: RouteTripIn, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    """Dress me for this trip: the route becomes the user's own trip, ready for the kit."""
    r = globe_routes.get(route_id)
    if r is None:
        raise HTTPException(404, "Route not found")
    start = body.start_date or globe_routes.start_in([body.month] if body.month else r["best_months"])
    it = inspire.get(r["guide"]) if r["guide"] else None
    trip = Trip(user_id=user.id, name=r["title"],
                notes=f"From the itinerary '{it.title}'." if it else "From a route on the globe.",
                start_estimated=body.start_date is None, source_itinerary=r["guide"])
    # a ready-made itinerary keeps its own stops (notes, guide links); only the start moves
    stops = inspire.stops_for(it, start) if it else globe_routes.stops_for(r, start)
    trip.stops = [Stop(position=i, **s) for i, s in enumerate(stops)]
    mark_ready_made(trip)
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


class PickedTripIn(BaseModel):
    """Places picked on the globe, in the order picked: whole cities and single sights."""
    places: list[Annotated[str, Field(max_length=80)]] = Field(min_length=1, max_length=60)
    month: int | None = Field(default=None, ge=1, le=12)


MAX_PICKED_STOPS = 20


@router.post("/trip", response_model=TripOut, status_code=201)
def picked_trip(body: PickedTripIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Dress me for the places I picked: Florence (with the Uffizi and Ponte Vecchio), then Rome."""
    known = globe.by_id()
    ids = list(dict.fromkeys(body.places))
    missing = [p for p in ids if p not in known]
    if missing:
        raise HTTPException(404, "Place not found")
    if len({known[p]["parent"] or p for p in ids}) > MAX_PICKED_STOPS:
        raise HTTPException(422, f"Pick up to {MAX_PICKED_STOPS} cities or places")
    start = globe_routes.start_in([body.month] if body.month else [])
    stops = globe.trip_stops(ids, start)
    trip = Trip(user_id=user.id, name=" · ".join(s["name"] for s in stops[:3]) + (" …" if len(stops) > 3 else ""),
                notes="Picked on the globe.", start_estimated=True)
    trip.stops = [Stop(position=i, **s) for i, s in enumerate(stops)]
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip
