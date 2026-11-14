"""The long tail of treks (tier B, Manu 2026-11-14): every waymarked, named hiking route of
OpenStreetMap in the trekking countries that is worth a walk, with its line, distance, climb,
time and difficulty computed from open data. The top treks (tier A) are written by hand in
data/<cc>/; these are generated and never edited by hand.

Where we draw the line (told to Manu):
- kept: named hiking relations of 4-250 km whose centre lies in the country;
- dropped: unnamed or code-only routes ("004B"), city and park walks, fitness and nature-trail
  loops, cycle or rail trails, routes that are only containers of other routes (their stages are
  kept), the same route twice, and anything a tier-A trek already covers.

Steps (run from the repo root; needs `pip install shapely`; the census is slow, ~1 h, and cached):
  python tools/trails/osm_tail.py census PE CL AR IS NZ JP VN NA    # Waymarked Trails -> cache
  python tools/trails/osm_tail.py build  PE CL AR IS NZ JP VN NA    # -> backend/app/trails/tail/<cc>.json

Open data only: OpenStreetMap (ODbL) through the Waymarked Trails API, the Copernicus DEM through
Open-Meteo, country shapes from Natural Earth (world-atlas, public domain), the month climate of
the nearest place from the app's TerraClimate normals (CC0).
"""
from __future__ import annotations

from collections import Counter
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import build_trails as bt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
CACHE = Path(__file__).resolve().parent / ".cache"
OUT = ROOT / "backend/app/trails/tail"
API = "https://hiking.waymarkedtrails.org/api/v1"
UA = {"User-Agent": "trail-builder/1.0 (open-data trail profiles)"}

BBOX = {  # lon0, lat0, lon1, lat1
    "PE": (-81.5, -18.5, -68.5, 0.1), "CL": (-76, -56, -66.4, -17.4), "AR": (-73.6, -55.2, -53.5, -21.7),
    "IS": (-24.6, 63.2, -13.4, 66.6), "VN": (102.1, 8.4, 109.6, 23.4), "JP": (122.9, 24.0, 146.0, 45.6),
    "NA": (11.7, -29.0, 25.3, -16.9), "NZ": (166.3, -47.4, 178.7, -34.3), "IT": (6.6, 36.6, 18.6, 47.1)}
ISO_NUM = {"PE": "604", "CL": "152", "AR": "032", "IS": "352", "VN": "704", "JP": "392", "NA": "516",
           "NZ": "554", "IT": "380"}
SOUTH = {"PE", "CL", "AR", "NZ", "NA"}

MIN_KM, MAX_KM = 4.0, 250.0
NOT_A_TREK = re.compile(
    r"park ?run|parkrun|alameda|city ?walk|stadt|rundgang|heritage|walking tour|tour of|cycle|cycling|bike|mtb|"
    r"rail ?trail|educational|botanic|interpretive|jogging|promenade|fitness|health|shopping|street|"
    r"健康|公園|ウォーキング|散歩|散策|商店街|サイクリング|自転車|緑道|"
    r"circuito urbano|paseo urbano|costanera|malecon|malecón", re.I)
SAC = {"hiking": 1, "mountain_hiking": 2, "demanding_mountain_hiking": 3, "alpine_hiking": 4,
       "demanding_alpine_hiking": 5, "difficult_alpine_hiking": 6}


def get(url: str):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.load(r)
        except Exception:
            if i == 4:
                raise
            time.sleep(2 + 3 * i)


def merc(lon: float, lat: float) -> tuple[float, float]:
    return lon * 20037508.34 / 180, math.log(math.tan((90 + lat) * math.pi / 360)) * 20037508.34 / math.pi


# ---------------------------------------------------------------- census

def _tile(b, out, depth=0):
    a, c = merc(b[0], b[1]), merc(b[2], b[3])
    rows = get(f"{API}/list/by_area?bbox={a[0]:.0f},{a[1]:.0f},{c[0]:.0f},{c[1]:.0f}&limit=100")["results"]
    if len(rows) < 100 or depth > 12:
        out.update({r["id"]: r for r in rows if r["type"] == "relation"})
        return
    mx, my = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    for s in [(b[0], b[1], mx, my), (mx, b[1], b[2], my), (b[0], my, mx, b[3]), (mx, my, b[2], b[3])]:
        _tile(s, out, depth + 1)


def _details(rel: int) -> dict:
    """One relation: its tags, length, extent, the hardest sac_scale on it and its line."""
    d = get(f"{API}/details/relation/{rel}")
    r = d.get("route") or {}
    sac = set()

    def walk(n):
        if isinstance(n, dict):
            t = n.get("tags")
            if isinstance(t, dict) and t.get("sac_scale"):
                sac.add(t["sac_scale"])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(r)
    ways: list = []
    try:
        bt._ways(r, ways)
        line = bt.chain(ways)
    except Exception:
        line = []
    b = d.get("bbox")
    box = None
    if b:
        (la0, lo0), (la1, lo1) = bt.merc(b[0], b[1]), bt.merc(b[2], b[3])
        box = [lo0, la0, lo1, la1]
    return {"id": rel, "name": d.get("name") or "", "group": d.get("group"), "tags": d.get("tags") or {},
            "length": r.get("length") or 0, "sub": bool(d.get("subroutes")), "bbox": box,
            "sac": max((SAC.get(s, 0) for s in sac), default=0),
            "line": [(round(a, 5), round(b, 5)) for a, b in line]}


def census(cc: str) -> None:
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"census-{cc}.json"
    done = {d["id"]: d for d in json.loads(f.read_text())} if f.exists() else {}
    found: dict = {}
    _tile(BBOX[cc], found)
    todo = [i for i in found if i not in done]
    print(f"{cc}: {len(found)} relations, {len(todo)} to read")
    with ThreadPoolExecutor(6) as ex:
        for n, d in enumerate(ex.map(lambda i: _safe(_details, i), todo)):
            if d:
                done[d["id"]] = d
            if n % 100 == 99:
                f.write_text(json.dumps(list(done.values())))
                print(f"  {n + 1}/{len(todo)}", flush=True)
    f.write_text(json.dumps(list(done.values())))


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:
        what = a[0].get("id") if a and isinstance(a[0], dict) else a[:1]
        print(f"  failed {what}: {type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------- choose

def _shapes():
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.prepared import prep
    f = CACHE / "countries-10m.json"
    if not f.exists():
        CACHE.mkdir(exist_ok=True)
        with urllib.request.urlopen("https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-10m.json") as r:
            f.write_bytes(r.read())
    t = json.loads(f.read_text())
    (sx, sy), (tx, ty) = t["transform"]["scale"], t["transform"]["translate"]
    arcs = []
    for a in t["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in a:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(idx):
        out: list = []
        for i in idx:
            pts = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(pts if not out else pts[1:])
        return out
    res = {}
    for g in t["objects"]["countries"]["geometries"]:
        cc = next((k for k, v in ISO_NUM.items() if v == g.get("id")), None)
        if cc:
            polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
            res[cc] = prep(MultiPolygon([Polygon(ring(p[0]), [ring(h) for h in p[1:]]) for p in polys]).buffer(0.02))
    return res


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def why_not(d: dict, cc: str, inside) -> str | None:
    """Why a relation is not a tier-B trek, or None when it is one."""
    from shapely.geometry import Point
    name = d["name"].strip()
    if not re.search(r"[A-Za-zÀ-ÿ぀-ヿ一-鿿]{3,}", name):
        return "no name"
    if d["sub"]:
        return "container of other routes"
    if NOT_A_TREK.search(name) or d["tags"].get("route") not in (None, "hiking", "foot"):
        return "city, park or cycle walk"
    km = (d["length"] or 0) / 1000
    if km < MIN_KM:
        return "shorter than 4 km"
    if km > MAX_KM:
        return "longer than 250 km"
    b = d.get("bbox")
    if not b or not inside.contains(Point((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)):
        return "other country"
    return None


# ---------------------------------------------------------------- build one

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _norm(s)).strip("-")[:40].strip("-") or "trail"


_towns_cache: list | None = None


def _towns() -> list:
    """GeoNames towns of 1,000+ people (CC-BY 4.0) in the 8 countries: [name, lat, lon, cc, pop]."""
    global _towns_cache
    if _towns_cache is None:
        f = CACHE / "geonames-towns.json"
        if not f.exists():
            import csv, io, zipfile
            raw = urllib.request.urlopen("https://download.geonames.org/export/dump/cities1000.zip", timeout=120).read()
            txt = zipfile.ZipFile(io.BytesIO(raw)).read("cities1000.txt").decode("utf-8")
            keep = set(BBOX)
            rows = [[r[1], round(float(r[4]), 5), round(float(r[5]), 5), r[8], int(r[14] or 0)]
                    for r in csv.reader(io.StringIO(txt), delimiter="\t") if r[8] in keep and r[6] == "P"]
            f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        _towns_cache = json.loads(f.read_text(encoding="utf-8"))
    return _towns_cache


def _base(lat: float, lon: float, cc: str):
    """The town to sleep in: the app's most visited town or city within 30 km of the start,
    else the biggest GeoNames town within 30 km, else the nearest app town within 90 km, else the
    nearest GeoNames town within 90 km, else the nearest park, lake or sight the app knows."""
    from app import globe
    places = [p for p in globe.by_id().values() if p["country"] == cc]
    near = [(bt.km((lat, lon), (p["lat"], p["lon"])), p) for p in places if p["kind"] in ("city", "town")]
    towns = [(bt.km((lat, lon), (t[1], t[2])), {"name": t[0], "lat": t[1], "lon": t[2], "pop": t[4]})
             for t in _towns() if t[3] == cc and abs(t[1] - lat) < 1 and abs(t[2] - lon) < 1.5]
    close = [x for x in near if x[0] <= 30]
    if close:
        return max(close, key=lambda x: (x[1]["level"], -x[0]))[1]
    close = [x for x in towns if x[0] <= 30]
    if close:
        return max(close, key=lambda x: x[1]["pop"])[1]
    for pool in (near, towns):
        pool = [x for x in pool if x[0] <= 90]
        if pool:
            return min(pool, key=lambda x: x[0])[1]
    near = [(bt.km((lat, lon), (p["lat"], p["lon"])), p) for p in places
            if p["kind"] in ("nature", "landmark", "island")]
    near = [x for x in near if x[0] <= 90]
    return min(near, key=lambda x: x[0])[1] if near else None


TC = "https://thredds.northwestknowledge.net/thredds/dodsC/TERRACLIMATE_ALL"
_tc_cache: dict | None = None
_tc_scale: dict[str, tuple[float, float]] = {}


def _tc_var(var: str, path: str, la_i: int, lo_i: int, months: bool = True) -> list[float]:
    """One TerraClimate cell through OPeNDAP (CC0, Abatzoglou et al. 2018)."""
    if var not in _tc_scale:
        das = urllib.request.urlopen(urllib.request.Request(f"{TC}/{path}.das", headers=UA), timeout=60).read().decode()
        block = das[das.find(f"    {var} {{"):]
        block = block[:block.find("    }")]
        sf = re.search(r"scale_factor ([-\d.eE]+)", block)
        off = re.search(r"add_offset ([-\d.eE]+)", block)
        _tc_scale[var] = (float(sf.group(1)) if sf else 1.0, float(off.group(1)) if off else 0.0)
    sel = (f"[0:11][{la_i}:{la_i}][{lo_i}:{lo_i}]" if months else f"[{la_i}:{la_i}][{lo_i}:{lo_i}]")
    url = f"{TC}/{path}.ascii?{var}{urllib.parse.quote(sel)}"
    for i in range(5):
        try:
            txt = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode()
            break
        except Exception:
            if i == 4:
                raise
            time.sleep(2 + 2 * i)
    body = txt.split("---------------------------------------------")[-1]
    vals = [float(m.group(1)) for m in re.finditer(r"\]\s*,\s*([-\d.eE]+)", body)]
    sf, off = _tc_scale[var]
    return [v * sf + off for v in vals]


def terraclimate(lat: float, lon: float):
    """[[tmin, tmax, rain mm, vapour kPa] x 12] and the cell's height, for one 1/24 degree cell."""
    global _tc_cache
    f = CACHE / "terraclimate.json"
    if _tc_cache is None:
        _tc_cache = json.loads(f.read_text()) if f.exists() else {}
    la_i, lo_i = int((90 - lat) * 24), int((lon + 180) * 24)
    k = f"{la_i},{lo_i}"
    if k not in _tc_cache:
        v = {n: _tc_var(n, f"climatology/TerraClimate_19912020_{n}.nc", la_i, lo_i) for n in ("tmin", "tmax", "ppt", "vap")}
        ele = _tc_var("elevation", "layers/terraclim_dem.nc", la_i, lo_i, months=False)
        if len(v["tmax"]) != 12 or not ele or any(abs(x) > 1000 for x in v["tmax"]):
            _tc_cache[k] = None  # sea or no data
        else:
            _tc_cache[k] = [[[round(v["tmin"][m], 1), round(v["tmax"][m], 1), round(v["ppt"][m]), round(v["vap"][m], 3)]
                             for m in range(12)], round(ele[0])]
        f.write_text(json.dumps(_tc_cache))
    return _tc_cache[k]


_STOP_ELE: dict[str, float] = {}


def _climate_near(lat: float, lon: float):
    """The normal weather of the nearest app stop within 150 km (TerraClimate, CC0) and its height."""
    from app.globe import routes
    if not _STOP_ELE:
        for r in json.loads((ROOT / "backend/app/globe/routes.json").read_text(encoding="utf-8"))["routes"]:
            for st in r["stops"]:
                _STOP_ELE[f"{st['lat']:.3f},{st['lon']:.3f}"] = st["elevation_m"]
        for f in sorted((ROOT / "backend/app/inspire/itineraries").glob("*.json")):
            for st in json.loads(f.read_text(encoding="utf-8"))["stops"]:
                _STOP_ELE[f"{st['lat']:.3f},{st['lon']:.3f}"] = st["elevation_m"]
    best = None
    for k, c in routes._climate().items():
        la, lo = map(float, k.split(","))
        d = bt.km((lat, lon), (la, lo))
        if d <= 150 and (best is None or d < best[0]):
            best = (d, c, _STOP_ELE.get(k, 0.0))
    return best


def _months(lat: float, lon: float, top_m: float, cc: str, low_m: float | None = None) -> list[int]:
    """Good months to walk: the normal weather of the trail's own 4 km cell (TerraClimate), moved
    up to its highest point (-6.5 °C per 1,000 m): not the wet months, not over 33 °C at its lowest
    point, and on top a day above 4 °C and a mean above 0 °C."""
    from app.globe import routes
    tc = _safe(terraclimate, lat, lon)
    near = (0, tc[0], tc[1]) if tc else _climate_near(lat, lon)
    if near:
        _, clim, here = near
        low_m = here if low_m is None else low_m
        mean_rain = sum(c[2] for c in clim) / 12
        good: list[int] = []
        fair: list[int] = []
        for m, (lo, hi, rain, vap) in enumerate(clim, 1):
            up = 6.5 * max(0.0, top_m - here) / 1000
            down = 6.5 * max(0.0, here - low_m) / 1000
            wet = rain > 400 or (rain > 60 and rain > 1.6 * mean_rain)
            hot = routes.feels_like(hi + down, vap) >= 33  # at the trail's lowest point
            cold = (lo + hi) / 2 - up < 0 or hi - up < 4  # frozen on top
            if not (wet or hot or cold):
                good.append(m)
            elif not (wet or hot):
                fair.append(m)  # cold on top: a high peak, climbed in its dry season anyway
        if not good and len(fair) >= 3:
            good = fair
        if good:
            return good
    summer = [11, 12, 1, 2, 3] if lat < 0 else [6, 7, 8, 9]
    return list(range(1, 13)) if top_m < 800 and abs(lat) < 38 else summer


def _difficulty(sac: int, hours: float, gain: float, top: float) -> str:
    if sac >= 4:
        return "technical"
    if sac == 3 or hours > 7 or gain > 1100 or top > 4000:
        return "hard"
    if sac == 2 or hours > 3.5 or gain > 450:
        return "moderate"
    return "easy"


CULTURE = re.compile(r"inca|inka|qhapaq|kumano|nakasendo|henro|pilgrim|camino real|ruin|templ|shrine|church|"
                     r"monaster|castle|fort|heritage|古道|街道|遍路|参道|寺|神社|城", re.I)


def effort(hours: float, gain: float, top: float, days: int) -> int:
    """The ranking rubric's effort: 1 = under 2 h and 200 m ... 5 = over 9 h, 1,200 m, a
    multiday walk with a pack, or above 4,500 m."""
    if days > 1 or hours > 9 or gain > 1200 or top > 4500:
        return 5
    if hours > 7 or gain > 900:
        return 4
    if hours >= 5 or gain >= 500:
        return 3
    if hours >= 2 or gain >= 200:
        return 2
    return 1


def scores(name: str, g: dict, days: int, hours: float, has_picture: bool, in_town: bool) -> dict:
    """All six scores of the ranking rubric, by rule from the computed line (Manu, 2026-11-14):
    effort from hours and climb; relax the other way round; nature and landscape from height
    and relief; culture and history when the name says so (an Inca road, a pilgrim way, a
    shrine) or the walk starts in a town."""
    top, relief = g["max_m"], g["max_m"] - g["min_m"]
    e = effort(hours, g["gain_m"], top, days)
    named = bool(CULTURE.search(name))
    return {
        "effort": e,
        "nature": min(5, 3 + (top > 1500 or relief > 600) + (top > 3000) - in_town),
        "culture": 3 if named else 1 if in_town else 0,
        "relax": max(0, 4 - e),
        "history": 4 if named else 1 if in_town else 0,
        "landscape": min(5, (2 if relief < 150 else 3 if relief < 500 else 4 if relief < 1200 else 5)
                         + (has_picture and relief < 1200)),
    }


def _anchors(p: dict) -> list[tuple[float, float]]:
    """Where a planned top trek is: its base town and the drawings it reuses."""
    from app import art, globe
    out = [(g["lat"], g["lon"]) for g in globe.by_id().values()
           if g["country"] == p["country"] and _norm(g["name"]) == _norm(p["base"])]
    for sc in p.get("scenes") or []:
        lm = art.by_id().get(sc["reuse"]) if sc.get("reuse") else None
        if lm:
            out.append((lm.lat, lm.lon))
    return out


def _words(s: str) -> set[str]:
    stop = {"trek", "trail", "track", "circuit", "circuito", "sendero", "senda", "the", "de", "del", "la",
            "los", "las", "to", "and", "y", "walk", "hike", "route", "ruta", "camino", "of", "lake", "laguna",
            "lagunas", "lago", "paso", "cerro", "mirador", "salto", "volcano", "volcan", "trekking", "travesia",
            "senda", "glaciar", "glacier", "valle", "valley", "rio", "piedra", "mount", "peak", "summit", "pass",
            "circuit", "loop", "traverse", "national", "park", "parque", "nacional", "track", "lookout", "base",
            "refugio", "hut", "estero", "playa", "beach", "costa"}
    return {w for w in _norm(s).split() if w not in stop and len(w) > 2}


DROPS = Counter()


def _drop(why):
    DROPS[why] += 1


def build_one(d: dict, cc: str, taken: list, planned: list = ()) -> tuple[dict, dict] | None:
    from app import art
    line = [tuple(p) for p in d.get("line") or []] or bt.from_osm(d["id"])
    if len(line) < 2:
        return _drop("no line")
    start, end = line[0], line[-1]
    w = _words(d["name"])
    mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    if w and any(len(w & _words(p)) >= max(1, (len(w) + 1) // 2)
                 and (not at or min(bt.km(mid, a) for a in at) < 50) for p, at in planned):
        return _drop("planned A name")  # a top trek planned by hand (list.json) is this route
    for t in taken:  # a tier-A trek already covers it
        a, b = (t.points[0].lat, t.points[0].lon), (t.points[-1].lat, t.points[-1].lon)
        if t.osm == d["id"] or (bt.km(start, a) < 1.5 and bt.km(end, b) < 1.5) or (bt.km(start, b) < 1.5 and bt.km(end, a) < 1.5):
            return _drop("tier A covers")
    samp = bt.resample(line, 0.04)
    if len(samp) > 6000:
        samp = bt.resample(line, 0.1)
    ele = bt.smooth(bt.tile_elevations(samp))
    if ele[0] >= max(ele) - 40 and ele[0] - ele[-1] > 150:  # drawn from the summit down: walk it up
        line, samp, ele = line[::-1], samp[::-1], ele[::-1]
        start, end = line[0], line[-1]
    top_i = max(range(len(ele)), key=ele.__getitem__)
    loop = bt.km(start, end) < 0.5
    # a line that climbs to its end is walked there and back
    shape = "loop" if loop else "out_and_back" if ele[-1] >= max(ele) - 40 and ele[-1] - ele[0] > 150 else "one_way"
    pts = [{"id": "start", "name": "Start", "lat": start[0], "lon": start[1], "role": "start"}]
    top = samp[top_i]
    if 0 < top_i < len(samp) - 1 and bt.km(top, start) > 1 and bt.km(top, end) > 1 and max(ele) - ele[0] > 200:
        pts.append({"id": "top", "name": f"Highest point, {round(max(ele)):,} m", "lat": top[0], "lon": top[1], "role": "point"})
    gname = "Back at the start" if loop else "End" if shape == "one_way" else f"Top, {round(ele[-1]):,} m"
    pts.append({"id": "goal", "name": gname, "lat": end[0], "lon": end[1], "role": "goal"})
    base = _base(start[0], start[1], cc)
    if not base:
        return _drop("no base")
    t = {"id": f"{cc.lower()}-osm-{d['id']}", "name": label(d)[:80], "country": cc, "base": base["name"][:60],
         "region": (d["tags"].get("operator") or "")[:100], "kind": "day", "days": 1, "shape": shape,
         "osm": d["id"], "router": "auto", "points": pts, "tier": "B"}
    real, real_ele = bt.from_osm, bt.elevations
    bt.from_osm = lambda rel: line  # the line we already have
    bt.elevations = bt.tile_elevations
    try:
        g = bt.build(t)
    finally:
        bt.from_osm, bt.elevations = real, real_ele
    if g["km"] < MIN_KM * (2 if shape == "out_and_back" else 1) * 0.9 or g["one_way_km"] < 0.6 * d["length"] / 1000:
        return _drop("broken line")  # a broken or partial line in OSM
    if not tidy(t, g):
        return _drop("points off the built line")
    h = g["walk_hours"]
    days = max(1, math.ceil(h / 7)) if h > 10 else 1
    t.update({
        "kind": "multiday" if days > 1 else "day", "days": min(days, 21),
        "difficulty": _difficulty(d["sac"], h, g["gain_m"], g["max_m"]),
        "glacier": False,
        "months": _months(start[0], start[1], g["max_m"], cc, g["min_m"]),
        "hours": [max(0.5, round(h * 0.85 * 2) / 2), max(0.5, round(h * 1.15 * 2) / 2)],
        "why": (f"A waymarked {('loop' if loop else 'path')} of {g['km']:.0f} km, +{g['gain_m']:,} m, "
                f"up to {g['max_m']:,} m, from near {base['name']}.")[:300],
        "sources": [f"https://www.openstreetmap.org/relation/{d['id']}",
                    f"https://hiking.waymarkedtrails.org/#route?id={d['id']}"],
    })
    # its picture: a drawing of the place it reaches (or passes at its top), never a far one
    for p in reversed(pts):
        lm = art._nearest(p["lat"], p["lon"], cc)
        if lm and bt.km((p["lat"], p["lon"]), (lm.lat, lm.lon)) <= 3 and all(q.get("scene") != lm.id for q in pts):
            p["scene"] = lm.id
            break
    t["scores"] = scores(d["name"], g, t["days"], h, any(p.get("scene") for p in pts),
                         bt.km(start, (base["lat"], base["lon"])) < 2)
    t["kind"] = "multiday" if t["days"] > 1 else "day"
    return t, g


def label(d: dict) -> str:
    """The route's name for an English app: name:en, else a romanised name, else the name."""
    tg = d.get("tags") or {}
    for k in ("name:en", "int_name", "name:ja-Latn", "name:ja_rm", "name:vi-Latn"):
        if tg.get(k) and tg[k].isascii():
            return tg[k].strip()
    return d["name"].strip()


CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
JP_KIND = [("縦走", "Ridge traverse"), ("街道", "Old road"), ("道中", "Old road"), ("古道", "Old road"),
           ("自然歩道", "Nature trail"), ("登山道", "Mountain trail"), ("ルート", "Mountain trail"),
           ("峠", "Pass trail"), ("コース", "Trail")]


def names(trails: list[dict]) -> None:
    """A name only in Japanese script gets an English lead ("Old road near Matsumoto (五千石街道)").
    Stages of one long trail share its name: tell them apart by their base town."""
    for t in trails:
        if CJK.search(t["name"]):
            kind = next((en for jp, en in JP_KIND if jp in t["name"]), "Trail")
            t["name"] = f"{kind} near {t['base']} ({t['name']})"[:80]
    seen: dict[str, int] = {}
    for t in trails:
        seen[t["name"]] = seen.get(t["name"], 0) + 1
    for t in trails:
        if seen[t["name"]] > 1:
            t["name"] = f"{t['name']} near {t['base']}"[:80]
    seen = {}
    for t in trails:
        n = seen[t["name"]] = seen.get(t["name"], 0) + 1
        if n > 1:
            t["name"] = f"{t['name']} ({n})"[:80]


def tidy(t: dict, g: dict) -> bool:
    """Keep the points on the built line: a gappy OSM line can be walked in another order, so a
    highest point found on the raw line may be off it (then it goes); an end off it drops the trek.
    The top's name takes the built height."""
    off = {gp["id"] for p, gp in zip(t["points"], g["points"]) if bt.km((p["lat"], p["lon"]), (gp["lat"], gp["lon"])) > 0.8}
    if off - {"top"}:
        return False
    if "top" in off:
        t["points"] = [p for p in t["points"] if p["id"] != "top"]
        g["points"] = [p for p in g["points"] if p["id"] != "top"]
    for p, gp in zip(t["points"], g["points"]):
        if p["id"] == "top":
            p["name"] = f"Highest point, {round(gp['ele']):,} m"
    return True


def build(cc: str) -> None:
    from app import trails
    inside = _shapes()[cc]
    rows = json.loads((CACHE / f"census-{cc}.json").read_text())
    taken = [t for t in trails.trails() if t.country == cc and t.tier == "A"]
    planned = [(p["name"], _anchors(p)) for p in trails.plan() if p["country"] == cc]
    why: dict[str, int] = {}
    keep, seen = [], set()
    for d in sorted(rows, key=lambda d: -d["length"]):
        w = why_not(d, cc, inside)
        key = (_norm(d["name"]), round(d["bbox"][0], 2) if d.get("bbox") else 0)
        if not w and key in seen:
            w = "same route twice"
        why[w or "kept"] = why.get(w or "kept", 0) + 1
        if not w:
            seen.add(key)
            keep.append(d)
    print(cc, why)
    out = []
    for n, d in enumerate(keep):
        r = _safe(build_one, d, cc, taken, planned)
        if r:
            out.append(r)
        if n % 25 == 24:
            print(f"  {n + 1}/{len(keep)}", flush=True)
    names([t for t, _ in out])
    OUT.mkdir(exist_ok=True)
    doc = {"_doc": "Tier-B treks (generated by tools/trails/osm_tail.py from OpenStreetMap, ODbL, and the "
                   "Copernicus DEM; never edit by hand).",
           "trails": [t for t, _ in out], "geo": {t["id"]: g for t, g in out}}
    (OUT / f"{cc.lower()}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{cc}: {len(out)} tier-B treks written; dropped {dict(DROPS)}")
    DROPS.clear()


if __name__ == "__main__":
    cmd, *ccs = sys.argv[1:]
    for c in ccs:
        {"census": census, "build": build}[cmd](c.upper())
