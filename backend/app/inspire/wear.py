"""What to wear on a recommended trip in a given month (Manu, 2026-11-16: "per ogni mese cosa
mettere come vestito").

Worked out, not written: the trip's stops and activities, the month's climate at each stop (the
TerraClimate normals of app.globe, the same estimate the trip page uses offline) and the layer
engine (app.engine.strategy). So when a rule of the engine changes, every recommended trip's
clothes change with it. The traveller's own trip, once made, gets the full kit with products.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

from app.engine.strategy import (
    StageInput,
    conditions_for_stage,
    requirements,
    warm_zone,
    zone_name,
)
from app.weather.service import estimate_day

YEAR = 2027  # any year without a 29 February
START_DAY = 8  # a trip "in July" leaves on 8 July

ORDER = ["shell_top", "insulation_top", "mid_top", "base_top", "base_bottom", "trousers",
         "shell_bottom", "headwear", "gloves", "sun_hat", "socks", "footwear"]


def label(slot: str, r) -> str:
    """The piece in plain words: "Rain jacket", "Warm down jacket", "Hiking boots"."""
    lv = r.level
    if slot == "shell_top":
        return "Rain jacket" if r.waterproof else "Windproof jacket"
    if slot == "insulation_top":
        # by the products of each level: Nano Puff, Down Sweater, Nuptse
        return {"light": "Light puffer", "medium": "Puffer jacket", "warm": "Warm down jacket",
                "very_warm": "Thick down jacket"}[lv]
    if slot == "mid_top":
        return {"light": "Light fleece", "medium": "Fleece", "warm": "Warm fleece",
                "very_warm": "Thick fleece"}[lv]
    if slot == "base_top":
        return {"light": "T-shirts", "medium": "Long-sleeve tops", "warm": "Warm base layer",
                "very_warm": "Thick base layer"}[lv]
    if slot == "base_bottom":
        return "Thermal leggings"
    if slot == "trousers":
        return {"light": "Light trousers or shorts", "medium": "Trousers", "warm": "Warm trousers",
                "very_warm": "Lined winter trousers"}[lv]
    if slot == "shell_bottom":
        return "Rain trousers"
    if slot == "headwear":
        return "Beanie"
    if slot == "gloves":
        return "Light gloves" if lv in ("light", "medium") else "Warm gloves"
    if slot == "sun_hat":
        return "Sun hat"
    if slot == "socks":
        return "Hiking socks" if r.footwear_type in ("hiking_boot", "mountaineering_boot") else "Socks"
    if slot == "footwear":
        name = {"sandal": "Sandals", "sneaker": "Sneakers", "trail_runner": "Trail shoes",
                "hiking_boot": "Hiking boots", "mountaineering_boot": "Mountaineering boots"}[
            r.footwear_type or "sneaker"]
        return f"Waterproof {name.lower()}" if r.waterproof and r.footwear_type != "sandal" else name
    return slot


def stages(stops: list[dict], month: int) -> list[StageInput]:
    """The stops back to back from the 8th of the month, each day at its climate normal.
    stops: name, lat, lon, elevation_m, days, activities."""
    out, cur = [], date(YEAR, month, START_DAY)
    for i, s in enumerate(stops):
        end = cur + timedelta(days=s["days"] - 1)
        days = [estimate_day(s["lat"], s["elevation_m"], cur + timedelta(days=k), s["lon"])
                for k in range(s["days"])]
        out.append(StageInput(index=i, stop_id=str(i), name=s["name"], base_elevation_m=s["elevation_m"],
                              start=cur, end=end, activities=s["activities"] or [{"type": "city"}],
                              days=days, country_code=s.get("country_code")))
        cur = end + timedelta(days=1)
    return out


def for_month(stops: list[dict], month: int) -> dict:
    """{month, low, high, rain, top_m, cold: {feels, place, what}, pieces: [{slot, name, level, pack, why}],
    hot: {names, pieces}}. cold: the moment the warm layers are for (the coldest feels-like)."""
    return {"month": month, **kit(stages(stops, month))}


def for_day(stop: dict, month: int, offset: int, acts: list[dict]) -> dict:
    """What to wear on one day of a recommended trip (Manu, 2026-11-16: "mi serve per creare
    l'outfit in base a dove vado"): the day's own walk or visit at that stop, on the climate of
    that date. offset: days from the start of the trip (which leaves on the 8th of the month)."""
    d = date(YEAR, month, START_DAY) + timedelta(days=offset)
    day = estimate_day(stop["lat"], stop["elevation_m"], d, stop["lon"])
    st = StageInput(index=0, stop_id="0", name=stop["name"], base_elevation_m=stop["elevation_m"], start=d, end=d,
                    activities=acts or [{"type": "city"}], days=[day], country_code=stop.get("country_code"))
    return kit([st])


def kit(st: list[StageInput]) -> dict:
    """The layer engine on these stages: the pieces, the coldest moment and the range."""
    conds = [c for s in st for c in conditions_for_stage(s)]
    reqs = requirements(st, conds)
    zone = warm_zone(st, conds, reqs)
    pieces = []
    for slot in ORDER:
        r = reqs[slot]
        if not r.needed:
            continue
        why = next((w.split(": ", 1)[1] for w in r.reasons if ": " in w), "")
        pieces.append({"slot": slot, "name": label(slot, r), "level": r.level,
                       "pack": bool(r.reasons) and all("in the pack" in w for w in r.reasons), "why": why})
    hot = None
    if zone:
        hot = {"names": zone["names"], "pieces": [zone_name(s, zone["reqs"][s]) for s in zone["slots"]]}
    c = min(conds, key=lambda x: x.feels_like_c)
    cold = {"feels": round(c.feels_like_c), "place": st[c.stage_index].name, "what": c.where}
    days = [d for s in st for d in s.days]
    lows = [d.tmin for d in days]
    highs = [d.tmax for d in days]
    return {
        "low": round(min(lows)), "high": round(max(highs)),
        "rain": round(max(d.precip_prob for d in days)),
        "top_m": round(max([s.base_elevation_m for s in st] + [a.get("max_altitude_m") or 0 for s in st for a in s.activities])),
        "cold": cold, "pieces": pieces, "hot": hot,
    }


@lru_cache(maxsize=1024)
def _cached(key: tuple, month: int) -> dict:
    stops = [dict(zip(("name", "lat", "lon", "elevation_m", "days", "activities"), (n, la, lo, el, d, [dict(a) for a in acts])))
             for n, la, lo, el, d, acts in key]
    return for_month(stops, month)


def for_itinerary(it, month: int) -> dict:
    key = tuple((s.name, s.lat, s.lon, s.elevation_m, s.days,
                 tuple(tuple(sorted(a.model_dump(exclude_none=True).items())) for a in s.activities))
                for s in it.stops)
    return _cached(key, month)
