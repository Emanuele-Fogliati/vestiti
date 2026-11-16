"""Trekking trails (Manu, 2026-11-13): where exactly to walk and what to wear on it.

GET /api/trails                 the trails, as cards (filter by country, or near a stop)
GET /api/trails/{id}            one trail: the numbers, key points with their drawings, the line
                                on the map, the altitude profile and the time of every stretch
GET /api/trails/{id}/wear       what to wear on it in a month (the same engine as the trip kit)
GET /api/trails/{id}.gpx        the line as GPX, to open in the walker's own navigation app
GET /api/trails/dots            every trail as a dot for the home globe in Trek mode (compact)
GET /api/trails/{id}/card       one trail as a card (the globe opens it when a dot is tapped)
GET /api/trails/around          how far each trail's path comes to a place, or to another trail
"""
from __future__ import annotations

from datetime import date, timedelta
import gzip
import json
from functools import lru_cache
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import art, trails
from app.trails import world
from app.db import get_db
from app.deps import optional_user
from app.models import User

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
    t = trails.find(trail_id)
    if not t:
        raise HTTPException(404, "No such trail")
    return t


def _scene(sid: str | None) -> dict | None:
    lm = art.by_id().get(sid or "")
    return {"kind": "landmark", "id": lm.id, "label": lm.label} if lm else None


def _cover(t: trails.Trail) -> dict | None:
    """The trail's picture: its goal's drawing, else the last point that has one."""
    c = _cover_at(t)
    return c[0] if c else None


def _cover_at(t: trails.Trail) -> tuple[dict, float, float] | None:
    return _cover_at_id(t.id)


@lru_cache(maxsize=None)
def _cover_at_id(tid: str) -> tuple[dict, float, float] | None:
    """The trail's picture and the point of the walk where you see it (Manu 2026-11-16: on the
    map the drawing sits where the thing is, the goal, not at the trailhead)."""
    t = trails.find(tid)
    goal = [p for p in t.points if p.role == "goal"]
    # the drawing sits on the place itself (its own coordinates), never on a point of the route,
    # so the same place is in one spot whichever walk shows it (Manu 2026-11-16)
    for p in goal + list(reversed(t.points)):
        lm = art.by_id().get(p.scene or "")
        if lm:
            return _scene(lm.id), lm.lat, lm.lon
    # until its scenes are linked: the drawing of the goal itself, when the library has it
    for p in goal:
        lm = art.match(p.name, p.lat, p.lon, country=t.country, gateway=False)
        if lm and trails.km(p.lat, p.lon, lm.lat, lm.lon) <= 1.5:
            return _scene(lm.id), lm.lat, lm.lon
    return None


def _sights(t: trails.Trail, skip: set[str]) -> list[dict]:
    """The drawn places the walk goes past (Manu 2026-11-16: "se passa da altri posti che abbiamo
    nel database ... mi aggiungi l'immagine a metà strada"): every landmark of the library within
    a few hundred metres of the path, in walking order, at the point of the path closest to it."""
    g = trails.geo(t.id) or {}
    line = [(p[0], p[1]) for p in g.get("line", [])] or [(p.lat, p.lon) for p in t.points]
    if not line:
        return []
    step = max(1, len(line) // 400)
    line = line[::step] + [line[-1]]
    s, n = min(p[0] for p in line) - 0.02, max(p[0] for p in line) + 0.02
    w, e = min(p[1] for p in line) - 0.03, max(p[1] for p in line) + 0.03
    out = []
    for lm in art.by_id().values():
        if lm.id in skip or not (s <= lm.lat <= n and w <= lm.lon <= e):
            continue
        d, i = min((trails.km(lm.lat, lm.lon, la, lo), i) for i, (la, lo) in enumerate(line))
        if d <= max(0.3, min(lm.radius_km or 0, 0.8)):
            out.append((i, {"id": lm.id, "name": lm.label, "lat": lm.lat, "lon": lm.lon, "art": _scene(lm.id)}))
    return [x for _, x in sorted(out, key=lambda x: x[0])][:12]


def _own_sights(points: list[dict], cover: str | None) -> list[dict]:
    """The walk's own points that have a drawing, each drawing once, on the place itself."""
    out, seen = [], {cover}
    for x in points:
        lm = art.by_id().get((x["art"] or {}).get("id", ""))
        if lm and lm.id not in seen:
            seen.add(lm.id)
            out.append({"id": lm.id, "name": x["name"], "lat": lm.lat, "lon": lm.lon, "art": x["art"]})
    return out


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


def _featured() -> frozenset[str]:
    from app.inspire.days import walks  # the walks of the recommended trips
    return walks()


def card(t: trails.Trail, month: int | None = None) -> dict:
    return {
        "id": t.id, "name": t.name, "country": t.country, "base": t.base, "region": t.region,
        "kind": t.kind, "days": t.days, "shape": t.shape, "difficulty": t.difficulty,
        "glacier": t.glacier, "hours": list(t.hours), "months": t.months,
        "months_text": _months_text(t.months),
        "in_season": None if month is None else month in t.months,
        "why": t.why, "art": _cover(t), "has_map": trails.geo(t.id) is not None,
        # where the picture goes on the map: the point of the walk where you see it
        "art_at": [round(c[1], 4), round(c[2], 4)] if (c := _cover_at(t)) else None,
        "tier": t.tier, "featured": t.id in _featured(), "style": t.style, "area": t.area, "scores": t.scores.model_dump() if t.scores else None,
        # where it starts, for the pins on the Treks map
        "lat": round(t.points[0].lat, 4) if t.points else None, "lon": round(t.points[0].lon, 4) if t.points else None,
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
        return {"trails": [card(t, month) for t in ts],
                "countries": sorted({t.country for t in trails.trails()})}
    return _country_cards(cc, month)


@lru_cache(maxsize=32)
def _country_cards(cc: str | None, month: int | None) -> dict:
    """A country's cards are fixed data: built once (thousands of walks since 2026-11-14)."""
    ts = [t for t in trails.trails() if cc is None or t.country == cc]
    return {"trails": [card(t, month) for t in ts],
            "countries": sorted({t.country for t in trails.trails()})}


LEVELS = ["easy", "moderate", "hard", "technical"]


def _rank(t: trails.Trail) -> int:
    """How far away its dot shows on the globe, the same ladder as the places (Manu 2026-11-14):
    6 = seen from space (the world's iconic treks), 5 = famous, ... 1 = only from close by.
    The top treks of a country are famous; the long tail ranks by its length."""
    if t.id in world.iconic():
        return 6
    if t.tier == "A":
        return 5
    km = (trails.geo(t.id) or {}).get("km") or 0
    return 4 if km >= 100 else 3 if km >= 30 else 2 if km >= 12 else 1


def _packed(request: Request, body: bytes) -> Response:
    """The dots are large (a 10-degree cell of the Alps: ~18,000 treks, 1.4 MB): gzip them."""
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(gzip.compress(body, 6), media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding", "Cache-Control": "public, max-age=3600"})
    return Response(body, media_type="application/json", headers={"Vary": "Accept-Encoding"})


@lru_cache(maxsize=64)
def _dumped(key: str) -> bytes:
    if key == "far":
        return json.dumps(_dots(), ensure_ascii=False, separators=(",", ":")).encode()
    i, j = map(int, key.split("/"))
    return json.dumps({"trails": [[r[0], r[1], r[2], r[3], r[4], "B", r[5], r[6]] for r in world.cell(i, j)]},
                      ensure_ascii=False, separators=(",", ":")).encode()


@lru_cache
def _dots() -> dict:
    def goal(t: trails.Trail):
        return next((p for p in reversed(t.points) if p.role == "goal"), t.points[-1])
    rows = [[t.id, t.name, round(goal(t).lat, 4), round(goal(t).lon, 4), LEVELS.index(t.difficulty), t.tier, t.days,
             _rank(t)] for t in trails.trails()]
    rows += [[r[0], r[1], r[2], r[3], r[4], "B", r[5], r[6]] for r in world.far()]
    return {"fields": ["id", "name", "lat", "lon", "level", "tier", "days", "rank"], "trails": rows,
            "cell": world.CELL, "cell_rank": world.FAR_RANK}


@router.get("/dots")
def dots(request: Request):
    """Manu, 2026-11-14: in Trek mode every trek has its dot on the globe. One row per trail,
    [id, name, lat, lon, difficulty 0-3, tier, days, rank], at the trail's goal: many trails leave
    from the same trailhead (El Chaltén), but each walks to its own lake or summit. The world's
    smaller treks (rank under `cell_rank`) come by cell, from /dots/cell/{i}/{j}, as you zoom in."""
    return _packed(request, _dumped("far"))


@router.get("/dots/cell/{i}/{j}")
def dots_cell(i: int, j: int, request: Request):
    """The smaller treks of one cell of `cell` degrees: lat in [i, i+1) * cell, lon in [j, j+1) * cell."""
    if not (-9 <= i <= 9 and -18 <= j <= 18):
        raise HTTPException(404, "No such cell")
    return _packed(request, _dumped(f"{i}/{j}"))


@router.get("/around")
def around(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
           km: float = Query(100, gt=0, le=200), trail: str | None = Query(None, max_length=120)):
    """{trail id: km} for the trails whose path passes within `km` of the place, or of `trail`'s
    path: the Walks page sorts and labels its zone by it, not by where each walk starts."""
    return {"away": trails.away(lat, lon, km, trail)}


@router.get("/{trail_id}/card")
def one_card(trail_id: str, month: int | None = Query(None, ge=1, le=12)):
    return card(_trail(trail_id), month)


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
    cover = _cover_at(t)
    seen = {x["art"]["id"] for x in points if x["art"]} | ({cover[0]["id"]} if cover else set())
    return {
        **card(t),
        "difficulty_text": DIFFICULTY_TEXT[t.difficulty],
        "start_by": t.start_by, "book": t.book, "water": t.water, "dangers": t.dangers,
        "turnaround": t.turnaround, "sources": [str(s) for s in t.sources],
        "published": t.published.model_dump(mode="json") if t.published else None,
        "points": points,
        # the drawings along the way: the walk's own points that have one, then the library's
        # places it goes past
        "sights": _own_sights(points, cover[0]["id"] if cover else None) + _sights(t, seen),
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
def wear(trail_id: str, month: int = Query(..., ge=1, le=12), db: Session = Depends(get_db),
         user: User | None = Depends(optional_user)):
    """What to wear on the trail in a month: the trip engine, run on this trail alone.
    Each piece carries three real products that pass its needs (cheaper, the pick, better),
    so the Treks page can sell the trek's kit without a trip (Manu, 2026-11-15)."""
    from sqlalchemy import select
    from app import models
    from app.engine import outfit as O
    from app.engine.garments import SLOT_BY_KEY
    from app.services.planner import cut_genders, market_of, product_item
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
    conds = conditions_for_stage(stage, day_walk=t.kind == "day")
    reqs = requirements([stage], conds)
    cold = min(conds, key=lambda c: c.feels_like_c) if conds else None
    need = {k: r for k, r in reqs.items() if r.needed}
    q = select(models.Product).where(models.Product.active.is_(True), models.Product.market == market_of(user),
                                     models.Product.category.in_(list(need)))
    q = q.where(models.Product.gender.in_(cut_genders(user.gender_pref if user else None)))
    cands = O.group_by_slot(O.rate(need, [product_item(p) for p in db.scalars(q).all()]))
    pieces = []
    for slot, r in reqs.items():
        if not r.needed:
            continue
        picks = {tier: O.pick_for_tier(cands.get(slot, []), tier) for tier in ("cheap", "medium", "premium")}
        pieces.append({"products": {k: v.as_dict() if v else None for k, v in picks.items()},
                       "slot": slot, "name": SLOT_BY_KEY[slot].name if slot in SLOT_BY_KEY else r.name,
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
