"""Build backend/app/globe/routes.json: the routes drawn on the home globe.

For every country (or pair of countries) and trip length we look at the organised trips we
read (the inventory manifest, day by day) and keep the shapes most of them share. A route is a
real trip, the one closest to all the others of its group (the "medoid"), reduced to where you
sleep each night plus what you visit each day. Only shapes followed by several trips from at
least two different operators are kept, so one operator's odd tour never becomes a route.

Usage:
    python tools/globe/build_routes.py manifest.json [--places backend/app/globe/places.json]
        [--out backend/app/globe/routes.json] [--elevations tools/globe/elevations.json]

Needs network once per new place: elevations come from the Open-Meteo elevation API (free, no
key) and are cached in --elevations, so a rebuild reads them from disk.
"""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# trip length (days) -> bucket shown on the globe
BUCKETS = [("1w", 5, 8), ("10d", 9, 12), ("2w", 13, 17), ("3w", 18, 25)]
MIN_TRIPS = 4          # trips sharing the shape
MIN_OPERATORS = 2      # ... from at least this many operators
SAME_SHAPE = 0.3       # Jaccard of the places you sleep in: same shape from here up
DISTINCT = 0.45        # two routes of one group must overlap less than this
MAX_PER_GROUP = 3
MERGE_KM = 25          # two stops closer than this are one stop
BASE_KINDS = ("city", "town")
OUTDOORS = ("nature", "island", "region")  # a day out there may be a hike: we dress for it


def km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def bucket_of(days: int) -> str | None:
    return next((b for b, lo, hi in BUCKETS if lo <= days <= hi), None)


def jaccard(a: set, b: set) -> float:
    return len(a & b) / max(1, len(a | b))


class Builder:
    def __init__(self, manifest: dict, places: dict[str, dict]):
        self.trips = manifest["trips"]
        self.info = manifest["places"]          # popularity + kind of every place read
        self.places = places                    # verified places (coordinates in their country)

    def pop(self, pid: str) -> int:
        return self.info.get(pid, {}).get("trips", 0)

    def shape(self, trip: dict):
        """(length, covered days, stops): where you sleep, merged, and what you see each day."""
        days = sorted((d for d in trip["days"] if d.get("places")), key=lambda d: d["day"])
        if not days:
            return None
        length = max(d["day"] for d in trip["days"])
        per_day = []
        for d in days:
            ps = [p for p in d["places"] if p in self.places]
            if not ps:
                continue
            good = [p for p in ps if self.pop(p) >= 8 and self.places[p]["kind"] in BASE_KINDS] \
                or [p for p in ps if self.pop(p) >= 8] or ps
            per_day.append((d["day"], good[-1], [p for p in ps if p != good[-1]]))
        if len(per_day) < 2:
            return None
        stops: list[dict] = []
        for day, base, seen in per_day:
            here = self.places[base]
            last = stops[-1] if stops else None
            if last and (last["id"] == base or km((last["lat"], last["lon"]), (here["lat"], here["lon"])) < MERGE_KM):
                last["seen"].append((day, seen + ([base] if base != last["id"] else [])))
                continue
            stop = {"id": base, "lat": here["lat"], "lon": here["lon"], "first": day, "seen": []}
            # a travel day: what you see on the way belongs to the stop it is closer to
            mine, theirs = [], []
            for pid in seen:
                q = self.places[pid]
                d_new = km((q["lat"], q["lon"]), (here["lat"], here["lon"]))
                d_old = km((q["lat"], q["lon"]), (last["lat"], last["lon"])) if last else 1e9
                (theirs if d_old < d_new else mine).append(pid)
            if theirs:
                last["seen"].append((day - 1, theirs))
            stop["seen"].append((day, mine))
            stops.append(stop)
        if len(stops) < 2:
            return None
        # days: from the day you reach a stop to the day you reach the next one
        stops[0]["first"] = 1
        for i, st in enumerate(stops):
            end = stops[i + 1]["first"] if i + 1 < len(stops) else length + 1
            st["days"] = max(1, end - st["first"])
        return length, len({d for d, _, _ in per_day}), stops

    def tidy(self, length: int, covered: int, stops: list[dict]) -> bool:
        """Good enough to show as a route: most days known, starts in a town, no back and forth."""
        if covered < 0.7 * length:
            return False
        if self.places[stops[0]["id"]]["kind"] not in BASE_KINDS:
            return False
        ids = [st["id"] for st in stops]
        counts = Counter(ids)
        if max(counts.values()) > 2 or sum(1 for c in counts.values() if c > 1) > 1:
            return False
        # a place you come back to is fine only as a hub (Cusco, Reykjavik) or the way home
        for pid, c in counts.items():
            if c == 2 and ids[0] != pid and ids[-1] != pid and len(ids) - ids[::-1].index(pid) - 1 - ids.index(pid) < 2:
                return False
        # no spikes: a one-day hop far away and straight back, or a last stop far from the rest
        pts = [(st["lat"], st["lon"]) for st in stops]
        for i in range(1, len(pts) - 1):
            if km(pts[i - 1], pts[i]) + km(pts[i], pts[i + 1]) > 3 * km(pts[i - 1], pts[i + 1]) + 800:
                return False
        if stops[-1]["days"] == 1 and km(pts[-2], pts[-1]) > 1200:
            return False
        # a temple or a cave is something you see, not where you sleep
        if sum(1 for st in stops if self.places[st["id"]]["kind"] == "landmark") > 1:
            return False
        return all(st["days"] <= max(5, length // 2) for st in stops)

    def build(self) -> list[dict]:
        groups: dict[tuple, list] = defaultdict(list)
        for t in self.trips:
            sh = self.shape(t)
            if not sh:
                continue
            length, covered, stops = sh
            b = bucket_of(length)
            if not b:
                continue
            cs = tuple(sorted({self.places[st["id"]]["country"] for st in stops}))
            if len(cs) > 3:
                continue
            groups[(cs, b)].append({"trip": t, "length": length, "stops": stops,
                                    "set": {st["id"] for st in stops},
                                    "ok": self.tidy(length, covered, stops)})
        routes = []
        for (cs, b), items in groups.items():
            left = list(items)
            picked: list[dict] = []
            while len(left) >= MIN_TRIPS and len(picked) < MAX_PER_GROUP:
                cands = [x for x in left if x["ok"]]
                if not cands:
                    break
                m = max(cands, key=lambda x: sum(jaccard(x["set"], y["set"]) for y in left))
                cluster = [x for x in left if jaccard(m["set"], x["set"]) >= SAME_SHAPE]
                left = [x for x in left if x not in cluster]
                ops = {x["trip"]["source"] for x in cluster}
                if len(cluster) < MIN_TRIPS or len(ops) < MIN_OPERATORS:
                    continue
                if any(jaccard(m["set"], p["set"]) >= DISTINCT for p in picked):
                    continue
                picked.append({**m, "support": len(cluster)})
            for p in picked:
                routes.append(self.route(cs, b, p))
        routes.sort(key=lambda r: -r["_support"])
        # same title in the same countries (three "Lima, Cusco and Machu Picchu"): the longer
        # ones name one more place they have and the shorter ones don't
        by_title = defaultdict(list)
        for r in routes:
            by_title[(tuple(r["countries"]), r["title"])].append(r)
        for twins in by_title.values():
            for r in sorted(twins, key=lambda r: r["days"])[1:]:
                extra = [n for n in sorted(r["_names"], key=lambda n: -r["_names"][n][1]) if n not in r["_top"]]
                if extra:
                    top = sorted(r["_top"] + extra[:1], key=lambda n: r["_names"][n][0])
                    r["title"] = ", ".join(top[:-1]) + " and " + top[-1]
        for r in routes:
            del r["_names"], r["_top"]
        # stable ids: country codes + bucket + rank in the group
        rank: Counter = Counter()
        for r in routes:
            key = "-".join(c.lower() for c in r["countries"]) + "-" + r["bucket"]
            rank[key] += 1
            r["id"] = f"{key}-{rank[key]}"
        return routes

    def route(self, cs, b, m) -> dict:
        stops = []
        for s in m["stops"]:
            p = self.places[s["id"]]
            plan = []
            for day, seen in s["seen"]:
                names = []
                for pid in seen:
                    n = self.places[pid]["name"] if pid in self.places else None
                    if n and n not in names and n != p["name"]:
                        names.append(n)
                d = day - s["first"] + 1
                if plan and plan[-1][0] == d:
                    plan[-1][1].extend(n for n in names if n not in plan[-1][1])
                else:
                    plan.append([d, names])
            outdoors = any(self.places[pid]["kind"] in OUTDOORS for _, ps in s["seen"] for pid in ps if pid in self.places)
            stops.append({"place": s["id"], "name": p["name"], "country": p["country"], "kind": p["kind"],
                          "outdoors": outdoors,
                          "lat": p["lat"], "lon": p["lon"], "days": s["days"],
                          "visits": [[d, n[:5]] for d, n in plan if n and 1 <= d <= s["days"]]})
        # title: the three best-known places you sleep in, in route order; a small town gives
        # way to the famous sight you go there for (Aguas Calientes -> Machu Picchu)
        names: dict[str, tuple[int, int]] = {}
        for i, st in enumerate(m["stops"]):
            pid, pop = st["id"], self.pop(st["id"])
            if self.places[pid]["kind"] != "city":
                here = self.places[pid]
                best = max((q for _, ps in st["seen"] for q in ps if q in self.places
                            and self.places[q]["kind"] not in BASE_KINDS
                            and km((here["lat"], here["lon"]), (self.places[q]["lat"], self.places[q]["lon"])) < 60),
                           key=self.pop, default=None)
                if best and self.pop(best) > pop:
                    pid, pop = best, self.pop(best)
            names.setdefault(self.places[pid]["name"], (i, pop, self.places[pid]["country"]))
        # every country of the route gets its best-known place, then the most visited fill in
        ranked = sorted(names, key=lambda n: -names[n][1])
        top = [next(n for n in ranked if names[n][2] == c) for c in cs if any(names[n][2] == c for n in ranked)]
        top += [n for n in ranked if n not in top][:max(0, 3 - len(top))]
        top = sorted(top, key=lambda n: names[n][0])
        title = ", ".join(top[:-1]) + " and " + top[-1] if len(top) > 1 else top[0]
        return {"countries": list(cs), "bucket": b, "days": sum(s["days"] for s in stops),
                "title": title, "stops": stops, "_support": m["support"], "_names": names, "_top": top}


def elevations(points: list[tuple[float, float]], cache_file: Path) -> dict[str, float]:
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    keys = [f"{la:.3f},{lo:.3f}" for la, lo in points]
    todo = sorted({k for k in keys if k not in cache})
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        lat = ",".join(k.split(",")[0] for k in chunk)
        lon = ",".join(k.split(",")[1] for k in chunk)
        url = f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    got = json.load(r)["elevation"]
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
        for k, e in zip(chunk, got):
            cache[k] = max(0.0, float(e))
        cache_file.write_text(json.dumps(cache, sort_keys=True, indent=0))  # a cut run resumes here
        time.sleep(0.5)
    return cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--places", default=str(ROOT / "backend/app/globe/places.json"))
    ap.add_argument("--out", default=str(ROOT / "backend/app/globe/routes.json"))
    ap.add_argument("--elevations", default=str(ROOT / "tools/globe/elevations.json"))
    a = ap.parse_args()
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    pj = json.loads(Path(a.places).read_text(encoding="utf-8"))
    places = {row[0]: dict(zip(pj["fields"], row)) for row in pj["places"]}
    routes = Builder(manifest, places).build()
    elev = elevations([(s["lat"], s["lon"]) for r in routes for s in r["stops"]], Path(a.elevations))
    for r in routes:
        for s in r["stops"]:
            s["elevation_m"] = round(elev[f"{s['lat']:.3f},{s['lon']:.3f}"])
        del r["_support"]
    out = {"_doc": "Routes for the home globe: for each country and trip length, the shapes most of the "
                   "organised trips we read share (one real trip per shape, reduced to where you sleep and "
                   "what you see each day). Built by tools/globe/build_routes.py; do not edit by hand.",
           "routes": routes}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    by = Counter(r["bucket"] for r in routes)
    print(f"{len(routes)} routes in {len({c for r in routes for c in r['countries']})} countries: {dict(by)}")


if __name__ == "__main__":
    main()
