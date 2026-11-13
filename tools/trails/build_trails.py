"""Build the computed side of the trails (Manu, 2026-11-13): the line on the map, distance,
climb, the altitude profile and the time of every stretch between two key points.

Input:  backend/app/trails/data/<cc>/<trail id>.json  (written by hand, with sources)
Output: backend/app/trails/geo/<trail id>.json

Open data only (AllTrails, Komoot and co. are proprietary and are never copied):
- the path, first that applies: the OpenStreetMap hiking relation when it covers start and goal
  (Waymarked Trails API, ways in order); the OSM ways listed in `osm_ways`, in walking order; a
  shortest walk on all OSM paths of the area through the key points (local router, mountain
  paths included); for long trails the FOSSGIS OSRM foot router (it skips sac_scale paths).
- the altitude: Copernicus DEM 90 m through the Open-Meteo elevation API.
The numbers we compute are checked against the ones the park or the hut publishes ("published"
in the data): a difference over 30% is printed, and the page shows the published figures when
they disagree (a DEM undercounts the climb on short, steep zigzags).

Run from the repo root:  python tools/trails/build_trails.py [trail id ...]
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend/app/trails/data"
GEO = ROOT / "backend/app/trails/geo"
UA = {"User-Agent": "trail-builder/1.0 (open-data trail profiles)"}


def get(url: str, tries: int = 4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # network hiccups: retry with backoff
            if i == tries - 1:
                raise
            print(f"  retry {url[:80]}: {e}")
            time.sleep(2 * (i + 1))


def km(a, b) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, h)))


def merc(x: float, y: float) -> tuple[float, float]:
    lon = x / 6378137 * 180 / math.pi
    lat = (2 * math.atan(math.exp(y / 6378137)) - math.pi / 2) * 180 / math.pi
    return lat, lon


# ---------------------------------------------------------------- the path

def _ways(node, out):
    if node.get("route_type") == "base":
        coords = [merc(x, y) for x, y in node["geometry"]["coordinates"]]
        out.append(coords)
        return
    for k in ("main", "ways", "forward", "backward"):
        for sub in node.get(k) or []:
            _ways(sub, out)
            if k == "forward":  # a split: keep one direction
                break


def chain(ways: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    """Ways in route order into one line, flipping each so it starts where the last ended."""
    line: list[tuple[float, float]] = []
    for w in ways:
        if not line:
            line = list(w)
            continue
        end = line[-1]
        if km(end, w[-1]) < km(end, w[0]):
            w = w[::-1]
        if len(line) == len(ways[0]) and km(line[0], w[0]) < km(end, w[0]) and km(line[0], w[0]) < 0.05:
            line = line[::-1]  # the first way was backwards
        line += w[1:] if km(line[-1], w[0]) < 0.02 else w
    return line


def from_osm(rel: int) -> list[tuple[float, float]]:
    d = get(f"https://hiking.waymarkedtrails.org/api/v1/details/relation/{rel}")
    ways: list = []
    _ways(d["route"], ways)
    return chain(ways)


def routed(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    coords = ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in points)
    d = get(f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{coords}"
            "?overview=full&geometries=geojson")
    if d.get("code") != "Ok":
        raise RuntimeError(d)
    return [(lat, lon) for lon, lat in d["routes"][0]["geometry"]["coordinates"]]


def from_ways(ids: list[int]) -> list[tuple[float, float]]:
    """OSM ways given by id, in walking order (each flipped to follow on from the last)."""
    ways = []
    for wid in ids:
        d = get(f"https://www.openstreetmap.org/api/0.6/way/{wid}/full.json")
        nodes = {e["id"]: (e["lat"], e["lon"]) for e in d["elements"] if e["type"] == "node"}
        way = next(e for e in d["elements"] if e["type"] == "way")
        ways.append([nodes[n] for n in way["nodes"]])
        time.sleep(0.3)
    return chain(ways)


# roads cost more than paths, so the local router keeps to the trail where both go
ROAD_COST = {"motorway": 9, "trunk": 6, "primary": 4, "secondary": 3, "tertiary": 2,
             "unclassified": 1.6, "residential": 1.6, "service": 1.4, "track": 1.1}


def local_route(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Shortest walk on every OSM highway in the area, mountain paths included (the public OSRM
    foot router leaves out paths with sac_scale=mountain_hiking and harder)."""
    import heapq
    pad = 0.01
    s, w = min(p[0] for p in points) - pad, min(p[1] for p in points) - pad
    n, e = max(p[0] for p in points) + pad, max(p[1] for p in points) + pad
    if (n - s) * (e - w) > 0.25:
        raise RuntimeError("area too large for the local router: add osm_ways or split with via")
    d = get(f"https://www.openstreetmap.org/api/0.6/map.json?bbox={w},{s},{e},{n}")
    nodes = {x["id"]: (x["lat"], x["lon"]) for x in d["elements"] if x["type"] == "node"}
    graph: dict[int, list[tuple[int, float]]] = {}
    for x in d["elements"]:
        tags = x.get("tags") or {}
        hw = tags.get("highway")
        if x["type"] != "way" or not hw or tags.get("foot") == "no" or tags.get("access") == "private":
            continue
        cost = ROAD_COST.get(hw, 1.0)
        nd = [i for i in x["nodes"] if i in nodes]
        for a, b in zip(nd, nd[1:]):
            c = km(nodes[a], nodes[b]) * cost
            graph.setdefault(a, []).append((b, c))
            graph.setdefault(b, []).append((a, c))
    if not graph:
        raise RuntimeError("no OSM paths in the area")

    def snap(p):
        return min(graph, key=lambda i: km(nodes[i], p))

    out: list[tuple[float, float]] = []
    for a, b in zip(points, points[1:]):
        src, dst = snap(a), snap(b)
        dist, prev, pq = {src: 0.0}, {}, [(0.0, src)]
        while pq:
            c, u = heapq.heappop(pq)
            if u == dst:
                break
            if c > dist.get(u, 1e18):
                continue
            for v, wv in graph[u]:
                if c + wv < dist.get(v, 1e18):
                    dist[v], prev[v] = c + wv, u
                    heapq.heappush(pq, (c + wv, v))
        if dst not in dist:
            raise RuntimeError("the OSM paths here don't connect these two points")
        path = [dst]
        while path[-1] != src:
            path.append(prev[path[-1]])
        seg = [nodes[i] for i in reversed(path)]
        out += seg[1:] if out else seg
    return out


def route(points, how: str):
    """local (OSM paths, every difficulty) for compact trails, OSRM for long ones."""
    if how != "osrm":
        try:
            return local_route(points), "local"
        except RuntimeError as e:
            if how == "local":
                raise
            print(f"  local router: {e}; trying OSRM")
    return routed(points), "osrm"


def nearest(line, p) -> tuple[int, float]:
    best = min(range(len(line)), key=lambda i: km(line[i], p))
    return best, km(line[best], p)


def clip(line, a, b):
    """The part of an OSM relation between the start and the goal, in that direction."""
    i, _ = nearest(line, a)
    j, _ = nearest(line, b)
    return line[i:j + 1] if i <= j else line[j:i + 1][::-1]


# ---------------------------------------------------------------- altitude

def resample(line, step_km: float):
    out = [line[0]]
    acc = 0.0
    for a, b in zip(line, line[1:]):
        d = km(a, b)
        while acc + d >= step_km and d > 0:
            t = (step_km - acc) / d
            a = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            out.append(a)
            d = km(a, b)
            acc = 0.0
        acc += d
    if km(out[-1], line[-1]) > 0.005:
        out.append(line[-1])
    return out


def elevations(pts) -> list[float]:
    out: list[float] = []
    for i in range(0, len(pts), 100):
        chunk = pts[i:i + 100]
        q = urllib.parse.urlencode({"latitude": ",".join(f"{p[0]:.5f}" for p in chunk),
                                    "longitude": ",".join(f"{p[1]:.5f}" for p in chunk)})
        out += get(f"https://api.open-meteo.com/v1/elevation?{q}")["elevation"]
        time.sleep(0.3)
    return out


def smooth(e: list[float], n: int = 2) -> list[float]:
    return [sum(e[max(0, i - n):i + n + 1]) / len(e[max(0, i - n):i + n + 1]) for i in range(len(e))]


def climb(e: list[float], threshold: float = 5.0) -> tuple[float, float]:
    """Up and down with a small dead band, so DEM noise on the flat does not add up."""
    up = down = 0.0
    ref = e[0]
    for x in e[1:]:
        if x - ref >= threshold:
            up += x - ref
            ref = x
        elif ref - x >= threshold:
            down += ref - x
            ref = x
    return up, down


def walk_hours(dist_km: float, up: float, down: float) -> float:
    """DIN 33466, the Alpine clubs' rule: 4 km/h on the flat, 300 m/h up, 500 m/h down;
    the larger of distance time and climb time plus half the smaller."""
    h = dist_km / 4.0
    v = up / 300.0 + down / 500.0
    return max(h, v) + min(h, v) / 2


def simplify(pts, tol_km: float):
    """Douglas-Peucker on (lat, lon, ...) points, distances in km on a local plane."""
    if len(pts) < 3:
        return pts
    lat0 = math.radians(pts[0][0])

    def xy(p):
        return (p[1] * 111.32 * math.cos(lat0), p[0] * 110.57)

    def dist(p, a, b):
        (px, py), (ax, ay), (bx, by) = xy(p), xy(a), xy(b)
        dx, dy = bx - ax, by - ay
        if dx == dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - ax - t * dx, py - ay - t * dy)

    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        k, dm = None, tol_km
        for m in range(i + 1, j):
            d = dist(pts[m], pts[i], pts[j])
            if d > dm:
                k, dm = m, d
        if k is not None:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [p for p, f in zip(pts, keep) if f]


# ---------------------------------------------------------------- one trail

def build(t: dict) -> dict:
    pts = [(p["lat"], p["lon"]) for p in t["points"]]
    start, goal = pts[0], pts[-1]
    line = None
    how = "routed"
    if t.get("osm"):
        try:
            rel = from_osm(t["osm"])
            _, ds = nearest(rel, start)
            _, dg = nearest(rel, goal)
            if ds < 1.0 and dg < 1.0:
                line = clip(rel, start, goal)
                how = "osm"
            else:
                print(f"  osm {t['osm']} misses start ({ds:.1f} km) or goal ({dg:.1f} km): routing")
        except Exception as e:
            print(f"  osm {t['osm']} failed: {e}")
    if line is None and t.get("osm_ways"):
        line = from_ways(t["osm_ways"])
        how = "osm_ways"
        if t["shape"] == "loop" and km(line[0], line[-1]) > 0.3:
            line += route([line[-1], line[0]], t.get("router", "auto"))[0][1:]
    if line is None:
        order = list(pts)
        for v in t.get("via") or []:  # extra routing points, placed where they fit best
            v = tuple(v)
            k = min(range(1, len(order)), key=lambda i: km(order[i - 1], v) + km(v, order[i]) - km(order[i - 1], order[i]))
            order.insert(k, v)
        if t["shape"] == "loop" and km(order[0], order[-1]) > 0.2:
            order.append(order[0])
        line, how = route(order, t.get("router", "auto"))
    elif how == "osm" and t["shape"] == "loop" and km(line[0], line[-1]) > 0.3:
        line += route([line[-1], line[0]], t.get("router", "auto"))[0][1:]

    samp = resample(line, 0.04)
    ele = smooth(elevations(samp))
    dists = [0.0]
    for a, b in zip(samp, samp[1:]):
        dists.append(dists[-1] + km(a, b))
    one_km = dists[-1]
    up, down = climb(ele)

    # the key points on the line, in order
    marks = []
    lo = 0
    for n, p in enumerate(t["points"]):
        here = (p["lat"], p["lon"])
        if n == 0 and km(samp[0], here) <= 0.8:
            i = 0  # the line starts at the start (a loop also ends there: never take its end)
        else:
            # the first pass within 100 m, so a loop or a there-and-back line that comes by the
            # same place twice keeps the walking order; else the nearest sample after the last
            near = [k for k in range(lo, len(samp)) if km(samp[k], here) <= 0.1]
            i = near[0] if near else min(range(lo, len(samp)), key=lambda k: km(samp[k], here))
        off = km(samp[i], (p["lat"], p["lon"]))
        if off > 0.8:
            print(f"  ! point {p['id']} is {off:.2f} km off the path")
        marks.append(i)
        lo = i
    segs = []
    for (a, ia), (b, ib) in zip(zip(t["points"], marks), zip(t["points"][1:], marks[1:])):
        u, d = climb(ele[ia:ib + 1]) if ib > ia else (0.0, 0.0)
        dk = dists[ib] - dists[ia]
        segs.append({"from": a["id"], "to": b["id"], "km": round(dk, 1), "up": round(u), "down": round(d),
                     "hours": round(walk_hours(dk, u, d), 1)})

    total_km = one_km * (2 if t["shape"] == "out_and_back" else 1)
    total_up = up + (down if t["shape"] == "out_and_back" else 0)
    total_down = down + (up if t["shape"] == "out_and_back" else 0)
    pub = t.get("published") or {}
    for name, ours, theirs in (("km", total_km, pub.get("km")), ("gain", total_up, pub.get("gain_m"))):
        if name == "gain" and ((theirs or 0) < 200 or t["kind"] == "multiday"):
            continue  # flat walks (DEM noise > climb) and long treks (a 90 m DEM misses the many small ups): the test skips them too
        if theirs and abs(ours - theirs) / theirs > 0.3:
            print(f"  ! {name}: computed {ours:.0f} vs published {theirs}")

    line3 = [(round(p[0], 5), round(p[1], 5), round(e)) for p, e in zip(samp, ele)]
    step = max(1, len(samp) // 160)
    prof = [[round(dists[i], 2), round(ele[i])] for i in range(0, len(samp), step)]
    if prof[-1][0] != round(dists[-1], 2):
        prof.append([round(dists[-1], 2), round(ele[-1])])
    return {
        "id": t["id"], "how": how,
        "km": round(total_km, 1), "one_way_km": round(one_km, 1),
        "gain_m": round(total_up), "loss_m": round(total_down),
        "max_m": round(max(ele)), "min_m": round(min(ele)),
        "walk_hours": round(walk_hours(total_km, total_up, total_down), 1),
        "points": [{"id": p["id"], "km": round(dists[i], 2), "ele": round(ele[i]),
                    "lat": samp[i][0], "lon": samp[i][1]} for p, i in zip(t["points"], marks)],
        "segments": segs,
        "profile": prof,
        "line": simplify(line3, 0.008),
    }


def main(only: list[str]) -> None:
    GEO.mkdir(parents=True, exist_ok=True)
    for f in sorted(DATA.glob("*/*.json")):
        for t in [json.loads(f.read_text(encoding="utf-8"))]:
            if only and t["id"] not in only:
                continue
            print(t["id"])
            g = build(t)
            print(f"  {g['how']}: {g['km']} km, +{g['gain_m']} m, {g['min_m']}-{g['max_m']} m, "
                  f"{g['walk_hours']} h walking; published {t.get('published')}; {len(g['line'])} pts")
            (GEO / f"{t['id']}.json").write_text(json.dumps(g, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
