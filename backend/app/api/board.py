"""The trip board (Manu, 2026-11-12): the days of the trip at a glance, what is booked and what
can still move, how you get from one place to the next, and what to do in each place day by day
with the weather.

GET  /api/trips/{id}/board   everything the board shows, computed
PUT  /api/trips/{id}/layout  new order / days / status of the stops; the dates follow back to
                             back, and nothing booked may move (409 says what is in the way)
GET  /api/travel/airports    airport search (home airport, a leg's airports)
GET  /api/travel/prices      prices seen recently for a flight (only with a Travelpayouts token)
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import travel
from app.db import get_db
from app.deps import current_user, own_trip
from app.guide import _norm
from app.guide.todo import NEED_TEXT, todo_for
from app.models import Stop, Trip
from app.schemas import FlightBookIn, FlightSearchIn, FlightsTogetherIn, LayoutIn, TripOut, check_date
from app.travel import duffel
from app.services.dayplan import plan_days
from app.weather.service import WeatherService

router = APIRouter(tags=["board"])


def _ordered(trip: Trip) -> list[Stop]:
    return sorted(trip.stops, key=lambda s: (s.position, s.start_date))


def _airport(code: str | None) -> dict | None:
    a = travel.by_code().get(code or "")
    return {"iata": a["iata"], "name": a["name"], "city": a["city"], "country": a["country"]} if a else None


def _leg(prev: Stop | None, stop: Stop | None, saved: dict | None, day: date, home: str | None) -> dict:
    """The leg into `stop` from `prev` (None = home on either side)."""
    pa = {"lat": prev.latitude, "lon": prev.longitude, "country": prev.country_code} if prev else None
    pb = {"lat": stop.latitude, "lon": stop.longitude, "country": stop.country_code} if stop else None
    g = travel.guess(pa, pb)
    saved = saved or {}
    mode = saved.get("mode") or {"local": "local", "road": "bus", "road_or_flight": "bus",
                                 "flight": "flight"}[g["mode"]]
    out = {"from_name": prev.name if prev else "Home", "to_name": stop.name if stop else "Home",
           "date": day.isoformat(), "guess": g["mode"], "km": g.get("km"), "hours": g.get("hours"),
           "border": g.get("border", False), "mode": mode, "chosen": bool(saved.get("mode")),
           "booked": bool(saved.get("booked")), "ref": saved.get("ref"), "note": saved.get("note"),
           "from_airport": None, "to_airport": None, "links": []}
    if mode == "flight" or g["mode"] in ("flight", "road_or_flight"):
        fa = saved.get("from") or (home if prev is None else None)
        if not fa and prev:
            a = travel.nearest_airport(prev.latitude, prev.longitude, prev.country_code)
            fa = a["iata"] if a else None
        ta = saved.get("to") or (home if stop is None else None)
        if not ta and stop:
            a = travel.nearest_airport(stop.latitude, stop.longitude, stop.country_code)
            ta = a["iata"] if a else None
        out["from_airport"], out["to_airport"] = _airport(fa), _airport(ta)
        if fa and ta and fa != ta:
            out["links"] = travel.flight_links(fa, ta, day)
    return out


def _plan_pins(stop: Stop, items) -> dict:
    """Saved choices, plus the visits the trip text named ("Laguna de los Tres on day 2"): a
    thing to do with the same name is pinned to that day unless the traveller moved it."""
    choices = dict(stop.plan or {})
    pins = dict(choices.get("pins") or {})
    for v in stop.visits or []:
        if not v.get("date"):
            continue
        n = _norm(v.get("name", ""))
        for it in items:
            if it.id not in pins and n and (n in _norm(it.name) or _norm(it.name) in n):
                pins[it.id] = v["date"]
    choices["pins"] = pins
    return choices


def _item_out(it, extra: dict | None = None) -> dict:
    d = it.model_dump()
    d["need_text"] = NEED_TEXT[it.need]
    d.update(extra or {})
    return d


@router.get("/api/trips/{trip_id}/board")
def board(trip: Trip = Depends(own_trip), db: Session = Depends(get_db)):
    stops = _ordered(trip)
    ws = WeatherService(db)
    out = []
    prev = None
    for s in stops:
        leg = _leg(prev, s, s.arrival, s.start_date, trip.home_airport)
        todo = todo_for(s.name, s.country_code, s.latitude, s.longitude)
        weather = ws.days_for(s.latitude, s.longitude, s.elevation_m, s.start_date, s.end_date)
        light = prev is None or leg["mode"] == "flight" or (leg["hours"] or 0) >= 3
        p = plan_days(weather, list(todo.items), todo.rain, todo.routes,
                      _plan_pins(s, todo.items), arrival_light=light)
        sources = sorted({d.source for d in weather})
        out.append({
            "id": s.id, "name": s.name, "country_code": s.country_code,
            "start_date": s.start_date.isoformat(), "end_date": s.end_date.isoformat(),
            "days": (s.end_date - s.start_date).days + 1, "status": s.status or "flex",
            "fixed_note": s.fixed_note, "sleep": s.sleep, "days_estimated": bool(s.days_estimated),
            "arrival": leg,
            "todo": {"source": todo.source, "area": todo.area,
                     "items": [_item_out(i) for i in todo.items],
                     "rain": todo.rain.model_dump() if todo.rain else None,
                     "routes": [r.model_dump() for r in todo.routes],
                     "season": todo.season, "sleep_tip": todo.sleep, "sources": todo.sources},
            "plan": {
                "mode": p.mode,
                "choices": s.plan or {},
                "days": [{
                    "date": d.date.isoformat(), "sky": d.sky, "rain_chance": round(d.rain_chance),
                    "source": d.source, "kind": d.kind, "title": d.title, "note": d.note,
                    "override": d.override,
                    "tmin": round(w.tmin), "tmax": round(w.tmax), "wind_kmh": round(w.wind_kmh),
                    "things": [_item_out(t.item, {"note": t.note, "moved": t.moved, "pinned": t.pinned})
                               for t in d.things],
                } for d, w in zip(p.days, weather)],
                "waiting": [_item_out(i) for i in p.waiting],
                "out_of_season": [i.name for i in p.out_of_season],
                "advice": p.advice,
            },
            "weather_sources": sources,
        })
        prev = s
    last = stops[-1] if stops else None
    ret = _leg(last, None, trip.return_leg, last.end_date + timedelta(days=1), trip.home_airport) \
        if last else None
    start = stops[0].start_date if stops else None
    end = max((s.end_date for s in stops), default=None)
    return {
        "trip_id": trip.id, "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "total_days": (end - start).days + 1 if start and end else 0,
        "start_estimated": bool(trip.start_estimated),
        "home_airport": _airport(trip.home_airport),
        "stops": out, "return_leg": ret,
        "prices": bool(travel.get_settings().travelpayouts_token),
    }


def check_layout(trip: Trip, body: LayoutIn) -> list[tuple[Stop, date, date, str]]:
    """The new dates of every stop, or 409 naming what booked thing would move."""
    stops = {s.id: s for s in trip.stops}
    ids = [x.id for x in body.stops]
    if len(ids) != len(stops) or set(ids) != set(stops):
        raise HTTPException(422, "stops must list every stop of the trip exactly once")
    old = _ordered(trip)
    start = body.start_date or (old[0].start_date if old else date.today())
    spans, cur = [], start
    for x in body.stops:  # back to back, with any free days the traveller left between stops
        a = cur + timedelta(days=x.gap_before)
        b = a + timedelta(days=x.days - 1)
        spans.append((a, b))
        cur = b + timedelta(days=1)
    out = []
    for x, (a, b) in zip(body.stops, spans):
        s = stops[x.id]
        status = x.status or s.status or "flex"
        if (s.status == "fixed" and status == "fixed") and (a, b) != (s.start_date, s.end_date):
            raise HTTPException(409, f"{s.name} is fixed ({s.fixed_note or 'booked'}): this change "
                                     "would move it. Unlock it first.")
        if (s.arrival or {}).get("booked") and a != s.start_date:
            mode = (s.arrival or {}).get("mode") or "trip"
            raise HTTPException(409, f"Your booked {mode} to {s.name} is on "
                                     f"{s.start_date.strftime('%d %b')}: this change would move it.")
        out.append((s, a, b, status))
    if (trip.return_leg or {}).get("booked") and old:
        if spans[-1][1] != max(s.end_date for s in old):
            raise HTTPException(409, "Your flight home is booked: this change would move the end "
                                     "of the trip.")
    return out


@router.put("/api/trips/{trip_id}/layout", response_model=TripOut)
def layout(body: LayoutIn, trip: Trip = Depends(own_trip), db: Session = Depends(get_db)):
    from app.api.trips import _move_visits, _verify
    for i, (s, a, b, status) in enumerate(check_layout(trip, body)):
        if (a, b) != (s.start_date, s.end_date):
            if (b - a) != (s.end_date - s.start_date):
                s.days_estimated = False
            shift = a - s.start_date
            plan = dict(s.plan or {})
            if shift and plan.get("pins"):  # "Base Torres on day 2" stays on day 2
                plan["pins"] = {k: (date.fromisoformat(v) + shift).isoformat()
                                for k, v in plan["pins"].items()}
                s.plan = plan
            _move_visits(s, s.start_date, a, b)
            s.start_date, s.end_date = a, b
        s.position = i
        if status != s.status:
            s.status = status
            if status != "fixed":
                s.fixed_note = None
    if body.start_date is not None:
        trip.start_estimated = False
    _verify(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.get("/api/travel/airports")
def airports(q: str = Query(min_length=2, max_length=60)):
    return [{"iata": a["iata"], "name": a["name"], "city": a["city"], "country": a["country"]}
            for a in travel.search_airports(q)]


@router.get("/api/travel/prices")
def prices(origin: str = Query(min_length=3, max_length=3), destination: str = Query(min_length=3, max_length=3),
           day: date = Query(alias="date"), _user=Depends(current_user)):
    try:
        check_date(day)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    o, d = origin.upper(), destination.upper()
    if o not in travel.by_code() or d not in travel.by_code():
        raise HTTPException(422, "unknown airport code")
    p = travel.prices(o, d, day)
    return {"available": p is not None, "prices": p or [],
            "note": "Prices seen recently by other travellers, not live seats: check before you book."}


# ---------------------------------------------------------------- flights: every leg, every flight

def _flight_legs(trip: Trip) -> list[dict]:
    stops = _ordered(trip)
    legs, prev = [], None
    for s in stops:
        leg = _leg(prev, s, s.arrival, s.start_date, trip.home_airport)
        if leg["mode"] == "flight":
            legs.append({"stop_id": s.id, **leg})
        prev = s
    if stops:
        ret = _leg(stops[-1], None, trip.return_leg, stops[-1].end_date + timedelta(days=1), trip.home_airport)
        if ret["mode"] == "flight":
            legs.append({"stop_id": None, **ret})
    return legs


def _kayak(legs: list[dict]) -> str | None:
    """One search page with every leg (Kayak takes up to 6 in its address)."""
    parts = [f"{x['from_airport']['iata']}-{x['to_airport']['iata']}/{x['date']}" for x in legs
             if x["from_airport"] and x["to_airport"] and not x["booked"]]
    if len(parts) < 2 or len(parts) > 6:
        return None
    return "https://www.kayak.com/flights/" + "/".join(parts)


@router.get("/api/trips/{trip_id}/flights")
def flights(trip: Trip = Depends(own_trip)):
    legs = _flight_legs(trip)
    return {"legs": legs, "all_legs_link": _kayak(legs), "search": duffel.enabled(),
            "book": duffel.enabled() and duffel.test_mode(), "test": duffel.test_mode()}


def _duffel_call(fn):
    try:
        return fn()
    except duffel.DuffelError as e:
        raise HTTPException(502, str(e)) from e


@router.post("/api/travel/flights")
def flight_search(body: FlightSearchIn, _user=Depends(current_user)):
    if not duffel.enabled():
        raise HTTPException(503, "Flight search is not set up yet: use the links.")
    offers = _duffel_call(lambda: duffel.search(
        [{"origin": body.origin, "destination": body.destination, "date": body.date}], body.adults))
    return {"offers": offers, "test": duffel.test_mode()}


@router.post("/api/travel/flights/together")
def flights_together(body: FlightsTogetherIn, _user=Depends(current_user)):
    """All legs as one ticket, to compare with buying them one by one."""
    if not duffel.enabled():
        raise HTTPException(503, "Flight search is not set up yet: use the links.")
    offers = _duffel_call(lambda: duffel.search([s.model_dump() for s in body.slices], body.adults))
    offers.sort(key=lambda o: o["price"])
    return {"offers": offers[:10], "test": duffel.test_mode()}


@router.post("/api/trips/{trip_id}/flights/book")
def flight_book(body: FlightBookIn, trip: Trip = Depends(own_trip), db: Session = Depends(get_db)):
    if not (duffel.enabled() and duffel.test_mode()):
        raise HTTPException(503, "Booking in the app is in test mode only for now.")
    stop = None
    if body.stop_id:
        stop = next((s for s in trip.stops if s.id == body.stop_id), None)
        if stop is None:
            raise HTTPException(404, "Stop not found")
    order = _duffel_call(lambda: duffel.book(body.offer_id, [p.model_dump(mode="json") for p in body.passengers]))
    sl = order["slices"][0] if order["slices"] else None
    flights_txt = ", ".join(g["flight"] for g in (sl or {}).get("segments", []))
    saved = {"mode": "flight", "booked": True,
             "ref": f"{order['booking_reference'] or order['order_id']}"[:40],
             "from": sl["origin"] if sl else None, "to": sl["destination"] if sl else None,
             "note": (f"{flights_txt} · " if flights_txt else "") + ("test booking" if order["test"] else "")}
    if stop is not None:
        stop.arrival = saved
    else:
        trip.return_leg = saved
    db.commit()
    return order
