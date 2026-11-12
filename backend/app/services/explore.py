"""From "Patagonia, three weeks in January" to a route you can change (Manu, 2026-11-12).

A trip is often a region, not a place: "Patagonia" is El Calafate, El Chaltén, Torres del
Paine, Ushuaia... Nothing here is invented:

- the region is hand-written geography (app/guide/regions.json) or a whole country;
- the places come from the globe (app.globe), grouped around the towns you sleep in: the
  Perito Moreno glacier and Lago Argentino are seen from El Calafate;
- the route merges the organised trips that go through the area (app.guide.patterns, built
  from the inventory by tools/guide/build_patterns.py): the places most trips of about this
  length sleep in, the days they give them, the order most of them follow, and for each stop
  the days out they take from it, several sights a day (Manu, 2026-11-12: "the trips you
  propose are random"). No single tour is copied;
- the counts stay on the server: the traveller sees an order, never a number;
- an area with too few organised trips falls back to one read route filled with the most
  visited places.
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


def _propose_from_route(a: dict, only: list[str] | None = None, days: int | None = None,
                        month: int | None = None, keep: list[str] | None = None, drop: list[str] | None = None,
                        last: list[str] | None = None) -> dict:
    """The old way, for areas with too few organised trips to merge: one read route as the
    backbone, filled with the most visited places."""
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


# ---------------------------------------------------------------- the proposal: merged organised trips

MIN_AREA_TRIPS = 4      # fewer organised trips than this in an area: the old way
START_KM = 500          # starting where few trips start costs as much as this much road
HOP_KM = 60             # each move costs at least this much: fewer, longer stays
FOLLOW = 0.85           # a move most trips make costs this much less road
IN_TOWN_KM = 15         # sights this close to where you sleep can share a day
DAY_MAX = 4             # things in one day at most, when they are close together
NEW_PLACE = 0.8         # a day somewhere new is worth a bit less: you spend part of it moving
DETOUR_KM = 300         # a move trips with both places never make costs this much more
SAME_PLACE_KM = 25       # a place to sleep this close to one chosen is the same stop
NEAR_BASE_KM = 40        # a town this close to a stop is a day out from it
FEW = 1.0               # a move one or two trips make is not yet "what trips do"
BRIDGE_KM = 150         # two stops this far apart that no trip joins directly need a night between
FLY_KM = 500            # farther than this you fly
RING_SHARE = 0.3        # trips that come back to where they started, from this share up
EXACT_ORDER_MAX = 11    # up to this many places the best order is searched exactly


def _area_trips(a: dict, only: list[str]) -> list[tuple[str, int, list[tuple[str, int]]]]:
    """The organised trips that go through the area, cut to what they do inside it:
    (operator, days inside, [(place, days)])."""
    from app import globe
    from app.guide import patterns
    P = globe.by_id()
    out = []
    for t in patterns.trips():
        tot = sum(d for _, d in t.stays) or 1
        inn: list[tuple[str, int]] = []
        for pid, d in t.stays:
            p = P.get(pid)
            if not p or not inside(a, p["lat"], p["lon"], p["country"], only):
                continue
            if inn and inn[-1][0] == pid:
                inn[-1] = (pid, inn[-1][1] + d)
            else:
                inn.append((pid, d))
        days = sum(d for _, d in inn)
        if len({p for p, _ in inn}) < 2 or days < 3:
            continue  # one town only: an extension, it says nothing about a route
        if days / tot < 0.5 and days < 6:
            continue  # a few days of a much longer trip elsewhere
        out.append((t.operator, days, inn))
    return out


class _Merge:
    """The trips of an area weighted by how close their length is to the days asked, each
    operator counting about as much as the others (a hundred variants of one operator's tour
    are still one way of doing it)."""

    def __init__(self, trips: list, target: int):
        from collections import Counter
        per_op = Counter(o for o, _, _ in trips)
        self.recs = []
        for o, n, stays in trips:
            w = math.exp(-((n - target) / (0.25 * target + 2)) ** 2) / math.sqrt(per_op[o])
            days: dict[str, int] = {}
            for pid, d in stays:
                days[pid] = days.get(pid, 0) + d
            self.recs.append({"w": max(w, 1e-4), "days": days, "seq": [pid for pid, _ in stays]})
        self.places = sorted({p for r in self.recs for p in r["days"]})
        self.imp = {p: sum(r["w"] for r in self.recs if p in r["days"]) for p in self.places}

    def typical(self, p: str) -> int:
        """The days trips like this one give a place (weighted median)."""
        xs = sorted((r["days"][p], r["w"]) for r in self.recs if p in r["days"])
        if not xs:
            return 2
        half, acc = sum(w for _, w in xs) / 2, 0.0
        for d, w in xs:
            acc += w
            if acc >= half:
                return max(1, min(MAX_STOP_DAYS, d))
        return xs[-1][0]

    def value(self, p: str, nth_day: int, chosen: list[str]) -> float:
        """How many (weighted) trips like this one, and like the places already chosen, give the
        place at least this many days."""
        v = 0.0
        for r in self.recs:
            d = r["days"].get(p, 0)
            if d >= nth_day:
                share = (1 + sum(1 for c in chosen if c in r["days"])) / (1 + len(chosen))
                v += r["w"] * share
        return v

    def hub(self, chosen: list[str]) -> tuple[str | None, float]:
        """Where trips like this start, and how often they come back there at the end (Reykjavik,
        Lima, Buenos Aires: the flights home leave from there)."""
        firsts: dict[str, float] = {}
        for r in self.recs:
            seq = [p for p in r["seq"] if p in chosen]
            if seq:
                firsts[seq[0]] = firsts.get(seq[0], 0) + r["w"]
        if not firsts:
            return None, 0.0
        h = max(firsts, key=firsts.get)
        back = sum(r["w"] for r in self.recs if r["seq"] and r["seq"][0] == h and r["seq"][-1] == h)
        start = sum(r["w"] for r in self.recs if r["seq"] and r["seq"][0] == h)
        return h, back / start if start else 0.0

    def order(self, chosen: list[str], end: str | None, ring: str | None = None) -> list[str]:
        """The order most trips follow, with as little road as possible. ring: the trip starts
        there and comes back to it, so it should end close to it."""
        from app import globe
        P = globe.by_id()
        n = len(chosen)
        if n <= 2 and not end and not ring:
            return self._two(chosen)
        idx = {p: i for i, p in enumerate(chosen)}
        move = [[0.0] * n for _ in range(n)]
        both = [[0.0] * n for _ in range(n)]
        first, lastw, pres = [0.0] * n, [0.0] * n, [0.0] * n
        for r in self.recs:
            seq = [p for p in r["seq"] if p in idx]
            if not seq:
                continue
            ids = {idx[p] for p in seq}
            for i in ids:
                pres[i] += r["w"]
                for j in ids:
                    both[i][j] += r["w"]
            first[idx[seq[0]]] += r["w"]
            lastw[idx[seq[-1]]] += r["w"]
            for x, y in zip(seq, seq[1:]):
                if x != y:
                    move[idx[x]][idx[y]] += r["w"]

        def km_(i: int, j: int) -> float:
            """Road, or a flight: past FLY_KM a longer flight costs little more."""
            a, b = P[chosen[i]], P[chosen[j]]
            d = km(a["lat"], a["lon"], b["lat"], b["lon"])
            return d if d <= FLY_KM else FLY_KM + (d - FLY_KM) * 0.3

        cost = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    # most trips go this way (half as much if they go the other way round)
                    follow = min(1.0, (move[i][j] + 0.5 * move[j][i]) / (both[i][j] + FEW))
                    cost[i][j] = HOP_KM + km_(i, j) * (1 - FOLLOW * follow) + DETOUR_KM * (1 - follow)
        start = [START_KM * (1 - (first[i] / pres[i] if pres[i] else 0)) for i in range(n)]
        stop = [START_KM / 2 * (1 - (lastw[i] / pres[i] if pres[i] else 0)) for i in range(n)]
        if end in idx:
            stop = [0.0 if i == idx[end] else math.inf for i in range(n)]
        elif ring in idx:
            h = idx[ring]
            start = [0.0 if i == h else math.inf for i in range(n)]
            stop = [km_(i, h) * 0.7 if i != h else 0.0 for i in range(n)]
        if n <= EXACT_ORDER_MAX:
            best = self._exact(n, cost, start, stop)
        else:
            best = self._greedy(n, cost, start, stop)
        return [chosen[i] for i in best]

    def direct(self, a: str, b: str) -> float:
        """How often trips with both places go straight from one to the other (either way)."""
        mv = both = 0.0
        for r in self.recs:
            if a in r["days"] and b in r["days"]:
                both += r["w"]
                seq = r["seq"]
                if any({x, y} == {a, b} for x, y in zip(seq, seq[1:])):
                    mv += r["w"]
        return mv / (both + FEW)

    def bridge(self, a: str, b: str, skip: set[str]) -> str | None:
        """The place trips sleep in between two places they never go straight between (Höfn
        between Vík and the north of Iceland)."""
        got: dict[str, float] = {}
        for r in self.recs:
            seq = r["seq"]
            for x, c, y in zip(seq, seq[1:], seq[2:]):
                if {x, y} == {a, b} and c not in skip:
                    got[c] = got.get(c, 0) + r["w"]
        return max(got, key=got.get) if got else None

    def _two(self, chosen: list[str]) -> list[str]:
        if len(chosen) < 2:
            return list(chosen)
        a, b = chosen
        ab = sum(r["w"] for r in self.recs if a in r["seq"] and b in r["seq"] and r["seq"].index(a) < r["seq"].index(b))
        ba = sum(r["w"] for r in self.recs if a in r["seq"] and b in r["seq"] and r["seq"].index(b) < r["seq"].index(a))
        return [a, b] if ab >= ba else [b, a]

    @staticmethod
    def _exact(n: int, cost, start, stop) -> list[int]:
        full = (1 << n) - 1
        dp = [[math.inf] * n for _ in range(1 << n)]
        back = [[-1] * n for _ in range(1 << n)]
        for i in range(n):
            dp[1 << i][i] = start[i]
        for mask in range(1, 1 << n):
            row = dp[mask]
            for j in range(n):
                c = row[j]
                if c == math.inf:
                    continue
                for k in range(n):
                    if mask & (1 << k):
                        continue
                    m2 = mask | (1 << k)
                    v = c + cost[j][k]
                    if v < dp[m2][k]:
                        dp[m2][k] = v
                        back[m2][k] = j
        j = min(range(n), key=lambda i: dp[full][i] + stop[i])
        out, mask = [], full
        while j != -1:
            out.append(j)
            j, mask = back[mask][j], mask & ~(1 << j)
        return out[::-1]

    @staticmethod
    def _greedy(n: int, cost, start, stop) -> list[int]:
        cur = min(range(n), key=lambda i: start[i])
        out, left = [cur], set(range(n)) - {cur}
        while left:
            cur = min(left, key=lambda k: cost[out[-1]][k])
            out.append(cur)
            left.remove(cur)
        if stop[out[-1]] == math.inf:  # the place to end with goes last
            e = next(i for i in range(n) if stop[i] == 0.0)
            out.remove(e)
            out.append(e)
        return out


def _anchor(pid: str, cands: list[str]) -> str | None:
    """The place to sleep that a kept place stands for: itself, the same place under another
    name, or the town a sight is seen from (Perito Moreno is El Calafate)."""
    from app import globe
    from app.guide import patterns
    if pid in cands:
        return pid
    P = globe.by_id()
    p = P.get(pid)
    if not p:
        return None
    near = sorted((km(p["lat"], p["lon"], P[c]["lat"], P[c]["lon"]), c) for c in cands if c in P)
    if near and near[0][0] <= 5:
        return near[0][1]
    outs = patterns.outings()
    from_ = [c for c in cands if any(pid in g for g, _, _ in outs.get(c, ()))]
    if from_:
        return min(from_, key=lambda c: km(p["lat"], p["lon"], P[c]["lat"], P[c]["lon"]))
    if p["kind"] not in BASE_KINDS and near and near[0][0] <= 40:
        return near[0][1]
    return None


def _days_of(stops: list[dict]) -> None:
    """What to do each day at each stop, from what organised trips do there: the days out they
    take from it (several sights in one day when trips see them together), what they see on the
    way in. Each sight once, with the stop it is closest to."""
    from app import globe
    from app.guide import patterns
    P = globe.by_id()
    outs, way = patterns.outings(), patterns.way()
    used: set[str] = {s["place_id"] for s in stops if s.get("place_id")}

    # a sight goes with the stop trips see it from most (Perito Moreno is El Calafate, even if
    # Torres del Paine is closer as the crow flies); one no trip names goes with the closest stop
    from_stop: dict[str, tuple[float, int]] = {}
    for k, o in enumerate(stops):
        mine = outs.get(o.get("place_id"), ())
        top = max((w for _, w, _ in mine), default=1) or 1
        for g, w, _ in mine:
            w = w / top  # how much of what trips do there
            for x in g:
                q = P.get(x)
                if not q:
                    continue
                # trips that see it from there, the closer the better (Colca is Chivay's)
                v = w / (1 + km(q["lat"], q["lon"], o["lat"], o["lon"]) / 30) ** 2
                if v > from_stop.get(x, (0, -1))[0]:
                    from_stop[x] = (v, k)

    def closest_is(sid: str, s: dict) -> bool:
        q = P.get(sid)
        if not q:
            return False
        if sid in from_stop:
            return stops[from_stop[sid][1]] is s
        mine = km(q["lat"], q["lon"], s["lat"], s["lon"])
        return all(km(q["lat"], q["lon"], o["lat"], o["lon"]) >= mine - 5 for o in stops if o is not s)

    def in_town(sids: list[str], s: dict) -> bool:
        return all(km(P[x]["lat"], P[x]["lon"], s["lat"], s["lon"]) <= IN_TOWN_KM for x in sids)

    for i, s in enumerate(stops):
        b = s.get("place_id")
        groups: list[tuple[list[str], int]] = []
        # places to sleep close by that are not stops are seen from here (Purmamarca from Tilcara)
        near = [c for c in outs if c != b and c in P and c not in used
                and km(P[c]["lat"], P[c]["lon"], s["lat"], s["lon"]) <= NEAR_BASE_KM and closest_is(c, s)]
        sources = [(g, n) for g, _, n in outs.get(b, ())]
        for c in sorted(near, key=lambda c: -sum(w for _, w, _ in outs[c])):
            sources.append(((c,), 1))
            sources += [(g, n) for g, _, n in outs[c]]
        for g, n in sources:
            ids = [x for x in g if x not in used and x in P and closest_is(x, s)]
            if ids:
                used.update(ids)
                groups.append((ids, n))
        on_way: list[str] = []
        if i > 0 and b and stops[i - 1].get("place_id"):
            on_way = [x for x in way.get((stops[i - 1]["place_id"], b), ()) if x not in used and x in P]
            used.update(on_way)
        plan: list[dict] = []
        later: list[tuple[list[str], int]] = []
        d = 1
        while d <= s["days"]:
            if d == 1 and (i > 0 or s["days"] > 1):
                things = list(on_way)
                if s["days"] == 1:
                    while groups and groups[0][1] > 1:
                        later.append(groups.pop(0))
                    if groups:
                        things += groups.pop(0)[0]
                plan.append({"day": 1, "kind": "arrive", "sights": [P[x]["name"] for x in things]})
                d += 1
                continue
            # the next day out that fits the days left (a 3-day trek needs 3)
            while groups and groups[0][1] > s["days"] - d + 1:
                later.append(groups.pop(0))
            if not groups and later:  # a longer trip out done in the days there are
                g, n = later.pop(0)
                groups.append((g, min(n, s["days"] - d + 1)))
            if not groups:
                plan.append({"day": d, "kind": "free", "sights": []})
                d += 1
                continue
            things, n = groups.pop(0)
            if n > 1:
                name = P[things[0]]["name"]
                plan.append({"day": d, "kind": "day", "sights": [P[x]["name"] for x in things], "days": n})
                for k in range(1, n):
                    plan.append({"day": d + k, "kind": "more", "sights": [], "of": name})
                d += n
                continue
            # short visits in town share the day
            while groups and groups[0][1] == 1 and len(things) < DAY_MAX and in_town(things, s) \
                    and in_town(groups[0][0], s) and len(things) + len(groups[0][0]) <= DAY_MAX:
                things += groups.pop(0)[0]
            plan.append({"day": d, "kind": "day", "sights": [P[x]["name"] for x in things]})
            d += 1
        s["plan"] = plan
        extra = [P[x]["name"] for g, _ in later + groups for x in g]
        s["also"] = extra[:6]  # more days out from here, if you add a day
        s["sights"] = ([n for p in plan for n in p["sights"]] + extra)[:12]


def propose(a: dict, only: list[str] | None = None, days: int | None = None,
            month: int | None = None, keep: list[str] | None = None, drop: list[str] | None = None,
            last: list[str] | None = None) -> dict:
    """A route through the area that fits the days: {stops, more, route, best_months, days}.

    Made by merging the organised trips of the area (Manu, 2026-11-12: "not one trip copied,
    the places that matter, in a good order, several things a day"):
    - the places to sleep in, chosen a day at a time: each next day goes where most trips of
      about this length (and with the places already chosen) spend it, a new place or one more
      day somewhere already in;
    - in the order most trips follow, with the least road;
    - each stop with its days planned from what trips do there.
    `last`: places the traveller wants to end with ("e alla fine Ushuaia"), kept and moved last.
    """
    only = only or list(a["countries"])
    trips = _area_trips(a, only)
    if len(trips) < MIN_AREA_TRIPS:
        p = _propose_from_route(a, only, days, month, keep, drop, last)
        _days_of(p["stops"])
        return p
    from app import globe
    P = globe.by_id()
    if not days:
        lengths = sorted(n for _, n, _ in trips)
        days = max(5, min(21, lengths[len(lengths) // 2]))
    m = _Merge(trips, days)
    drop_set = set(drop or [])
    cands = [p for p in m.places if p in P and p not in drop_set]
    forced: list[str] = []
    extra_stops: dict[str, dict] = {}
    for k in [*(keep or []), *(last or [])]:
        b = _anchor(k, cands)
        if b is None and k in P and k not in drop_set:  # a place no trip sleeps in: the traveller wants it
            b = k
            extra_stops[k] = P[k]
        if b and b not in forced:
            forced.append(b)
    ends = [_anchor(k, cands) or k for k in (last or [])]
    end = ends[-1] if ends else None

    chosen: list[str] = []
    alloc: dict[str, int] = {}
    for b in forced:
        chosen.append(b)
        alloc[b] = m.typical(b) if b in m.imp else DEFAULT_DAYS.get(P[b]["kind"], 2)
    top = max(m.imp.values()) if m.imp else 1.0

    def total() -> int:
        return sum(alloc.values())

    while total() < days:
        left = days - total()
        best, pick = 0.0, None
        for b in chosen:
            if alloc[b] < MAX_STOP_DAYS and b in m.imp:
                v = m.value(b, alloc[b] + 1, chosen)
                if v > best:
                    best, pick = v, (b, False)
        for b in cands:
            if b in alloc or m.imp[b] < 0.04 * top:
                continue
            if any(km(P[b]["lat"], P[b]["lon"], P[c]["lat"], P[c]["lon"]) <= SAME_PLACE_KM for c in chosen):
                continue  # Iguazu Falls is Puerto Iguazú
            # a new place comes with the days trips give it (no one-night hops), and moving costs
            n = max(1, min(m.typical(b), left))
            v = NEW_PLACE * sum(m.value(b, k, chosen) for k in range(1, n + 1)) / n
            if v > best:
                best, pick = v, (b, True)
        if not pick or best < 1e-6:
            break
        b, new = pick
        if new:
            chosen.append(b)
            alloc[b] = max(1, min(m.typical(b), days - total()))
        else:
            alloc[b] += 1
    # days nobody spends anywhere else: more time where it matters most
    i = 0
    while total() < days and chosen and i < 200:
        b = sorted(chosen, key=lambda c: -m.imp.get(c, 0))[i % len(chosen)]
        if alloc[b] < MAX_STOP_DAYS:
            alloc[b] += 1
        i += 1
    # more than the days (the places kept take more): trim where trips spend the least
    while total() > days and len(chosen) > 1:
        many = [c for c in chosen if alloc[c] > 1]
        if many:
            c = min(many, key=lambda c: m.value(c, alloc[c], chosen) if c in m.imp else 0)
            alloc[c] -= 1
            continue
        free = [c for c in chosen if c not in forced] or [c for c in chosen if c != end]
        if not free:
            break
        c = min(free, key=lambda c: m.imp.get(c, 0))
        chosen.remove(c)
        del alloc[c]
    # two places trips never go straight between: add the night they spend in between
    order0 = m.order(chosen, end, None) if len(chosen) >= 2 else list(chosen)
    for x, y in list(zip(order0, order0[1:])):
        d_xy = km(P[x]["lat"], P[x]["lon"], P[y]["lat"], P[y]["lon"])
        if not BRIDGE_KM <= d_xy <= FLY_KM or m.direct(x, y) >= 0.15:  # farther: you fly
            continue
        c = m.bridge(x, y, set(chosen) | drop_set)
        donor = max(chosen, key=lambda k: alloc[k])
        if c and c in P and alloc[donor] >= 3:
            alloc[donor] -= 1
            chosen.append(c)
            alloc[c] = 1
    ring, back = (m.hub(chosen) if not end and len(chosen) >= 3 else (None, 0.0))
    ring = ring if back >= RING_SHARE and P[ring]["kind"] == "city" else None
    order = m.order(chosen, end, ring)
    stops = [{**_stop_of_base({**P[b], "sights": []}, alloc[b]), "key": b} for b in order]
    if ring and alloc[ring] >= 2 and stops[-1]["kind"] != "city" \
            and km(P[ring]["lat"], P[ring]["lon"], stops[-1]["lat"], stops[-1]["lon"]) > 120:
        # back where the flights leave from: the last night there
        stops[0]["days"] -= 1
        stops.append({**_stop_of_base({**P[ring], "sights": []}, 1), "key": f"{ring}~back"})
    _days_of(stops)
    taken = set(order)
    more = []
    for b in sorted(cands, key=lambda c: -m.imp[c]):
        if b in taken or any(km(P[b]["lat"], P[b]["lon"], P[c]["lat"], P[c]["lon"]) <= TOWN_IN_CITY_KM for c in taken):
            continue
        more.append(_stop_of_base({**P[b], "sights": []}, m.typical(b)))
        if len(more) >= 10:
            break
    _days_of(more)  # what you would do there, if you add it
    routes = area_routes(a, only)
    best_months = sorted({mo for r in routes[:6] for mo in r.get("best_months") or []})
    return {"stops": stops, "more": more, "route": None, "best_months": best_months, "days": total()}


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
