from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.art import assign
from app.db import get_db
from app.deps import current_user, own_trip
from app.models import Stop, Trip, User
from app.schemas import ReorderIn, StopIn, StopOut, StopPatch, TripIn, TripOut, TripPatch, TripSummary

router = APIRouter(prefix="/api/trips", tags=["trips"])
MAX_STOPS = 30


def _renumber(trip: Trip):
    for i, s in enumerate(sorted(trip.stops, key=lambda s: (s.position, s.start_date))):
        s.position = i


def _stop_from(body: StopIn, position: int) -> Stop:
    return Stop(name=body.name, country_code=(body.country_code or None) and body.country_code.upper(),
                latitude=body.latitude, longitude=body.longitude, elevation_m=body.elevation_m,
                start_date=body.start_date, end_date=body.end_date,
                activities=[a.model_dump() for a in body.activities], notes=body.notes,
                position=position)


@router.get("", response_model=list[TripSummary])
def list_trips(user: User = Depends(current_user), db: Session = Depends(get_db)):
    trips = db.scalars(select(Trip).where(Trip.user_id == user.id).order_by(Trip.updated_at.desc())).all()
    out = []
    for t in trips:
        stops = sorted(t.stops, key=lambda s: s.position)
        out.append(TripSummary(id=t.id, name=t.name, created_at=t.created_at, updated_at=t.updated_at,
                               stop_count=len(stops),
                               start_date=min((s.start_date for s in stops), default=None),
                               end_date=max((s.end_date for s in stops), default=None),
                               places=[s.name for s in stops],
                               art=next(({"id": lm.id, "label": lm.label} for lm in assign(stops) if lm), None)))
    return out


@router.post("", response_model=TripOut, status_code=201)
def create_trip(body: TripIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if len(body.stops) > MAX_STOPS:
        raise HTTPException(422, f"At most {MAX_STOPS} stops")
    trip = Trip(user_id=user.id, name=body.name, notes=body.notes)
    trip.stops = [_stop_from(s, i) for i, s in enumerate(body.stops)]
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.get("/{trip_id}", response_model=TripOut)
def get_trip(trip: Trip = Depends(own_trip)):
    return trip


@router.patch("/{trip_id}", response_model=TripOut)
def patch_trip(body: TripPatch, trip: Trip = Depends(own_trip), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(trip, k, v)
    db.commit()
    db.refresh(trip)
    return trip


@router.delete("/{trip_id}", status_code=204)
def delete_trip(trip: Trip = Depends(own_trip), db: Session = Depends(get_db)):
    db.delete(trip)
    db.commit()


@router.post("/{trip_id}/duplicate", response_model=TripOut, status_code=201)
def duplicate_trip(trip: Trip = Depends(own_trip), db: Session = Depends(get_db)):
    copy = Trip(user_id=trip.user_id, name=f"{trip.name} (copy)", notes=trip.notes)
    copy.stops = [Stop(name=s.name, country_code=s.country_code, latitude=s.latitude,
                       longitude=s.longitude, elevation_m=s.elevation_m, start_date=s.start_date,
                       end_date=s.end_date, activities=list(s.activities or []), notes=s.notes,
                       position=s.position) for s in trip.stops]
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


@router.post("/{trip_id}/stops", response_model=StopOut, status_code=201)
def add_stop(body: StopIn, trip: Trip = Depends(own_trip), db: Session = Depends(get_db)):
    if len(trip.stops) >= MAX_STOPS:
        raise HTTPException(422, f"At most {MAX_STOPS} stops")
    pos = body.position if body.position is not None else len(trip.stops)
    for s in trip.stops:
        if s.position >= pos:
            s.position += 1
    stop = _stop_from(body, pos)
    trip.stops.append(stop)
    _renumber(trip)
    db.commit()
    db.refresh(stop)
    return stop


@router.patch("/{trip_id}/stops/{stop_id}", response_model=StopOut)
def patch_stop(stop_id: str, body: StopPatch, trip: Trip = Depends(own_trip),
               db: Session = Depends(get_db)):
    stop = next((s for s in trip.stops if s.id == stop_id), None)
    if stop is None:
        raise HTTPException(404, "Stop not found")
    data = body.model_dump(exclude_unset=True)
    if "activities" in data and data["activities"] is not None:
        data["activities"] = [dict(a) for a in data["activities"]]
    for k, v in data.items():
        setattr(stop, k, v)
    if stop.end_date < stop.start_date:
        raise HTTPException(422, "end_date is before start_date")
    db.commit()
    db.refresh(stop)
    return stop


@router.delete("/{trip_id}/stops/{stop_id}", status_code=204)
def delete_stop(stop_id: str, trip: Trip = Depends(own_trip), db: Session = Depends(get_db)):
    stop = next((s for s in trip.stops if s.id == stop_id), None)
    if stop is None:
        raise HTTPException(404, "Stop not found")
    trip.stops.remove(stop)
    db.delete(stop)
    _renumber(trip)
    db.commit()


@router.post("/{trip_id}/stops/reorder", response_model=TripOut)
def reorder(body: ReorderIn, trip: Trip = Depends(own_trip), db: Session = Depends(get_db)):
    ids = {s.id: s for s in trip.stops}
    if set(body.stop_ids) != set(ids):
        raise HTTPException(422, "stop_ids must list every stop of the trip exactly once")
    for i, sid in enumerate(body.stop_ids):
        ids[sid].position = i
    db.commit()
    db.refresh(trip)
    return trip
