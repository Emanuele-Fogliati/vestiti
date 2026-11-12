"""From "Patagonia, three weeks in January" to a route you can change (Manu, 2026-11-12).

A trip is often a region, not a place: "Patagonia" is El Calafate, El Chaltén, Torres del
Paine, Ushuaia... Nothing here is invented:

- the region is hand-written geography (app/guide/regions.json) or a whole country;
- the places come from the globe (app.globe), grouped around the towns you sleep in: the
  Perito Moreno glacier and Lago Argentino are seen from El Calafate;
- how much a place matters is how many organised trips go there (the counts stay on the
  server: the traveller sees an order, never a number);
- how many days a place takes is what the organised routes give it (a hand-written
  itinerary counts double); a route that fits the region and the days is the backbone of
  the proposal, the next places by importance fill the days left.
"""
from __future__ import annotations

import json
import math
from datetime import date
from functools import lru_cache
from pathlib import Path

from app.guide.todo import areas as todo_areas, km
from app.places.countries import _data as country_data, norm

HERE = Path(__file__).resolve().parents[1] / "guide"

BASE_KINDS = ("city", "town")
TOWN_IN_CITY_KM = 15  # Ginza is Tokyo: a town this close to a bigger city is part of it
SIGHT_RADIUS_KM = 120  # a sight is seen from the town it is nearest to, within this
ROUTE_SHARE = 0.6
CLUSTER_KM = 150
FAR_KM, FAR_DAYS = 400, 5  # a place this far from the route is added only with this many days to spare  # when filling the days, a new place must be this far from the others  # a route belongs to a region when this share of its days is inside it
MAX_STOP_DAYS = 6
DEFAULT_DAYS = {"city": 2, "town": 2, "island": 3, "nature": 2, "region": 2, "landmark": 1}


# ---------------------------------------------------------------- areas: regions and countries

@lru_cache
def regions() -> tuple[dict, ...]:
    doc = json.loads((HERE / "regions.json").read_text(encoding="utf-8"))
    return tuple({**r, "kind": "region", "keys": tuple(norm(n) for n in [r["name"], *r["names"]])}
                 for r in doc["regions"])


@lru_cache
def countries() -> tuple[dict, ...]:
    out = []
    for cc, d in country_data().items():
        out.append({"id": f"c-{cc.lower()}", "name": d["name"], "kind": "country", "countries": [cc],
                    "boxes": [], "keys": tuple(dict.fromkeys(norm(n) for n in [d["name"], *d["names"]]))})
    return tuple(out)


def area(area_id: str) -> dict | None:
    return next((a for a in (*regions(), *countries()) if a["id"] == area_id), None)


def find_areas(text: str) -> list[dict]:
    """The regions and countries a text names, longest name first ("patagonia cilena" before
    "cile"), each once."""
    t = f" {norm(text)} "
    hits: list[tuple[int, int, dict]] = []
    for a in (*regions(), *countries()):
        for k in a["keys"]:
            if len(k) >= 3 and f" {k} " in t:
                hits.append((t.index(f" {k} "), -len(k), a))
                break
    hits.sort(key=lambda h: (h[1], h[0]))
    seen, out = set(), []
    for _, _, a in hits:
        if a["id"] not in seen:
            seen.add(a["id"])
            out.append(a)
    return out


def best_area(text: str) -> tuple[dict | None, list[str]]:
    """The area a text is about, narrowed to the countries it also names ("Patagonia
    cilena" is Patagonia in Chile). A region beats a country it lies in."""
    found = find_areas(text)
    if not found:
        return None, []
    named = {c for a in found if a["kind"] == "country" for c in a["countries"]}
    reg = next((a for a in found if a["kind"] == "region"), None)
    if reg:
        narrow = [c for c in reg["countries"] if c in named]
        return reg, narrow or list(reg["countries"])
    a = found[0]
    return a, list(a["countries"])


def suggest(q: str, limit: int = 6) -> list[dict]:
    """Regions and countries whose name starts with what is typed."""
    n = norm(q)
    if len(n) < 2:
        return []
    out = []
    for a in (*regions(), *countries()):
        k = next((k for k in a["keys"] if k.startswith(n) or f" {n}" in f" {k}"), None)
        if k:
            out.append((0 if k.startswith(n) else 1, 0 if a["kind"] == "region" else 1, len(k), a))
    out.sort(key=lambda x: x[:3])
    from app.places.countries import name as cname
    return [{"type": a["kind"], "id": a["id"], "name": a["name"],
             "sub": ", ".join(cname(c) or c for c in a["countries"][:3]) + ("…" if len(a["countries"]) > 3 else "")
             if a["kind"] == "region" else "Country"} for *_, a in out[:limit]]


def inside(a: dict, lat: float, lon: float, country: str | None, only: list[str] | None = None) -> bool:
    ccs = only or a["countries"]
    if country and country not in ccs:
        return False
    if not a["boxes"]:
        return True
    return any(b[0] <= lat <= b[2] and b[1] <= lon <= b[3] for b in a["boxes"])


# ---------------------------------------------------------------- places: towns with their sights

@lru_cache
def _trips() -> dict[str, int]:
    from app import globe
    return {r[0]: r[6] for r in globe._rows()}  # never sent to the browser


@lru_cache
def _todo_names() -> frozenset[str]:
    """The first name of each hand-written area: a park with its own page is a place to stay."""
    return frozenset(norm(a.names[0]) for a in todo_areas())


def bases(a: dict, only: list[str] | None = None) -> list[dict]:
    """The places to sleep in an area, most visited (with their sights) first. Each:
    {id, name, country, lat, lon, kind, score, sights: [names]}."""
    from app import globe
    trips = _trips()
    places = [p for p in globe.by_id().values()
              if not p["parent"] and inside(a, p["lat"], p["lon"], p["country"], only)]
    # a park with its own hand-written page (Torres del Paine) is somewhere you stay
    is_base = {p["id"]: p["kind"] in BASE_KINDS or norm(p["name"]) in _todo_names() for p in places}
    cities = [p for p in places if p["kind"] == "city"]
    for p in places:
        if p["kind"] == "town" and any(c["id"] != p["id"] and trips.get(c["id"], 0) >= trips.get(p["id"], 0)
                                       and km(p["lat"], p["lon"], c["lat"], c["lon"]) <= TOWN_IN_CITY_KM for c in cities):
            is_base[p["id"]] = False
    base = {p["id"]: {**p, "score": trips.get(p["id"], 0), "sights": []} for p in places if is_base[p["id"]]}
    for p in places:
        if is_base[p["id"]]:
            continue
        near = [(km(p["lat"], p["lon"], b["lat"], b["lon"]), b) for b in base.values()]
        near = [x for x in near if x[0] <= SIGHT_RADIUS_KM]
        same = [x for x in near if x[1]["country"] == p["country"]] or near
        if same:
            b = min(same, key=lambda x: x[0])[1]
            b["score"] += trips.get(p["id"], 0)
            b["sights"].append((trips.get(p["id"], 0), p["name"]))
        else:  # far from any town: a place of its own (a remote park, a glacier camp)
            base[p["id"]] = {**p, "score": trips.get(p["id"], 0), "sights": []}
    out = sorted(base.values(), key=lambda b: (-b["score"], b["name"]))
    for b in out:
        b["sights"] = [n for _, n in sorted(b["sights"], key=lambda s: -s[0])]
    keep = [b for b in out if b["score"] > 0] or out[:12]
    return keep


def _base_of(bs: list[dict], lat: float, lon: float) -> dict | None:
    """The town a route stop belongs to: the town itself, or the town a sight is seen from
    (a route that stops at the Perito Moreno glacier is in El Calafate)."""
    b = _nearest(bs, lat, lon, 40)
    if b:
        return b
    from app import globe
    p = min(((km(lat, lon, q["lat"], q["lon"]), q) for q in globe.by_id().values()
             if abs(q["lat"] - lat) < 0.3 and abs(q["lon"] - lon) < 0.5), key=lambda x: x[0], default=(None, None))[1]
    if p is None:
        return None
    return next((b for b in bs if p["name"] in b["sights"] or b["id"] == p["id"]), None)


def _nearest(b_list: list[dict], lat: float, lon: float, max_km: float = 40) -> dict | None:
    near = [(km(lat, lon, b["lat"], b["lon"]), b) for b in b_list]
    near = [x for x in near if x[0] <= max_km]
    return min(near, key=lambda x: x[0])[1] if near else None


def _route_share(r: dict, a: dict, only: list[str]) -> float:
    tot = sum(s["days"] for s in r["stops"]) or 1
    return sum(s["days"] for s in r["stops"] if inside(a, s["lat"], s["lon"], s["country"], only)) / tot


@lru_cache
def _routes():
    from app.globe import routes as globe_routes
    return globe_routes.routes()


def area_routes(a: dict, only: list[str]) -> list[dict]:
    return [r for r in _routes() if _route_share(r, a, only) >= ROUTE_SHARE]


def typical_days(b: dict, routes: list[dict], all_bases: list[dict]) -> int:
    """What the organised routes give this place, a hand-written itinerary counting double."""
    got, weight = 0.0, 0.0
    for r in routes:
        d = sum(s["days"] for s in r["stops"]
                if (_base_of(all_bases, s["lat"], s["lon"]) or {}).get("id") == b["id"])
        if d:
            w = 2.0 if r.get("guide") else 1.0
            got += d * w
            weight += w
    if weight:
        return max(1, min(MAX_STOP_DAYS, int(got / weight + 0.5)))
    return DEFAULT_DAYS.get(b["kind"], 2)


# ---------------------------------------------------------------- the proposal

def _stop_of_base(b: dict, days: int) -> dict:
    return {"key": b["id"], "place_id": b["id"], "name": b["name"], "country": b["country"],
            "lat": b["lat"], "lon": b["lon"], "kind": b["kind"], "days": days,
            "elevation_m": None, "activities": None, "sights": b["sights"][:4]}


def _cost(order: list[dict]) -> float:
    return sum(km(a["lat"], a["lon"], b["lat"], b["lon"]) for a, b in zip(order, order[1:]))


def _insert(stops: list[dict], s: dict, keep_first: bool) -> None:
    """Where adding this place costs the least road."""
    best, at = math.inf, len(stops)
    for i in range(1 if keep_first and stops else 0, len(stops) + 1):
        c = _cost(stops[:i] + [s] + stops[i:])
        if c < best:
            best, at = c, i
    stops.insert(at, s)


def propose(a: dict, only: list[str] | None = None, days: int | None = None,
            month: int | None = None, keep: list[str] | None = None, drop: list[str] | None = None,
            last: list[str] | None = None) -> dict:
    """A route through the area that fits the days: {stops, more, route, best_months, days}.
    `last`: places the traveller wants to end with ("e alla fine Ushuaia"), kept and moved last."""
    keep = list(dict.fromkeys([*(keep or []), *(last or [])]))
    only = only or list(a["countries"])
    drop = set(drop or [])
    bs = bases(a, only)
    if not bs:
        return {"stops": [], "more": [], "route": None, "best_months": [], "days": days or 0}
    rank = {b["id"]: i for i, b in enumerate(bs)}
    by_id = {b["id"]: b for b in bs}
    routes = area_routes(a, only)
    tdays = {b["id"]: typical_days(b, routes, bs) for b in bs[:40]}
    best_months = sorted({m for r in routes[:6] for m in r.get("best_months") or []})
    if month:
        fit = [r for r in routes if month in (r.get("best_months") or [])]
        routes = fit or routes
    want = days
    route = None
    if routes:
        target = want or 14
        route = min(routes, key=lambda r: (abs(r["days"] - target) / target - (0.15 if r.get("guide") else 0),
                                           -_route_share(r, a, only)))
        if want and abs(route["days"] - want) > max(4, want * 0.6):
            route = None  # nothing like the days asked: build from the places instead
    stops: list[dict] = []
    if route:
        for j, s in enumerate(route["stops"]):
            b = _base_of(bs, s["lat"], s["lon"])
            if not b:
                continue  # outside the area: "Patagonia" is not 3 days in Buenos Aires (Manu, 2026-11-12)
            key = b["id"] if b else f"r-{norm(s['name'])}"
            if key in drop:
                continue
            same = next((x for x in stops if x["key"] == key), None)
            if same:  # back through the same town (out to the glacier and back): one stop
                same["days"] += s["days"]
                continue
            stops.append({"key": key, "place_id": b["id"] if b else None,
                          "name": b["name"] if b and b["kind"] in BASE_KINDS else s["name"],
                          "country": s["country"], "lat": s["lat"], "lon": s["lon"], "kind": s["kind"],
                          "days": s["days"], "elevation_m": s.get("elevation_m"),
                          "activities": s.get("activities"),
                          "sights": (b["sights"][:4] if b else [n for _, ns in s["visits"] for n in ns][:4])})
        # a hand-made route knows its days; a summary route gives 1 day everywhere: use ours
        if not route.get("guide"):
            for s in stops:
                if s["place_id"] in tdays:
                    s["days"] = max(s["days"], tdays[s["place_id"]])
    for k in keep or []:
        if k in by_id and not any(s["key"] == k for s in stops):
            _insert(stops, _stop_of_base(by_id[k], tdays.get(k, 2)), keep_first=bool(route))
    if not stops:
        first = next((b for b in bs if b["id"] not in drop), None)
        if first:
            stops.append(_stop_of_base(first, tdays.get(first["id"], 2)))
    want = want or sum(s["days"] for s in stops)

    def total() -> int:
        return sum(s["days"] for s in stops)

    # fill: the next places by importance while they fit
    for b in bs[:40]:
        if total() >= want:
            break
        if b["id"] in drop or any(s["key"] == b["id"] for s in stops):
            continue
        if any(km(b["lat"], b["lon"], s["lat"], s["lon"]) <= CLUSTER_KM for s in stops):
            continue  # Trelew next to Puerto Madryn: the same corner, already in
        if stops and want - total() < FAR_DAYS and min(km(b["lat"], b["lon"], s["lat"], s["lon"]) for s in stops) > FAR_KM:
            continue  # 2 days left are not worth a flight to Valdés: they go to the places already in
        d = tdays.get(b["id"], 2)
        if total() + d <= want + 1 or total() + 1 <= want:
            _insert(stops, _stop_of_base(b, min(d, max(1, want - total()))), keep_first=bool(route))
    # trim: the least important first, never what the traveller kept
    keep_set = set(keep or [])
    while total() > want and len(stops) > 1:
        extra = total() - want
        big = max(stops, key=lambda s: s["days"])
        if big["days"] > 2 and extra > 0:
            big["days"] -= 1
            continue
        cand = [s for s in stops if s["key"] not in keep_set]
        if not cand:
            break
        worst = max(cand, key=lambda s: rank.get(s["place_id"] or "", 999))
        if total() - worst["days"] < want - 1 and worst["days"] > 1:
            worst["days"] -= 1
            continue
        stops.remove(worst)
    # spread what is left over on the most important places
    i = 0
    order = sorted(stops, key=lambda s: rank.get(s["place_id"] or "", 999))
    while total() < want and order and i < 200:
        s = order[i % len(order)]
        if s["days"] < MAX_STOP_DAYS:
            s["days"] += 1
        i += 1
    for k in last or []:
        end = next((s for s in stops if s["key"] == k), None)
        if end:
            stops.remove(end)
            stops.append(end)
    taken = {s["key"] for s in stops}
    more = [{**_stop_of_base(b, tdays.get(b["id"], 2))} for b in bs[:30]
            if b["id"] not in taken][:10]
    return {"stops": stops, "more": more, "route": route["title"] if route else None,
            "best_months": best_months, "days": total()}


def start_for(month: int | None, best: list[int], today: date | None = None) -> date:
    from app.globe.routes import start_in
    return start_in([month] if month else best, today)


# ---------------------------------------------------------------- no place yet: ideas

def ideas(month: int | None, days: int | None, wishes: list[str], limit: int = 6) -> list[dict]:
    """Routes that fit a wish ("somewhere warm in February, by the sea"): good weather that
    month (climate normals), the wish, and about the length asked. One per country set."""
    from app.globe.routes import GOOD
    out = []
    for r in _routes():
        ms = r.get("months")
        mo = ms[month - 1] if ms and month else None
        if month and (not mo or (mo["level"] != GOOD and "snow" not in wishes)):
            continue  # good weather that month (snow trips are "cold" by definition)
        stops = r["stops"]
        tot = sum(s["days"] for s in stops) or 1
        share = lambda pred: sum(s["days"] for s in stops if pred(s)) / tot  # noqa: E731
        score = 0.0
        why = []
        if "warm" in wishes:
            if not mo or mo["hi"] < 26:
                continue
            score += 1
            why.append(f"up to {mo['hi']} °C")
        if "snow" in wishes:
            if not mo or mo["hi"] > 5:  # every stop cold all day: snow
                continue
            score += 1
            why.append(f"{mo['lo']} to {mo['hi']} °C")
        if "beach" in wishes:
            sea = share(lambda s: s["kind"] == "island")
            if sea < 0.2:
                continue
            score += sea
        if "mountains" in wishes:
            high = share(lambda s: (s.get("elevation_m") or 0) >= 1200 or s["kind"] == "nature")
            if high < 0.3:
                continue
            score += high
        if "city" in wishes:
            score += share(lambda s: s["kind"] == "city")
        if days:
            score -= abs(r["days"] - days) / max(days, 1)
        if r.get("guide"):
            score += 0.3
        if mo and not why:
            why.append(f"{mo['lo']}–{mo['hi']} °C")
        out.append((score, r, ", ".join(why)))
    out.sort(key=lambda x: -x[0])
    seen, res = set(), []
    for _, r, why in out:
        k = tuple(sorted(r["countries"]))
        if k in seen:
            continue
        seen.add(k)
        res.append({"id": r["id"], "title": r["title"], "days": r["days"], "countries": r["countries"],
                    "weather": why, "guide": r.get("guide")})
        if len(res) >= limit:
            break
    return res
