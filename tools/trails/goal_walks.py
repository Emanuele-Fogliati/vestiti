"""Walks to a goal (Manu, 2026-11-14, option C): the footpaths of OpenStreetMap from the road to a
named peak, pass, hut, lake, waterfall or lookout, and the walking tracks of New Zealand's
Department of Conservation. Generated like tier B (osm_tail.py) and never edited by hand.

Where we draw the line:
- OSM: the shortest walk on footpaths (path, footway, steps, bridleway; 4x4 tracks count as road)
  from the goal to the first road, 2-25 km one way; a peak, pass or lookout needs 150 m of climb;
  the goal lies in the country and no trek of the app already reaches it (1.5 km).
- DOC NZ: open, public walking and tramping tracks and routes of 2 km or more that are not a
  Great Walk, a cycle track or a pavement, and that no trek of the app already covers.

Steps (run from the repo root):
  node --max-old-space-size=13000 tools/trails/pbf_paths.js <cc>.osm.pbf tools/trails/.cache/walks-<cc>.json
  python tools/trails/goal_walks.py osm IS PE CL AR VN NA JP     # -> backend/app/trails/tail/<cc>-goals.json
  python tools/trails/goal_walks.py doc NZ                       # -> backend/app/trails/tail/nz-doc.json

Open data only: OpenStreetMap extracts (ODbL; openstreetmap.fr and geo2day country extracts), DOC
Tracks open data (CC-BY 4.0, Department of Conservation), Wikidata labels (CC0), the Copernicus
DEM terrain tiles, TerraClimate (CC0).
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import build_trails as bt
import osm_tail as ot

CACHE = ot.CACHE
OUT = ot.OUT
MIN_KM, MAX_KM, MIN_GAIN = 2.0, 25.0, 150
DOC_API = ("https://services1.arcgis.com/3JjYDyG3oajxU6HO/arcgis/rest/services/DOC_Tracks_Open_Data/"
           "FeatureServer/0/query")
KIND = {"peak": "summit", "pass": "pass", "hut": "hut", "lake": "lake", "waterfall": "waterfall",
        "viewpoint": "lookout", "glacier": "glacier"}
HAS_KIND = re.compile(r"\b(mount|mt|cerros?|volc[aá]n|nevados?|picos?|monte|peaks?|summit|hill|lakes?|lagos?|lagunas?|lagunillas?|"
                      r"tarns?|hut|refugio|biv|bivouac|falls?|saltos?|cascadas?|waterfall|pass|paso|portezuelo|saddle|morro|"
                      r"col|mirador|lookout|viewpoint|glacier|glaciar|fjall|fell|vatn|foss|skar[ðd])\b|"
                      r"(fjall|fell|vatn|foss|tindur|jokull|jökull|hnúkur|hnukur|山|岳|峰|岳|峠|池|湖|沼|滝|小屋|ヶ岳)$",
                      re.I)
GENERIC = re.compile(r"^(the |la |el |los |las )?(pool|dam|lake|lagoon|laguna|lago|lagunita|reservoir|pond|tank|tarn|mirador|viewpoint|"
                     r"view ?point|lookout|cascada|waterfall|falls|salto|cerro|hill|peak|summit|hut|refugio|estanque|"
                     r"tranque|embalse|puesto|cumbre|cima|punto panoramico|vista|[a-z]?\d+[a-z]?)( \d+)?$", re.I)
NOT_A_GOAL = re.compile(r"reservoir|embalse|tranque|represa|\bdam\b|pond|tailings|relave|sewage|ダム|貯水池|調整池|"
                        r"遊水|浄水|沈殿|tank|piscina|pileta|antena|antenna|tower|torre|cross|cruz", re.I)
DROPS = Counter()
UA = {"User-Agent": "ThruwearArtBot/1.0 (reference only)"}


def _get(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def wikidata_labels(qids: list[str]) -> dict[str, str]:
    """English labels of Wikidata items (CC0), cached."""
    f = CACHE / "wikidata-labels.json"
    have = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    todo = sorted({q for q in qids if re.fullmatch(r"Q\d+", q or "") and q not in have})
    for i in range(0, len(todo), 50):
        ids = "|".join(todo[i:i + 50])
        d = None
        for k in range(6):
            try:
                d = _get(f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={ids}&props=labels&languages=en&format=json")
                break
            except Exception as e:  # Wikimedia answers 429 to this container now and then
                time.sleep(8 * (k + 1))
        if d is None:
            print("  wikidata failed: labels left out")
            break
        time.sleep(1)
        for q, e in d.get("entities", {}).items():
            have[q] = (e.get("labels", {}).get("en") or {}).get("value", "")
    f.write_text(json.dumps(have, ensure_ascii=False), encoding="utf-8")
    return have


def _latin(s: str) -> bool:
    return bool(s) and not ot.CJK.search(s) and bool(re.search(r"[A-Za-z]", s))


def goal_name(w: dict, labels: dict) -> str:
    """The goal in English letters: name:en or a romanised name, the Wikidata label, else the name."""
    for n in (w.get("en"), labels.get(w.get("wiki") or ""), w["name"]):
        if n and _latin(n):
            return n.strip()
    return w["name"].strip()


def trek_name(goal: str, kind: str, base: str) -> str:
    if ot.CJK.search(goal):
        return f"{KIND[kind].capitalize()} near {base} ({goal})"[:80]
    if HAS_KIND.search(goal):
        return goal[:80]
    return f"{goal} {KIND[kind]}"[:80]


def _taken(cc: str) -> list[tuple[float, float]]:
    from app import trails
    return [(p.lat, p.lon) for t in trails.trails() if t.country == cc for p in t.points]


def _near(pts, p, km) -> bool:
    return any(abs(a - p[0]) < km / 80 and abs(b - p[1]) < km / 60 and bt.km((a, b), p) < km for a, b in pts)


def build_walk(cc: str, line: list, gname: str, kind: str, ele, sac: int, src: list[str], tid: str,
               why_kind: str, region: str = "", via: str = "") -> tuple[dict, dict] | None:
    """One walk from the road (line[0]) to the goal (line[-1]), there and back."""
    start, end = line[0], line[-1]
    base = ot._base(start[0], start[1], cc)
    if not base:
        DROPS["no base"] += 1
        return None
    if len(gname) < 3:
        gname = f"{gname} ({KIND[kind]})"  # a two-letter Japanese name
    gpt = {"id": "goal", "name": gname[:80], "lat": end[0], "lon": end[1], "role": "goal"}
    pts = [{"id": "start", "name": "Trailhead", "lat": start[0], "lon": start[1], "role": "start"}, gpt]
    t = {"id": tid, "name": trek_name(gname, kind, base["name"]), "country": cc, "base": base["name"][:60],
         "region": region[:100], "kind": "day", "days": 1, "shape": "out_and_back", "router": "auto",
         "points": pts, "tier": "B"}
    real, real_ele = bt.from_osm, bt.elevations
    bt.from_osm = lambda rel: line
    bt.elevations = bt.tile_elevations
    t["osm"] = 1  # build() reads the line through from_osm
    try:
        g = bt.build(t)
    finally:
        bt.from_osm, bt.elevations = real, real_ele
        t.pop("osm")
    g["id"] = tid
    gain_up = g["gain_m"] / 2  # there and back
    if kind in ("peak", "pass", "viewpoint") and gain_up < MIN_GAIN:
        DROPS["flat"] += 1
        return None
    if ele:
        gpt["name"] = f"{gname}, {round(ele):,} m"[:80]
    h = g["walk_hours"]
    days = 1 if h <= 10 else max(2, math.ceil(h / 7))
    t.update({
        "kind": "multiday" if days > 1 else "day", "days": min(days, 21),
        "difficulty": ot._difficulty(sac, h, g["gain_m"], g["max_m"]),
        "months": ot._months(start[0], start[1], g["max_m"], cc, g["min_m"]),
        "hours": [max(0.5, round(h * 0.85 * 2) / 2), max(0.5, round(h * 1.15 * 2) / 2)],
        "why": (f"{why_kind} {g['one_way_km']:.1f} km each way, +{round(gain_up):,} m, up to {g['max_m']:,} m, "
                f"from near {base['name']}{(' along ' + via) if via else ''}.")[:300],
        "sources": src,
    })
    ot.pick_scene(t)
    t["scores"] = ot.scores(t["name"], g, t["days"], h, any(p.get("scene") for p in pts),
                            bt.km(start, (base["lat"], base["lon"])) < 2)
    return t, g


def zone(t: dict) -> None:
    """No drawing of its own goal: the nearest drawing of its zone within 30 km (as one-way stages)."""
    from app import art
    end = t["points"][-1]
    d, lm = min(((bt.km((end["lat"], end["lon"]), (m.lat, m.lon)), m) for m in art.landmarks()
                 if m.country == t["country"]), default=(999, None), key=lambda x: x[0])
    if lm and d <= ot.ZONE_KM:
        end["scene"] = lm.id


def dedupe(trails: list[dict]) -> None:
    """Two walks with one name are told apart by their base town, then by a number
    (osm_tail.names() would wrap the Japanese names a second time)."""
    seen = Counter(t["name"] for t in trails)
    for t in trails:
        if seen[t["name"]] > 1 and t["base"] not in t["name"]:
            t["name"] = f"{t['name']} near {t['base']}"[:80]
    seen = Counter()
    for t in trails:
        seen[t["name"]] += 1
        if seen[t["name"]] > 1:
            t["name"] = f"{t['name']} ({seen[t['name']]})"[:80]


def _write(cc: str, name: str, out: list, doc: str) -> None:
    dedupe([t for t, _ in out])
    body = {"_doc": doc, "trails": [t for t, _ in out], "geo": {t["id"]: g for t, g in out}}
    (OUT / f"{name}.json").write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{cc}: {len(out)} walks written to {name}.json; dropped {dict(DROPS)}")
    DROPS.clear()


def _prefetch_climate(starts: list[tuple[float, float]]) -> None:
    """Fetch the TerraClimate cells of all trailheads in parallel, then write the cache once
    (the builds then run one by one: the DEM tile cache is not thread-safe)."""
    ot.terraclimate(*starts[0]) if starts else None  # loads the cache
    cells = {}
    for la, lo in starts:
        cells.setdefault(f"{int((90 - la) * 24)},{int((lo + 180) * 24)}", (la, lo))
    todo = [(k, p) for k, p in cells.items() if k not in ot._tc_cache]
    print(f"  climate: {len(todo)} new cells", flush=True)

    def one(kp):
        k, (la, lo) = kp
        la_i, lo_i = map(int, k.split(","))
        try:
            v = {n: ot._tc_var(n, f"climatology/TerraClimate_19912020_{n}.nc", la_i, lo_i) for n in ("tmin", "tmax", "ppt", "vap")}
            ele = ot._tc_var("elevation", "layers/terraclim_dem.nc", la_i, lo_i, months=False)
        except Exception:
            return k, "fail"
        if len(v["tmax"]) != 12 or not ele or any(abs(x) > 1000 for x in v["tmax"]):
            return k, None
        return k, [[[round(v["tmin"][m], 1), round(v["tmax"][m], 1), round(v["ppt"][m]), round(v["vap"][m], 3)]
                    for m in range(12)], round(ele[0])]
    with ThreadPoolExecutor(8) as ex:
        for k, r in ex.map(one, todo):
            if r != "fail":
                ot._tc_cache[k] = r
    (CACHE / "terraclimate.json").write_text(json.dumps(ot._tc_cache))


def _run(jobs, fn, starts):
    _prefetch_climate(starts)
    out = []
    for n, j in enumerate(jobs):
        r = ot._safe(fn, *j)
        if r:
            out.append(r)
        if n % 100 == 99:
            print(f"  {n + 1}/{len(jobs)}", flush=True)
    return out


# ---------------------------------------------------------------- OSM goals

def osm(cc: str) -> None:
    from shapely.geometry import Point
    inside = ot._shapes()[cc]
    walks = json.loads((CACHE / f"walks-{cc.lower()}.json").read_text(encoding="utf-8"))["walks"]
    taken = _taken(cc)
    keep: list[dict] = []
    for w in sorted(walks, key=lambda w: (-bool(w.get("wiki")), -(w.get("ele") or 0), -w["km"])):
        p = (w["lat"], w["lon"])
        nm = ot._norm(w.get("en") or w["name"]) or w["name"]
        why = ("generic name" if GENERIC.match(nm) or NOT_A_GOAL.search(w["name"] + " " + (w.get("en") or "")) else
               "abroad" if not inside.contains(Point(w["lon"], w["lat"])) else
               "short" if w["km"] < MIN_KM else "long" if w["km"] > MAX_KM else
               "a trek reaches it" if _near(taken, p, 1.5) else
               "same goal" if _near([(k["lat"], k["lon"]) for k in keep], p, 1.0) else None)
        if why:
            DROPS[why] += 1
        else:
            keep.append(w)
    labels = wikidata_labels([w.get("wiki") for w in keep])
    say = {"peak": "A footpath to the summit:", "pass": "A footpath to the pass:", "hut": "A footpath to the hut:",
           "lake": "A footpath to the lake:", "waterfall": "A footpath to the falls:",
           "viewpoint": "A footpath to the lookout:", "glacier": "A footpath to the glacier:"}

    def one(w):
        line = [tuple(p) for p in w["line"]][::-1]  # road first
        kind = w["kind"]
        if kind != "lake" and bt.km(line[-1], (w["lat"], w["lon"])) > 0.02:
            line.append((w["lat"], w["lon"]))  # the last steps off the mapped path, to the goal itself
        kind = w["kind"]
        typ = "way" if kind == "lake" else "node"
        src = [f"https://www.openstreetmap.org/{typ}/{w['id']}"]
        if w.get("wiki"):
            src.append(f"https://www.wikidata.org/wiki/{w['wiki']}")
        via = next((v for v in w.get("via") or [] if _latin(v) and len(v) < 50), "")
        return build_walk(cc, line, goal_name(w, labels), kind, w.get("ele"), w.get("sac") or 0, src,
                          f"{cc.lower()}-goal-{w['id']}", say[kind], via=via)
    out = _run([(w,) for w in keep], one, [tuple(w['line'][-1]) for w in keep])
    _write(cc, f"{cc.lower()}-goals", out,
           "Walks to a goal (generated by tools/trails/goal_walks.py from OpenStreetMap, ODbL, and the "
           "Copernicus DEM; never edit by hand).")


# ---------------------------------------------------------------- DOC New Zealand

DOC_WORDS = [(r"\bTk\b\.?", "Track"), (r"\bRte\b", "Route"), (r"\bJct\b", "Junction"), (r"\bRd\b", "Road"),
             (r"\bMt\b", "Mount"), (r"\bSt\b", "Stream"), (r"\bCk\b", "Creek"), (r"\bR\b", "River"),
             (r"\bVly\b", "Valley"), (r"\bBiv\b", "Bivvy"), (r"\bPk\b", "Peak"), (r"\bCa\b", "Carpark"),
             (r"\bW/Way\b", "Walkway"), (r"(?<=\w) To (?=\w)", " to ")]


def doc_name(s: str) -> str:
    s = re.sub(r"^T\d+\s*[:-]\s*", "", s or "").strip()
    s = re.sub(r"\s*\(.*$", "", s)
    for a, b in DOC_WORDS:
        s = re.sub(a, b, s)
    s = re.sub(r"\s+", " ", s).strip(" -/")
    if s and not re.search(r"\b(Track|Route|Walk|Walkway|Trail|Circuit|Loop|Path)\b", s, re.I):
        s += " Track"
    return s


def _char(a: dict, name: str):
    for i in range(2, 16):
        if a.get(f"CharName{i}") == name:
            return a.get(f"CharValue{i}")
    return None


def doc(cc: str = "NZ") -> None:
    f = CACHE / "doc-tracks.json"
    if not f.exists():
        feats = []
        for off in range(0, 10000, 2000):
            q = urllib.parse.urlencode({"where": "1=1", "outFields": "*", "outSR": 4326, "resultOffset": off,
                                        "resultRecordCount": 2000, "f": "json"})
            page = _get(f"{DOC_API}?{q}")["features"]
            feats += page
            if len(page) < 2000:
                break
        f.write_text(json.dumps(feats), encoding="utf-8")
    feats = json.loads(f.read_text(encoding="utf-8"))
    from app import trails
    taken = _taken(cc)
    names_ex = {ot._norm(t.name) for t in trails.trails() if t.country == cc}
    jobs, seen = [], set()
    for ft in feats:
        a = ft["attributes"]
        typ, name = a.get("SubObjectType"), doc_name(a.get("TechObjectName") or "")
        why = ("type" if typ in (None, "Cycle Track", "Pavement", "Short Walk (disabled)", "Great Walk") else
               "closed" if _char(a, "USER_STATUS") != "OPEN" or _char(a, "PUBLIC_USE") == "No" else
               "bike" if re.search(r"bike|mtb|cycle", name, re.I) else
               "no name" if len(name) < 4 else
               "short" if a["Shape__Length"] < MIN_KM * 1000 else
               "same name" if ot._norm(name) in names_ex or ot._norm(name) in seen else None)
        paths = (ft.get("geometry") or {}).get("paths") or []
        line = _join([[(y, x) for x, y in p] for p in paths])
        if not why and (len(line) < 2 or (_near(taken, line[0], 1.0) and _near(taken, line[-1], 1.0))):
            why = "a trek covers it"
        if why:
            DROPS[why] += 1
            continue
        seen.add(ot._norm(name))
        jobs.append((name, typ, line, a))

    def one(name, typ, line, a):
        samp = bt.resample(line, 0.05)
        ele = bt.smooth(bt.tile_elevations(samp))
        if ele[0] > ele[-1]:  # walk it up
            line, ele = line[::-1], ele[::-1]
        loop = bt.km(line[0], line[-1]) < 0.5
        sac = 3 if typ == "Route" else 2 if typ == "Tramping Track" else 1
        dur = _char(a, "WEB_WALKING_DURATION") or ""
        src = ["https://www.doc.govt.nz/parks-and-recreation/things-to-do/walking-and-tramping/",
               "https://data-doc.opendata.arcgis.com/"]
        what = {"Route": "A DOC route (unformed, for experienced trampers):",
                "Tramping Track": "A DOC tramping track:", "Easy Tramping Track": "A DOC easy tramping track:",
                "Walking Track": "A DOC walking track:", "Short Walk": "A DOC short walk:"}[typ]
        tid = f"nz-doc-{a['OBJECTID']}"
        if loop:
            return _doc_loop(cc, name, line, sac, src, tid, what, dur)
        r = build_walk(cc, line, name, "hut" if re.search(r"hut|biv", name, re.I) else "peak", None, sac, src,
                       tid, what, region=dur)
        if r:
            r[0]["name"] = name[:80]
            r[0]["points"][-1]["name"] = "End of the track"
            r[0]["region"] = ""
        return r
    out = _run(jobs, one, [j[2][0] for j in jobs] + [j[2][-1] for j in jobs])
    _write(cc, "nz-doc", out,
           "DOC walking and tramping tracks (generated by tools/trails/goal_walks.py from the Department of "
           "Conservation's open data, CC-BY 4.0, and the Copernicus DEM; never edit by hand).")


def _doc_loop(cc, name, line, sac, src, tid, what, dur):
    base = ot._base(line[0][0], line[0][1], cc)
    if not base:
        DROPS["no base"] += 1
        return None
    far = max(line, key=lambda p: bt.km(p, line[0]))
    pts = [{"id": "start", "name": "Trailhead", "lat": line[0][0], "lon": line[0][1], "role": "start"},
           {"id": "goal", "name": "Back at the start", "lat": line[-1][0], "lon": line[-1][1], "role": "goal"}]
    t = {"id": tid, "name": name[:80], "country": cc, "base": base["name"][:60], "region": "", "kind": "day",
         "days": 1, "shape": "loop", "router": "auto", "points": pts, "tier": "B", "osm": 1}
    real, real_ele = bt.from_osm, bt.elevations
    bt.from_osm, bt.elevations = (lambda rel: line), bt.tile_elevations
    try:
        g = bt.build(t)
    finally:
        bt.from_osm, bt.elevations = real, real_ele
        t.pop("osm")
    g["id"] = tid
    h = g["walk_hours"]
    t.update({"difficulty": ot._difficulty(sac, h, g["gain_m"], g["max_m"]),
              "months": ot._months(line[0][0], line[0][1], g["max_m"], cc, g["min_m"]),
              "hours": [max(0.5, round(h * 0.85 * 2) / 2), max(0.5, round(h * 1.15 * 2) / 2)],
              "why": f"{what} a loop of {g['km']:.1f} km, +{g['gain_m']:,} m, up to {g['max_m']:,} m, from near {base['name']}."[:300],
              "sources": src})
    if h > 10:
        t["days"] = max(2, math.ceil(h / 7))
        t["kind"] = "multiday"
    ot.pick_scene(t)
    t["scores"] = ot.scores(name, g, t["days"], h, any(p.get("scene") for p in pts),
                            bt.km(line[0], (base["lat"], base["lon"])) < 2)
    return t, g


def _join(parts: list[list]) -> list:
    """The parts of a DOC track in walking order (each part is turned to meet the line so far)."""
    parts = [p for p in parts if len(p) >= 2]
    if not parts:
        return []
    line = list(parts.pop(0))
    while parts:
        best = min(range(len(parts)), key=lambda i: min(bt.km(line[-1], parts[i][0]), bt.km(line[-1], parts[i][-1]),
                                                       bt.km(line[0], parts[i][0]), bt.km(line[0], parts[i][-1])))
        p = parts.pop(best)
        d = [bt.km(line[-1], p[0]), bt.km(line[-1], p[-1]), bt.km(line[0], p[-1]), bt.km(line[0], p[0])]
        k = d.index(min(d))
        if min(d) > 0.5:
            continue  # a stray piece far from the rest
        line = line + p if k == 0 else line + p[::-1] if k == 1 else p + line if k == 2 else p[::-1] + line
    return line


if __name__ == "__main__":
    sys.path.insert(0, str(ot.ROOT / "backend"))
    cmd, *ccs = sys.argv[1:]
    for c in ccs:
        {"osm": osm, "doc": doc}[cmd](c.upper())
