"""Every trek in the world (Manu, 2026-11-14): the waymarked hiking routes of OpenStreetMap, one
continent at a time, as dots with their numbers (no drawings). The same rules as the 8 trekking
countries (osm_tail.py): named, 4-250 km, no city, park, fitness or cycle loops, no containers.

Steps (from the repo root; needs osmium-tool, `pip install osmium shapely pycountry pillow`):
  # per country extract (openstreetmap.fr / geo2day, ODbL): osmium tags-filter ... r/route=hiking,foot
  osmium merge routes/*.pbf -o europe-routes.pbf     # cross-border routes become whole again
  python tools/trails/pbf_routes.py europe-routes.pbf census-europe.json
  python tools/trails/world_tail.py count census-europe.json
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import osm_tail as ot

CACHE = ot.CACHE
DONE = {"PE", "CL", "AR", "IS", "VN", "JP", "NA", "NZ"}  # the 8 trekking countries: their own thread


def shapes():
    """Natural Earth 1:10m countries (public domain, world-atlas) -> (STRtree, [alpha2])."""
    import pycountry
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.strtree import STRtree
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
    geoms, codes = [], []
    extra = {"Kosovo": "XK", "N. Cyprus": "CY", "Somaliland": "SO"}
    for g in t["objects"]["countries"]["geometries"]:
        if g["type"] not in ("Polygon", "MultiPolygon"):
            continue
        c = pycountry.countries.get(numeric=str(g.get("id", "")).zfill(3)) if g.get("id") else None
        cc = c.alpha_2 if c else extra.get(g.get("properties", {}).get("name", ""))
        if not cc:
            continue
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
        parts = [Polygon(ring(p[0]), [ring(h) for h in p[1:] if len(ring(h)) >= 4]) for p in polys if len(ring(p[0])) >= 4]
        if not parts:
            continue
        geoms.append(MultiPolygon(parts).buffer(0))
        codes.append(cc)
    return STRtree(geoms), geoms, codes


class Where:
    def __init__(self):
        self.tree, self.geoms, self.codes = shapes()

    def __call__(self, lon: float, lat: float) -> str | None:
        from shapely.geometry import Point
        p = Point(lon, lat)
        for i in self.tree.query(p):
            if self.geoms[i].contains(p):
                return self.codes[i]
        near = self.tree.query_nearest(p, max_distance=0.1)  # a coast walk just off the 1:10m shoreline
        return self.codes[near[0]] if len(near) else None


def why_not(d: dict, where: Where) -> tuple[str | None, str | None]:
    """(why it is not a trek or None, its country by the middle of its extent)."""
    name = d["name"].strip()
    if not re.search(r"[A-Za-zÀ-ÿĀ-žА-яͰ-Ͽ぀-ヿ一-鿿]{3,}", name):
        return "no name", None
    if d["sub"]:
        return "container of other routes", None
    if ot.NOT_A_TREK.search(name) or d["tags"].get("route") not in (None, "hiking", "foot"):
        return "city, park or cycle walk", None
    km = (d["length"] or 0) / 1000
    if km < ot.MIN_KM:
        return "shorter than 4 km", None
    if km > ot.MAX_KM:
        return "longer than 250 km (its stages are kept)", None
    b = d.get("bbox")
    if not b:
        return "no line", None
    cc = where((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    if not cc:
        return "at sea", None
    if cc in DONE:
        return "one of the 8 trekking countries", cc
    return None, cc


def count(census: str) -> None:
    rows = json.loads(Path(census).read_text(encoding="utf-8"))
    where = Where()
    why, per, km_band, group = Counter(), Counter(), Counter(), Counter()
    seen = set()
    for d in sorted(rows, key=lambda d: -d["length"]):
        w, cc = why_not(d, where)
        key = (ot._norm(d["name"]), round(d["bbox"][0], 2) if d.get("bbox") else 0)
        if not w and key in seen:
            w = "same route twice"
        why[w or "kept"] += 1
        if w:
            continue
        seen.add(key)
        per[cc] += 1
        k = d["length"] / 1000
        km_band["4-10 km" if k < 10 else "10-20 km" if k < 20 else "20-50 km" if k < 50 else "50-250 km"] += 1
        group[d.get("group") or "-"] += 1
    print(json.dumps({"relations": len(rows), "why": why, "km": km_band, "network": group,
                      "countries": dict(per.most_common())}, indent=1, ensure_ascii=False))


# ---------------------------------------------------------------- climate, towns (bulk, local)

TC = ot.TC


def _tc_grid(var: str, path: str, la: tuple[int, int], lo: tuple[int, int], months: bool):
    import numpy as np
    das = urllib.request.urlopen(urllib.request.Request(f"{TC}/{path}.das", headers=ot.UA), timeout=60).read().decode()
    block = das[das.find(f"    {var} {{"):]
    block = block[:block.find("    }")]
    sf = re.search(r"scale_factor ([-\d.eE]+)", block)
    off = re.search(r"add_offset ([-\d.eE]+)", block)
    fill = re.search(r"_FillValue ([-\d.eE]+)", block) or re.search(r"missing_value ([-\d.eE]+)", block)
    sel = (f"[0:11]" if months else "") + f"[{la[0]}:{STRIDE}:{la[1]}][{lo[0]}:{STRIDE}:{lo[1]}]"
    url = f"{TC}/{path}.ascii?{var}{urllib.parse.quote(sel)}"
    txt = urllib.request.urlopen(urllib.request.Request(url, headers=ot.UA), timeout=600).read().decode()
    body = txt.split("---------------------------------------------")[-1]
    grid = body.split(f"{var}.{var}[", 1)[1].split("\n\n", 1)[0]
    rows = [ln.split(",", 1)[1] for ln in grid.splitlines() if ln.startswith("[")]
    a = np.array([[float(v) for v in r.split(",")] for r in rows])
    bad = (a == float(fill.group(1))) if fill else (a == -32768)
    bad |= a == -32768
    a = a * (float(sf.group(1)) if sf else 1.0) + (float(off.group(1)) if off else 0.0)
    a[bad] = np.nan
    n_lo = a.shape[1]
    return a.reshape((12, -1, n_lo) if months else (-1, n_lo))


STRIDE = 2  # 1/12 degree, ~9 km: plenty for which months are good


class Climate:
    """TerraClimate 1991-2020 normals (CC0) for a whole region in 5 requests, not 5 per trek."""

    def __init__(self, box: tuple[float, float, float, float]):
        import numpy as np
        lon0, lat0, lon1, lat1 = box
        la = (int((90 - lat1) * 24), int((90 - lat0) * 24))
        lo = (int((lon0 + 180) * 24), int((lon1 + 180) * 24))
        f = CACHE / f"tc-{la[0]}-{la[1]}-{lo[0]}-{lo[1]}-{STRIDE}.npz"
        if f.exists():
            z = np.load(f)
            self.v = {k: z[k] for k in z.files}
        else:
            self.v = {n: _tc_grid(n, f"climatology/TerraClimate_19912020_{n}.nc", la, lo, True)
                      for n in ("tmin", "tmax", "ppt", "vap")}
            self.v["ele"] = _tc_grid("elevation", "layers/terraclim_dem.nc", la, lo, False)
            np.savez_compressed(f, **self.v)
        self.la0, self.lo0 = la[0], lo[0]

    def __call__(self, lat: float, lon: float):
        import math as m
        i = round((int((90 - lat) * 24) - self.la0) / STRIDE)
        j = round((int((lon + 180) * 24) - self.lo0) / STRIDE)
        ny, nx = self.v["ele"].shape
        best = None
        for r in range(0, 3):  # a coast or lake cell has no data: the nearest land cell
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    a, b = i + di, j + dj
                    if 0 <= a < ny and 0 <= b < nx and not m.isnan(self.v["tmax"][0, a, b]) \
                            and not m.isnan(self.v["ele"][a, b]):
                        best = (a, b)
                        break
                if best:
                    break
            if best:
                break
        if not best:
            return None
        a, b = best
        clim = [[round(float(self.v["tmin"][k, a, b]), 1), round(float(self.v["tmax"][k, a, b]), 1),
                 round(float(self.v["ppt"][k, a, b])), round(float(self.v["vap"][k, a, b]), 3)] for k in range(12)]
        return [clim, round(float(self.v["ele"][a, b]))]


class Towns:
    """Where to sleep (osm_tail._base, same order of choice) with a 1-degree grid, for any country."""

    def __init__(self):
        import csv, io, zipfile
        from app import globe
        f = CACHE / "geonames-world.json"
        if not f.exists():
            raw = urllib.request.urlopen("https://download.geonames.org/export/dump/cities1000.zip", timeout=300).read()
            txt = zipfile.ZipFile(io.BytesIO(raw)).read("cities1000.txt").decode("utf-8")
            rows = [[r[1], round(float(r[4]), 5), round(float(r[5]), 5), r[8], int(r[14] or 0)]
                    for r in csv.reader(io.StringIO(txt), delimiter="\t") if r[6] == "P"]
            f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        self.geo = defaultdict(list)
        for t in json.loads(f.read_text(encoding="utf-8")):
            self.geo[(int(t[1] // 1), int(t[2] // 1))].append({"name": t[0], "lat": t[1], "lon": t[2], "pop": t[4], "cc": t[3]})
        self.app = defaultdict(list)
        for p in globe.by_id().values():
            self.app[(int(p["lat"] // 1), int(p["lon"] // 1))].append(p)

    @staticmethod
    def _around(grid, lat, lon, cc):
        i, j = int(lat // 1), int(lon // 1)
        for a in (i - 1, i, i + 1):
            for b in (j - 2, j - 1, j, j + 1, j + 2):
                for p in grid.get((a, b), ()):
                    if p.get("cc", p.get("country")) == cc:
                        yield p

    def __call__(self, lat: float, lon: float, cc: str):
        from build_trails import km
        here = (lat, lon)
        app = [(km(here, (p["lat"], p["lon"])), p) for p in self._around(self.app, lat, lon, cc)]
        near = [x for x in app if x[1]["kind"] in ("city", "town")]
        towns = [(km(here, (t["lat"], t["lon"])), t) for t in self._around(self.geo, lat, lon, cc)]
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
        pool = [x for x in app if x[1]["kind"] in ("nature", "landmark", "island") and x[0] <= 90]
        return min(pool, key=lambda x: x[0])[1] if pool else None


# ---------------------------------------------------------------- build

def polyline(pts, prec=(1e5, 1e5, 1)) -> str:
    """Google's encoded polyline with a third value (metres): ~5 bytes a point instead of ~25."""
    out, last = [], [0] * len(prec)
    for p in pts:
        for k, f in enumerate(prec):
            v = int(round(p[k] * f))
            d, last[k] = v - last[k], v
            d = ~(d << 1) if d < 0 else d << 1
            while d >= 0x20:
                out.append(chr((0x20 | (d & 0x1f)) + 63))
                d >>= 5
            out.append(chr(d + 63))
    return "".join(out)


def compact(g: dict) -> dict:
    """The geo of a world trek, small: the line simplified to 25 m and encoded, no profile (the
    app rebuilds it from the line)."""
    import build_trails as bt
    line = bt.simplify([tuple(p) for p in g["line"]], 0.025)
    out = {k: g[k] for k in ("km", "one_way_km", "gain_m", "loss_m", "max_m", "min_m", "walk_hours", "points", "segments")}
    out["points"] = [{**p, "lat": round(p["lat"], 5), "lon": round(p["lon"], 5)} for p in g["points"]]
    out["enc"] = polyline(line)
    return out


BOT_WIKIS = {"cebwiki", "warwiki", "arzwiki", "svwiki", "azbwiki"}  # bot-made geo stubs


def sitelinks(qids) -> dict[str, int]:
    """How many Wikipedias have an article (Wikidata, CC0), not counting the wikis whose bots wrote
    a stub for every hill on the map: the 'famous' rule is 5 or more languages."""
    import time
    f = CACHE / "wikidata-sitelinks.json"
    have = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    todo = sorted({q for q in qids if q and re.fullmatch(r"Q\d+", q) and q not in have})
    print(f"  wikidata: {len(todo)} items to look up", flush=True)
    for i in range(0, len(todo), 50):
        ids = "|".join(todo[i:i + 50])
        d = None
        for k in range(6):
            try:
                url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={ids}&props=sitelinks&format=json"
                with urllib.request.urlopen(urllib.request.Request(url, headers=ot.UA), timeout=120) as r:
                    d = json.loads(r.read().decode("utf-8"))
                break
            except Exception:
                time.sleep(8 * (k + 1))
        if d is None:
            print("  wikidata failed: the rest count as not famous")
            break
        for q, e in d.get("entities", {}).items():
            sl = e.get("sitelinks") or {}
            have[q] = sum(1 for k in sl if k.endswith("wiki") and k not in BOT_WIKIS
                          and k not in ("commonswiki", "specieswiki", "metawiki", "wikidatawiki"))
        f.write_text(json.dumps(have), encoding="utf-8")
        time.sleep(float(__import__("os").environ.get("WIKIDATA_PAUSE", 0.5)))  # Wikimedia throttles this host
    f.write_text(json.dumps(have), encoding="utf-8")
    return have


def route_rank(d: dict, km: float, links: dict) -> int:
    """The places' zoom ladder for a route: 5 famous (5+ Wikipedias), 4 any Wikipedia article, an
    international or national network or 100+ km, 3 a regional network or 30+ km, 2 12+ km, else 1.
    6 (seen from space) is kept for the iconic treks of the world (_iconic.json)."""
    tg = d.get("tags") or {}
    n = links.get(tg.get("wikidata", ""), 0)
    if n >= 5:
        return 5
    if n or tg.get("wikipedia") or d.get("group") in ("I", "N") or km >= 100:
        return 4
    if d.get("group") == "R" or km >= 30:
        return 3
    return 2 if km >= 12 else 1


def goal_rank(w: dict, gain: float, links: dict) -> int:
    n = links.get(w.get("wiki") or "", 0)
    return 5 if n >= 5 else 3 if n else 2 if gain >= 600 else 1


def prefetch(lines) -> None:
    """Download the terrain tiles of all lines at once, 32 at a time (the builds then only read
    the disk): hundreds of thousands of treks, one tile at a time, would take a day."""
    import math as m
    from concurrent.futures import ThreadPoolExecutor
    import build_trails as bt
    n = 2 ** bt.TILE_Z
    keys = set()
    for line in lines:
        prev = None
        for la, lo in line:
            if prev and abs(prev[0] - la) < 0.002 and abs(prev[1] - lo) < 0.002:
                continue
            prev = (la, lo)
            x = (lo + 180) / 360 * n
            y = (1 - m.log(m.tan(m.radians(la)) + 1 / m.cos(m.radians(la))) / m.pi) / 2 * n
            keys.add((int(x), int(y)))
    d = Path(bt.__file__).resolve().parent / ".cache" / "terrarium"
    d.mkdir(parents=True, exist_ok=True)
    todo = [k for k in keys if not (d / f"{bt.TILE_Z}-{k[0]}-{k[1]}.png").exists()]
    print(f"  terrain tiles: {len(keys)}, {len(todo)} to download", flush=True)

    def get(k):
        f = d / f"{bt.TILE_Z}-{k[0]}-{k[1]}.png"
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{bt.TILE_Z}/{k[0]}/{k[1]}.png"
        for i in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=ot.UA), timeout=60) as r:
                    b = r.read()
                tmp = f.with_suffix(".part")
                tmp.write_bytes(b)
                tmp.rename(f)
                return
            except Exception:
                __import__("time").sleep(1 + 2 * i)
    with ThreadPoolExecutor(32) as ex:
        for i, _ in enumerate(ex.map(get, todo)):
            if i % 5000 == 4999:
                print(f"    {i + 1}/{len(todo)}", flush=True)


_W: dict = {}


def _init(box):
    _W["clim"] = Climate(box)
    _W["towns"] = Towns()
    ot.terraclimate = lambda lat, lon: _W["clim"](lat, lon)
    ot._base = lambda lat, lon, cc: _W["towns"](lat, lon, cc)
    ot.pick_scene = lambda t: None  # dots only for now (Manu 2026-11-14): no drawings
    import build_trails as bt
    # the line is the whole route, start and goal are its ends: never clip it (a loop's start and
    # end are one point, and clipping between them left nothing), and never ask a web router to
    # close a gap (the OSM API forbids bulk use): a straight step is enough for the numbers
    bt.clip = lambda line, a, b: list(line)
    bt.route = lambda pts, how="auto": ([tuple(p[:2]) for p in pts], "line")


def _one(args):
    d, cc = args
    try:
        r = ot.build_one(d, cc, [], [])
    except Exception as e:
        return None, f"error {type(e).__name__}"
    if not r:
        return None, next(iter(ot.DROPS), "dropped") if ot.DROPS else "dropped"
    t, g = r
    ot.DROPS.clear()
    return (t, compact(g)), None


def stream(census: str):
    """The census rows one by one (pbf_routes.py writes one row a line): a continent is 1+ GB."""
    with open(census, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip().lstrip("[,").rstrip("]")
            if ln:
                yield json.loads(ln)


def build(census: str, region: str, *box) -> None:
    """census rows -> backend/app/trails/world/<cc>.json for every country of the region.
    Three passes over the census so a continent fits in memory: choose (no lines kept), fetch the
    terrain tiles, build in batches."""
    import os
    from multiprocessing import Pool
    box = tuple(float(x) for x in box)
    where = Where()
    light = []
    for d in stream(census):
        w, cc = why_not(d, where)
        if not w:
            light.append((d["length"], d["id"], ot._norm(d["name"]), round(d["bbox"][0], 2), cc,
                          (d.get("tags") or {}).get("wikidata")))
    light.sort(key=lambda x: -x[0])
    order, seen = {}, set()
    for n, (_, rid, nm, b0, cc, _) in enumerate(light):
        if (nm, b0) not in seen:
            seen.add((nm, b0))
            order[rid] = (n, cc)
    print(f"{region}: {len(order)} to build", flush=True)
    links = sitelinks(x[5] for x in light if x[1] in order)
    del light
    Climate(box)  # fetch once before the workers start
    Towns()
    prefetch(d["line"] for d in stream(census) if d["id"] in order)
    res: dict[int, tuple] = {}
    drops = Counter()
    batch: list = []

    def run(pool, batch):
        for (r, why), (d, cc) in zip(pool.imap(_one, batch, chunksize=8), batch):
            if r:
                r[0]["rank"] = route_rank(d, r[1]["km"], links)
                res[d["id"]] = (cc, r)
            else:
                drops[why] += 1
        print(f"  {len(res) + sum(drops.values())}/{len(order)} kept {len(res)}", flush=True)
    with Pool(int(os.environ.get("WORKERS", 4)), _init, (box,)) as pool:
        for d in stream(census):
            if d["id"] in order:
                batch.append((d, order[d["id"]][1]))
                if len(batch) >= 2000:
                    run(pool, batch)
                    batch = []
        if batch:
            run(pool, batch)
    per = defaultdict(list)
    for rid in sorted(res, key=lambda i: order[i][0]):
        cc, r = res[rid]
        per[cc].append(r)
    WORLD.mkdir(exist_ok=True)
    for cc, out in sorted(per.items()):
        ot.names([t for t, _ in out])
        doc = {"_doc": "World treks (generated by tools/trails/world_tail.py from OpenStreetMap, ODbL, and the "
                       "Copernicus DEM; never edit by hand). geo.enc: encoded polyline of lat, lon, metres.",
               "trails": [t for t, _ in out], "geo": {t["id"]: g for t, g in out}}
        (WORLD / f"{cc.lower()}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{region}: {len(res)} treks in {len(per)} countries; dropped {dict(drops)}")


WORLD = ot.ROOT / "backend/app/trails/world"
LEVELS = ["easy", "moderate", "hard", "technical"]


def rerank() -> None:
    """The ranks of the walks to a goal again, once Wikidata has answered (it throttles this host:
    run `WIKIDATA_PAUSE=60 python world_tail.py qids` first, slowly)."""
    links = json.loads((CACHE / "wikidata-sitelinks.json").read_text(encoding="utf-8"))
    for f in sorted(WORLD.glob("[a-z][a-z].json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        n = 0
        for t in doc["trails"]:
            if "-goal-" not in t["id"]:
                continue
            q = next((s.rsplit("/", 1)[1] for s in t["sources"] if "wikidata.org" in s), "")
            r = goal_rank({"wiki": q}, doc["geo"][t["id"]]["gain_m"] / 2, links)
            n += r != t.get("rank")
            t["rank"] = r
        if n:
            f.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"{f.stem}: {n} ranks changed")


def qids() -> None:
    """Look up the Wikipedia languages of every goal of the world files (slowly, see rerank)."""
    q = []
    for f in sorted(WORLD.glob("[a-z][a-z].json")):
        for t in json.loads(f.read_text(encoding="utf-8"))["trails"]:
            q += [s.rsplit("/", 1)[1] for s in t["sources"] if "wikidata.org" in s]
    sitelinks(q)


def dots() -> None:
    """world/_dots.json: one row per world trek for the globe, at its goal."""
    rows = []
    for f in sorted(WORLD.glob("[a-z][a-z].json")):
        for t in json.loads(f.read_text(encoding="utf-8"))["trails"]:
            g = next((p for p in reversed(t["points"]) if p["role"] == "goal"), t["points"][-1])
            rows.append([t["id"], t["name"], round(g["lat"], 4), round(g["lon"], 4), LEVELS.index(t["difficulty"]),
                         t["days"], t.get("rank", 1)])
    (WORLD / "_dots.json").write_text(json.dumps({"fields": ["id", "name", "lat", "lon", "level", "days", "rank"],
                                                  "dots": rows}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(rows)} dots; by rank {dict(sorted(Counter(r[6] for r in rows).items()))}")


# ---------------------------------------------------------------- walks to a goal (option C)

def _goal_job(w):
    import build_trails as bt
    import goal_walks as gw
    cc = w["cc"]
    line = [tuple(p) for p in w["line"]][::-1]  # road first
    kind = w["kind"]
    if kind != "lake" and bt.km(line[-1], (w["lat"], w["lon"])) > 0.02:
        line.append((w["lat"], w["lon"]))
    typ = "way" if kind == "lake" else "node"
    src = [f"https://www.openstreetmap.org/{typ}/{w['id']}"]
    if w.get("wiki"):
        src.append(f"https://www.wikidata.org/wiki/{w['wiki']}")
    via = next((v for v in w.get("via") or [] if gw._latin(v) and len(v) < 50), "")
    say = {"peak": "A footpath to the summit:", "pass": "A footpath to the pass:", "hut": "A footpath to the hut:",
           "lake": "A footpath to the lake:", "waterfall": "A footpath to the falls:",
           "viewpoint": "A footpath to the lookout:", "glacier": "A footpath to the glacier:"}
    try:
        r = gw.build_walk(cc, line, gw.goal_name(w, _W.get("labels", {})), kind, w.get("ele"), w.get("sac") or 0,
                          src, f"{cc.lower()}-goal-{w['id']}", say[kind], via=via)
    except Exception as e:
        return None, f"error {type(e).__name__}"
    if not r:
        why = next(iter(gw.DROPS), "dropped")
        gw.DROPS.clear()
        return None, why
    t, g = r
    return (t, compact(g)), None


def _ginit(box, labels):
    _init(box)
    _W["labels"] = labels


def goals(region: str, *files_and_box) -> None:
    """pbf_paths.js walks -> added to backend/app/trails/world/<cc>.json, the same rules as
    goal_walks.osm (2-25 km, 150 m up to a peak, pass or lookout, not where a trek already goes)."""
    import goal_walks as gw
    from multiprocessing import Pool
    box, files = tuple(float(x) for x in files_and_box[-4:]), files_and_box[:-4]
    where = Where()
    # what the world's routes already reach: their start, top and end, by 0.1-degree cell
    taken = defaultdict(list)
    for f in WORLD.glob("[a-z][a-z].json"):
        for t in json.loads(f.read_text(encoding="utf-8"))["trails"]:
            if "-goal-" in t["id"]:
                continue
            for p in t["points"]:
                taken[(round(p["lat"], 1), round(p["lon"], 1))].append((p["lat"], p["lon"]))

    def near_taken(p, km):
        import build_trails as bt
        for a in (-0.1, 0, 0.1):
            for b in (-0.1, 0, 0.1):
                for q in taken.get((round(p[0] + a, 1), round(p[1] + b, 1)), ()):
                    if bt.km(p, q) < km:
                        return True
        return False
    keep, why, kept_cells = [], Counter(), defaultdict(list)
    for f in files:
        walks = json.loads(Path(f).read_text(encoding="utf-8"))["walks"]
        for w in sorted(walks, key=lambda w: (-bool(w.get("wiki")), -(w.get("ele") or 0), -w["km"])):
            p = (w["lat"], w["lon"])
            nm = ot._norm(w.get("en") or w["name"]) or w["name"]
            if gw.GENERIC.match(nm) or gw.NOT_A_GOAL.search(w["name"] + " " + (w.get("en") or "")):
                why["generic name"] += 1
                continue
            if w["km"] < gw.MIN_KM or w["km"] > gw.MAX_KM:
                why["shorter than 2 or longer than 25 km"] += 1
                continue
            cc = where(w["lon"], w["lat"])
            if not cc or cc in DONE:
                why["8 countries or at sea"] += 1
                continue
            if near_taken(p, 1.5):
                why["a trek reaches it"] += 1
                continue
            cell = kept_cells[(round(p[0], 1), round(p[1], 1))]
            import build_trails as bt
            if any(bt.km(p, q) < 1.0 for q in cell):
                why["same goal"] += 1
                continue
            cell.append(p)
            keep.append({**w, "cc": cc})
    print(f"{region}: {len(keep)} walks to build; dropped {dict(why)}", flush=True)
    labels = gw.wikidata_labels([w.get("wiki") for w in keep])
    links = sitelinks(w.get("wiki") for w in keep)
    prefetch(w["line"] for w in keep)
    per, drops = defaultdict(list), Counter()
    with Pool(int(__import__("os").environ.get("WORKERS", 4)), _ginit, (box, labels)) as pool:
        for n, ((r, bad), w) in enumerate(zip(pool.imap(_goal_job, keep, chunksize=8), keep)):
            if r:
                r[0]["rank"] = goal_rank(w, r[1]["gain_m"] / 2, links)
                per[w["cc"]].append(r)
            else:
                drops[bad] += 1
            if n % 2000 == 1999:
                print(f"  {n + 1}/{len(keep)} kept {sum(map(len, per.values()))}", flush=True)
    for cc, out in sorted(per.items()):
        f = WORLD / f"{cc.lower()}.json"
        doc = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {
            "_doc": "World treks (generated by tools/trails/world_tail.py; never edit by hand).", "trails": [], "geo": {}}
        doc["trails"] = [t for t in doc["trails"] if "-goal-" not in t["id"]]
        doc["geo"] = {k: v for k, v in doc["geo"].items() if "-goal-" not in k}
        gw.dedupe([t for t, _ in out])
        doc["trails"] += [t for t, _ in out]
        doc["geo"].update({t["id"]: g for t, g in out})
        f.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{region}: {sum(map(len, per.values()))} walks to a goal in {len(per)} countries; dropped {dict(drops)}")

if __name__ == "__main__":
    cmd, *a = sys.argv[1:]
    {"count": count, "build": build, "goals": goals, "dots": dots, "rerank": rerank, "qids": qids}[cmd](*a)
