"""Trekking trails (Manu, 2026-11-13): where exactly to walk and what to wear on it.

GET /api/trails                 the trails, as cards (filter by country, or near a stop)
GET /api/trails/{id}            one trail: the numbers, key points with their drawings, the line
                                on the map, the altitude profile and the time of every stretch
GET /api/trails/{id}/wear       what to wear on it in a month (the same engine as the trip kit)
GET /api/trails/{id}.gpx        the line as GPX, to open in the walker's own navigation app
"""
from __future__ import annotations

from datetime import date, timedelta
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import art, trails
from app.db import get_db

router = APIRouter(prefix="/api/trails", tags=["trails"])

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DIFFICULTY_TEXT = {
    "easy": "Easy: a good path, little climbing",
    "moderate": "Moderate: a few hours, steady climbs",
    "hard": "Hard: long, steep or high; you need to be fit",
    "technical": "Technical: ropes, crampons, scrambling or a guide",
}
ODBL = "Path © OpenStreetMap contributors (ODbL); altitude Copernicus DEM"


def _trail(trail_id: str) -> trails.Trail:
    t = trails.by_id().get(trail_id)
    if not t:
        raise HTTPException(404, "No such trail")
    return t


def _scene(sid: str | None) -> dict | None:
    lm = art.by_id().get(sid or "")
    return {"kind": "landmark", "id": lm.id, "label": lm.label} if lm else None


def _cover(t: trails.Trail) -> dict | None:
    """The trail's picture: its goal's drawing, else the last point that has one."""
    goal = [p for p in t.points if p.role == "goal"]
    for p in goal + list(reversed(t.points)):
        s = _scene(p.scene)
        if s:
            return s
    # until its scenes are linked: the drawing of the goal itself, when the library has it
    for p in goal:
        lm = art.match(p.name, p.lat, p.lon, country=t.country, gateway=False)
        if lm and trails.km(p.lat, p.lon, lm.lat, lm.lon) <= 1.5:
            return _scene(lm.id)
    return None


def _numbers(t: trails.Trail) -> dict:
    """The park's published numbers first (a 90 m DEM undercounts steep zigzags); ours otherwise."""
    g = trails.geo(t.id) or {}
    pub = t.published
    return {
        "km": pub.km if pub else g.get("km"),
        "gain_m": pub.gain_m if pub and pub.gain_m is not None else g.get("gain_m"),
        "max_m": g.get("max_m"), "min_m": g.get("min_m"),
        "numbers_from": str(pub.source) if pub else ("map" if g else None),
    }


def _months_text(ms: list[int]) -> str:
    ms = sorted(ms)
    if len(ms) == 12:
        return "All year"
    # a run across the new year (Nov-Mar) reads from its real start
    runs, cur = [], [ms[0]]
    for m in ms[1:]:
        if m == cur[-1] + 1:
            cur.append(m)
        else:
            runs.append(cur)
            cur = [m]
    runs.append(cur)
    if len(runs) > 1 and runs[0][0] == 1 and runs[-1][-1] == 12:
        runs = [runs[-1] + runs[0]] + runs[1:-1]
    return ", ".join(MONTHS[r[0] - 1] if len(r) == 1 else f"{MONTHS[r[0] - 1]}–{MONTHS[r[-1] - 1]}"
                     for r in runs)


def card(t: trails.Trail, month: int | None = None) -> dict:
    return {
        "id": t.id, "name": t.name, "country": t.country, "base": t.base, "region": t.region,
        "kind": t.kind, "days": t.days, "shape": t.shape, "difficulty": t.difficulty,
        "glacier": t.glacier, "hours": list(t.hours), "months": t.months,
        "months_text": _months_text(t.months),
        "in_season": None if month is None else month in t.months,
        "why": t.why, "art": _cover(t), "has_map": trails.geo(t.id) is not None,
        **_numbers(t),
    }


@router.get("")
def list_trails(country: str | None = Query(None, pattern=r"^[A-Za-z]{2}$"),
                lat: float | None = Query(None, ge=-90, le=90),
                lon: float | None = Query(None, ge=-180, le=180),
                name: str | None = Query(None, max_length=120),
                month: int | None = Query(None, ge=1, le=12)):
    cc = country.upper() if country else None
    if lat is not None and lon is not None:
        ts = trails.near(lat, lon, cc, name)
    else:
        ts = [t for t in trails.trails() if cc is None or t.country == cc]
    return {"trails": [card(t, month) for t in ts],
            "countries": sorted({t.country for t in trails.trails()})}


@router.get("/{trail_id}.gpx")
def gpx(trail_id: str):
    t = _trail(trail_id)
    g = trails.geo(t.id)
    if not g:
        raise HTTPException(404, "This trail has no line on the map yet")
    pts = "".join(f'<trkpt lat="{la}" lon="{lo}"><ele>{e}</ele></trkpt>' for la, lo, e in g["line"])
    wpts = "".join(f'<wpt lat="{p.lat}" lon="{p.lon}"><name>{escape(p.name)}</name>'
                   f'<desc>{escape(p.note)}</desc></wpt>' for p in t.points)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<gpx version="1.1" creator="trail planner" xmlns="http://www.topografix.com/GPX/1/1">'
           f'<metadata><name>{escape(t.name)}</name><copyright author="OpenStreetMap contributors">'
           '<license>https://opendatacommons.org/licenses/odbl/</license></copyright></metadata>'
           f'{wpts}<trk><name>{escape(t.name)}</name><trkseg>{pts}</trkseg></trk></gpx>')
    slug = t.id.split("-", 1)[1]
    return Response(xml, media_type="application/gpx+xml",
                    headers={"Content-Disposition": f'attachment; filename="{slug}.gpx"'})


@router.get("/{trail_id}")
def one(trail_id: str):
    t = _trail(trail_id)
    g = trails.geo(t.id) or {}
    gp = {p["id"]: p for p in g.get("points", [])}
    points = [{"id": p.id, "name": p.name, "role": p.role, "note": p.note, "night": p.night,
               "lat": p.lat, "lon": p.lon, "art": _scene(p.scene),
               "km": gp.get(p.id, {}).get("km"), "ele": gp.get(p.id, {}).get("ele")}
              for p in t.points]
    names = {p.id: p.name for p in t.points}
    return {
        **card(t),
        "difficulty_text": DIFFICULTY_TEXT[t.difficulty],
        "start_by": t.start_by, "book": t.book, "water": t.water, "dangers": t.dangers,
        "turnaround": t.turnaround, "sources": [str(s) for s in t.sources],
        "published": t.published.model_dump(mode="json") if t.published else None,
        "points": points,
        "segments": [{**s, "from_name": names.get(s["from"], ""), "to_name": names.get(s["to"], "")}
                     for s in g.get("segments", [])],
        "computed": {k: g[k] for k in ("km", "one_way_km", "gain_m", "loss_m", "walk_hours")} if g else None,
        "profile": g.get("profile", []),
        "line": [[lo, la] for la, lo, _ in g.get("line", [])],
        "attribution": ODBL if g else None,
        "activity": trails.activity(t),
        "base_trails": [x.id for x in trails.trails() if x.base == t.base and x.id != t.id],
    }


def _next(month: int, today: date) -> date:
    y = today.year if month > today.month or (month == today.month and today.day <= 10) else today.year + 1
    return date(y, month, 15)


@router.get("/{trail_id}/wear")
def wear(trail_id: str, month: int = Query(..., ge=1, le=12), db: Session = Depends(get_db)):
    """What to wear on the trail in a month: the trip engine, run on this trail alone."""
    from app.engine.garments import SLOT_BY_KEY
    from app.engine.strategy import StageInput, conditions_for_stage, requirements
    from app.weather.service import WeatherService
    t = _trail(trail_id)
    g = trails.geo(t.id) or {}
    s = t.points[0]
    base = float(g["points"][0]["ele"]) if g.get("points") else 0.0
    start = _next(month, date.today())
    end = start + timedelta(days=max(1, t.days) - 1)
    days = WeatherService(db).days_for(s.lat, s.lon, base, start, end)
    stage = StageInput(index=0, stop_id=t.id, name=t.name, base_elevation_m=base, start=start,
                       end=end, activities=[trails.activity(t)], days=days, country_code=t.country)
    conds = conditions_for_stage(stage)
    reqs = requirements([stage], conds)
    cold = min(conds, key=lambda c: c.feels_like_c) if conds else None
    pieces = []
    for slot, r in reqs.items():
        if not r.needed:
            continue
        pieces.append({"slot": slot, "name": SLOT_BY_KEY[slot].name if slot in SLOT_BY_KEY else r.name,
                       "level": r.level, "waterproof": r.waterproof,
                       "footwear_type": r.footwear_type, "ankle_support": r.ankle_support,
                       "reasons": r.reasons[:2]})
    d0 = days[0] if days else None
    return {
        "trail_id": t.id, "month": month, "in_season": month in t.months,
        "weather": {"tmin": round(d0.tmin), "tmax": round(d0.tmax), "wind_kmh": round(d0.wind_kmh),
                    "rain_chance": round(d0.precip_prob), "source": d0.source} if d0 else None,
        "coldest": {"feels_like_c": round(cold.feels_like_c), "where": cold.where,
                    "altitude_m": round(cold.altitude_m)} if cold else None,
        "pieces": pieces,
    }
