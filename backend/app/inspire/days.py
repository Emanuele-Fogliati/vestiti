"""The days of a recommended trip, one by one (Manu, 2026-11-16: "come faccio a vedere che cosa
fare nei 4 giorni a El Chaltén? ... a me quello serve per creare l'outfit in base a dove vado").

Each day of a stop: what you do (the things of the zone's hand-written guide, hour by hour), the
walk on the map when the thing is a trail of app.trails, and what to wear that day, worked out
by the layer engine for that day's own activity at that stop on that date (a Fitz Roy day is not
a town day). Nothing here is written by hand: it all comes from the guides, the trails and the
engine, so a fix in any of them shows up here.
"""
from __future__ import annotations

from functools import lru_cache

from app import trails
from app.guide.todo import NEED_TEXT, areas
from app.inspire import wear

EFFORT = {"easy": "Easy", "moderate": "Moderate", "hard": "Hard"}


@lru_cache
def _items() -> dict[str, dict]:
    return {a.id: {it.id: it for it in a.items} for a in areas()}


def _trail(tid: str | None) -> dict | None:
    t = trails.find(tid) if tid else None
    if t is None:
        return None
    g = trails.geo(t.id) or {}
    pub = t.published
    return {"id": t.id, "name": t.name, "difficulty": t.difficulty, "hours": list(t.hours),
            "km": pub.km if pub else g.get("km"),
            "gain_m": pub.gain_m if pub and pub.gain_m is not None else g.get("gain_m"),
            "max_m": g.get("max_m"), "has_map": bool(g)}


def _act(it) -> dict:
    """What the thing means for the clothes: the trail's own (its real top from the map) or the guide's."""
    t = trails.find(it.trail) if it.trail else None
    if t is not None:
        a = trails.activity(t)
        guide_top = (it.act or {}).get("max_altitude_m") or 0
        if guide_top > (a.get("max_altitude_m") or 0):
            a["max_altitude_m"] = guide_top
    else:
        a = dict(it.act or {"type": "city"})
    return {k: v for k, v in a.items() if v not in (None, False)}


def _thing(it, spare: bool = False) -> dict:
    return {"id": it.id, "name": it.name, "hours": it.hours, "effort": EFFORT[it.effort],
            "need": NEED_TEXT[it.need] if it.need != "any" else "", "best": it.best, "book": it.book,
            "why": it.why, "steps": [s.model_dump() for s in it.steps], "spare": spare,
            "trail": _trail(it.trail)}


def _wear(w: dict) -> dict:
    return {"low": w["low"], "high": w["high"], "rain": w["rain"],
            "wear": [p["name"] for p in w["pieces"] if not p["pack"]],
            "pack": [p["name"] for p in w["pieces"] if p["pack"]],
            "cold": w["cold"]}


_CACHE: dict[tuple, tuple] = {}


def _stop_days(it, index: int, offset: int, month: int) -> tuple:
    s = it.stops[index]
    key = (it.slug, it.total_days, tuple((x.name, x.days) for x in it.stops), index, offset, month)
    if key in _CACHE:
        return _CACHE[key]
    things = _items().get(s.area or "", {})
    stop = {"name": s.name, "lat": s.lat, "lon": s.lon, "elevation_m": s.elevation_m,
            "country_code": s.country_code}
    out = []
    for k, dp in enumerate(s.day_plans):
        done = [things[x] for x in dp.things if x in things]
        spare = things.get(dp.spare) if dp.spare else None
        shown = [_thing(x) for x in done] + ([_thing(spare, spare=True)] if spare else [])
        # a spare day is dressed for its walk: if the sky is good, that is where you will be;
        # a thing out of its season (skiing in May) is shown with its months, not dressed for
        on = [x for x in done + ([spare] if spare else []) if not x.months or month in x.months]
        acts = [_act(x) for x in on if x is not spare] or ([_act(spare)] if spare in on else [])
        # and the evening in the place you sleep: the day's clothes cover the whole day
        acts = acts + [{"type": "city"}]
        out.append({"kind": dp.kind, "title": s.plan[k], "things": shown,
                    **_wear(wear.for_day(stop, month, offset + k, acts))})
    if len(_CACHE) > 4096:
        _CACHE.clear()
    _CACHE[key] = tuple(out)
    return _CACHE[key]


@lru_cache
def walks() -> frozenset[str]:
    """The walks (app.trails ids) that a day of a recommended trip does: the Walks map shows them
    as their drawing, not as a dot (Manu 2026-11-16)."""
    from app import inspire
    out: set[str] = set()
    for it in inspire.itineraries():
        for s in it.stops:
            things = _items().get(s.area or "", {})
            for dp in s.day_plans:
                for x in [*dp.things, *([dp.spare] if dp.spare else [])]:
                    if x in things and things[x].trail:
                        out.add(things[x].trail)
    return frozenset(out)


def for_stop(it, index: int, offset: int, month: int) -> list[dict]:
    """The days of stop `index`; offset: the trip's days before it. [] when the stop has no guide."""
    if not it.stops[index].day_plans:
        return []
    return list(_stop_days(it, index, offset, month))
