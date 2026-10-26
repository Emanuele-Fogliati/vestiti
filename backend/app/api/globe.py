import hashlib
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app import globe
from app.db import get_db
from app.deps import current_user
from app.globe import routes as globe_routes
from app.models import Stop, Trip, User
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
    start_date: date | None = None  # none: a placeholder date the trip page asks to change

    _sd = field_validator("start_date")(classmethod(lambda cls, v: check_date(v)))


@router.post("/routes/{route_id}/trip", response_model=TripOut, status_code=201)
def dress_me(route_id: str, body: RouteTripIn, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    """Dress me for this trip: the route becomes the user's own trip, ready for the kit."""
    r = globe_routes.get(route_id)
    if r is None:
        raise HTTPException(404, "Route not found")
    start = body.start_date or globe_routes.default_start()
    trip = Trip(user_id=user.id, name=r["title"], notes="From a route on the globe.",
                start_estimated=body.start_date is None, source_itinerary=r["guide"])
    trip.stops = [Stop(position=i, **s) for i, s in enumerate(globe_routes.stops_for(r, start))]
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip
