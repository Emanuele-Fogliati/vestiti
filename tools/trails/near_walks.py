"""Walks near every drawn place of the app (Manu, 2026-11-15): the traveller plans the days on foot
around the places they already visit, not the 90,000 trails of Europe nobody opens.

Two kinds, both tier B, generated, never written by hand:
- city walks (`style: city`) in every drawn city and town outside the 8 trekking countries (those
  have theirs since 2026-11-14, tools/trails/city_walks.py): the same chains of famous sights, but
  the sights come from Wikidata (CC0) around the town instead of a country's OSM extract;
- short walks to a drawn sight (a waterfall, a lookout, a temple on a hill) from the nearest road a
  car reaches, when the walk takes 10 to 45 minutes each way on mapped paths.

  python3 tools/trails/near_walks.py bases          # drawn cities/towns -> .cache/near-bases.json
  python3 tools/trails/near_walks.py sights         # Wikidata sights around each (cached)
  python3 tools/trails/near_walks.py city [CC ...]  # -> backend/app/trails/tail/<cc>-city.json

Sources: Wikidata (CC0) for the sights and their fame (Wikipedia languages), GeoNames (CC-BY) for
people, the FOSSGIS OSRM foot router on OpenStreetMap (ODbL) for the line, the Copernicus DEM and
TerraClimate (CC0) for climb and months. Never AllTrails, Komoot, Wikiloc or Outdooractive.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))
sys.path.insert(0, str(HERE))

import build_trails as bt  # noqa: E402
import osm_tail as ot  # noqa: E402

CACHE = ot.CACHE
DONE = {"PE", "CL", "AR", "IS", "VN", "JP", "NA", "NZ"}  # their city walks: tools/trails/city_walks.py
UA = {"User-Agent": "trip-planner-open-data/1.0 (walks near sights; Wikidata CC0)", "Accept": "application/json"}
WDQS = "https://query.wikidata.org/sparql"


def geonames() -> list:
    """GeoNames places of 1,000+ people (CC-BY 4.0), the whole world: [name, lat, lon, cc, pop]."""
    f = CACHE / "geonames-world.json"
    if not f.exists():
        CACHE.mkdir(exist_ok=True)
        raw = urllib.request.urlopen("https://download.geonames.org/export/dump/cities1000.zip", timeout=300).read()
        txt = zipfile.ZipFile(io.BytesIO(raw)).read("cities1000.txt").decode("utf-8")
        rows = [[r[1], round(float(r[4]), 5), round(float(r[5]), 5), r[8], int(r[14] or 0)]
                for r in csv.reader(io.StringIO(txt), delimiter="\t", quoting=csv.QUOTE_NONE) if r[6] == "P"]
        f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return json.loads(f.read_text(encoding="utf-8"))


def bases() -> list[dict]:
    """The drawn cities and towns outside the 8 countries, with their people, radius and number of
    walks by the rules of city_walks.bases (a quarter of a bigger city walks its own streets only)."""
    from app import globe
    grid: dict[tuple[int, int], list] = {}
    for t in geonames():
        grid.setdefault((int(t[1] * 10), int(t[2] * 10)), []).append(t)
    out = []
    for p in globe.by_id().values():
        if not p.get("art") or p["kind"] not in ("city", "town") or p["country"] in DONE:
            continue
        a, b = int(p["lat"] * 10), int(p["lon"] * 10)
        pop = max([t[4] for i in (-1, 0, 1) for j in (-1, 0, 1) for t in grid.get((a + i, b + j), ())
                   if t[3] == p["country"] and bt.km((t[1], t[2]), (p["lat"], p["lon"])) <= 6] or [0])
        city = p["kind"] == "city"
        r, n = ((15, 10) if pop >= 5_000_000 else (10, 8) if pop >= 1_000_000 else (6, 4) if pop >= 300_000
                else (4, 3) if city else (2.5, 1))
        out.append({"id": p["id"], "name": p["name"], "cc": p["country"], "lat": p["lat"], "lon": p["lon"],
                    "city": city, "pop": pop, "radius": r, "walks": n})
    out.sort(key=lambda b: (-b["pop"], -b["city"]))
    for i, b in enumerate(out):
        if any(a["cc"] == b["cc"] and bt.km((a["lat"], a["lon"]), (b["lat"], b["lon"])) <= a["radius"]
               for a in out[:i] if not a.get("quarter")):
            b["quarter"] = True
            b["radius"], b["walks"] = 2.0, 2
    (CACHE / "near-bases.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(out)} bases, {sum(b.get('quarter', False) for b in out)} quarters, "
          f"{sum(b['walks'] for b in out)} walks at most")
    return out


AROUND = """ { SERVICE wikibase:around { ?i wdt:P625 ?c . bd:serviceParam wikibase:center "Point(%f %f)"^^geo:wktLiteral .
    bd:serviceParam wikibase:radius "%s" . } ?i wikibase:sitelinks ?n . FILTER(?n >= %d) }"""
QUERY = "SELECT DISTINCT ?i ?n ?c ?t WHERE { { %s } OPTIONAL { ?i wdt:P31 ?t } }"
_last = [0.0]


def minn(r: float) -> int:
    """3+ Wikipedia languages, more in a big city (its walks keep only the famous sights anyway)."""
    return 3 if r < 6 else 6 if r < 10 else 10


def wdqs(circles: list[tuple[float, float, float]]) -> list[dict]:
    """Wikidata items within any of the circles (lat, lon, km): [{wiki, n, lat, lon, types}].
    The query service allows one request a minute (2026-11): many towns go in one UNION."""
    q = QUERY % " UNION ".join(AROUND % (lon, lat, r, minn(r)) for lat, lon, r in circles)
    data = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
    for i in range(4):
        time.sleep(max(0.0, _last[0] + 62 - time.time()))
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(WDQS, data=data, headers=UA), timeout=75) as f:
                rows = json.load(f)["results"]["bindings"]
            break
        except Exception as e:
            print(f"    wdqs try {i + 1}: {str(e)[:120]}", flush=True)
            if i == 3 or "429" not in str(e):
                raise
    out: dict[str, dict] = {}
    for b in rows:
        m = re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", b["c"]["value"])
        if not m:
            continue
        k = b["i"]["value"].rsplit("/", 1)[1]
        r = out.setdefault(k, {"wiki": k, "n": int(b["n"]["value"]), "lat": round(float(m.group(2)), 5),
                               "lon": round(float(m.group(1)), 5), "types": []})
        t = b.get("t", {}).get("value", "").rsplit("/", 1)[-1]
        if t and t not in r["types"]:
            r["types"].append(t)
    return list(out.values())


def fetch_sights(budget: float = 700.0) -> None:
    """All bases in UNION batches of about `budget` km2; a batch that fails is split in two."""
    bs = json.loads((CACHE / "near-bases.json").read_text(encoding="utf-8"))
    f = CACHE / "near-sights.json"
    have = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"done": [], "items": {}}
    todo = [b for b in sorted(bs, key=lambda b: b["radius"]) if b["id"] not in set(have["done"])]
    batches, cur = [], []
    for b in todo:
        if cur and sum(x["radius"] ** 2 for x in cur) + b["radius"] ** 2 > budget:
            batches.append(cur)
            cur = []
        cur.append(b)
    batches += [cur] if cur else []
    print(f"{len(todo)} bases to fetch in {len(batches)} queries", flush=True)
    while batches:
        bt_ = batches.pop(0)
        try:
            rows = wdqs([(b["lat"], b["lon"], b["radius"]) for b in bt_])
        except Exception:
            if len(bt_) == 1:
                print(f"  {bt_[0]['id']}: failed, skipped", flush=True)
                continue
            batches[:0] = [bt_[:len(bt_) // 2], bt_[len(bt_) // 2:]]
            continue
        for r in rows:
            have["items"][r["wiki"]] = r
        have["done"] += [b["id"] for b in bt_]
        f.write_text(json.dumps(have, ensure_ascii=False), encoding="utf-8")
        print(f"  {len(have['done'])}/{len(bs)} bases, {len(have['items'])} items (+{len(rows)}), "
              f"{len(batches)} queries left", flush=True)


LABELS = """SELECT ?i ?l ?d ?m WHERE { VALUES ?i { %s }
  OPTIONAL { ?i rdfs:label ?l FILTER(LANG(?l) = "en") }
  OPTIONAL { ?i schema:description ?d FILTER(LANG(?d) = "en") }
  OPTIONAL { ?i rdfs:label ?m FILTER(LANG(?m) = "mul") } }"""


def labels(qids, chunk: int = 4000) -> dict[str, list[str]]:
    """[English label, English description, 'mul' label] of Wikidata items (CC0), cached. Through the
    query service, a few thousand items a request (the Wikidata API answered 429 to everything, 2026-11)."""
    f = CACHE / "near-labels.json"
    have = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    todo = sorted({q for q in qids if q not in have})
    for i in range(0, len(todo), chunk):
        ids = todo[i:i + chunk]
        data = urllib.parse.urlencode({"query": LABELS % " ".join(f"wd:{q}" for q in ids), "format": "json"}).encode()
        for k in range(4):
            time.sleep(max(0.0, _last[0] + 62 - time.time()))
            _last[0] = time.time()
            try:
                with urllib.request.urlopen(urllib.request.Request(WDQS, data=data, headers=UA), timeout=75) as r:
                    rows = json.load(r)["results"]["bindings"]
                break
            except Exception as e:
                print(f"    labels try {k + 1}: {str(e)[:100]}", flush=True)
                if k == 3:
                    raise
        for q in ids:
            have.setdefault(q, ["", "", ""])
        for b in rows:
            q = b["i"]["value"].rsplit("/", 1)[1]
            h = have[q]
            for n, key in enumerate(("l", "d", "m")):
                if key in b and not h[n]:
                    h[n] = b[key]["value"]
        f.write_text(json.dumps(have, ensure_ascii=False), encoding="utf-8")
        print(f"  labels {min(i + chunk, len(todo))}/{len(todo)}", flush=True)
    return have


# A sight is an item whose class (Wikidata P31, by its English name) is a place you walk to and look
# at; a class of the second list (a school, a station, a district, a person, an event) rules it out.
SIGHT = re.compile(
    r"church|cathedral|basilica|chapel|abbey|priory|monastery|convent|temple|shrine|pagoda|stupa|mosque|"
    r"synagogue|madrasa|museum|gallery|palace|castle|ch[aâ]teau|fort\b|fortress|citadel|kasbah|tower|gate|"
    r"bridge|square|plaza|piazza|park\b|garden|monument|memorial|statue|sculpture|fountain|market|bazaar|souk|"
    r"ruin|archaeological|amphitheat|theat(re|er)|opera|concert hall|mausoleum|tomb|necropolis|cemetery|"
    r"lighthouse|viewpoint|lookout|beach|waterfall|harbou?r|pier|promenade|old town|historic|heritage|landmark|"
    r"skyscraper|observation|aqueduct|city wall|walls|obelisk|triumphal arch|baths|forum|villa|manor|residence|"
    r"hall\b|town hall|city hall|cloister|minaret|belfry|clock tower|bell tower|mansion|pavilion|zoo|aquarium|"
    r"botanical|arch\b|stairway|steps|hill\b|island|lake|canal|historic district|old quarter|wat\b|"
    r"capitol|parliament building|library building|opera house|chorten|gompa|dzong|caravanserai|hammam|"
    r"cave|gorge|cliff|rock formation|volcano|crater|mountain|spring|geyser|viaduct|dam\b|windmill|mill\b", re.I)
NOT_SIGHT = re.compile(
    r"human\b|person|school|college|university|kindergarten|station|stop\b|airport|airfield|port of entry|"
    r"hospital|clinic|hotel|hostel|company|business|enterprise|organi[sz]ation|club|team|league|stadium|arena|"
    r"sports venue|event|festival|competition|tournament|season|election|battle|war\b|conflict|protest|"
    r"government|ministry|embassy|consulate|office|headquarters|bank|cinema|shopping|mall|supermarket|"
    r"restaurant|caf[eé]\b|bar\b|pub\b|nightclub|residential|apartment|housing|street|road|avenue|boulevard|"
    r"highway|motorway|expressway|lane\b|alley|metro|subway|railway|tramway|line\b|bus\b|ward\b|"
    r"administrative|municipality|commune|county|province|prefecture|village|town\b|city\b|settlement|"
    r"census|postal|electoral|constituency|parish\b|diocese|archdiocese|dynasty|language|species|taxon|genus|"
    r"film|book|song|album|newspaper|magazine|periodical|television|radio|ship|vessel|car\b|locomotive|"
    r"research institute|institute|laboratory|academy|faculty|prison|police|military base|barracks|"
    r"power station|power plant|factory|plant\b|warehouse|industrial|mine\b|quarry|well\b|weather station|"
    r"ordinary|demolished|destroyed|former|defunct|closed|proposed|planned|under construction|"
    r"country|state\b|republic|empire|kingdom|polity|caliphate|khanate|sultanate|principality|era\b|period\b|"
    r"district of|urban district|borough|neighbo|quarter of|region|territory|capital|oblast|raion|"
    r"(?<!historic )district\b|operation|offensive|conference|siege|treaty|massacre|uprising|incident|disaster|"
    r"attack|bombing|expedition|campaign|convention|congress|exhibition cent|concert venue|music venue|"
    r"cricket ground|sports ground|multi-purpose|performing arts venue", re.I)
KIND_OF = (("park", re.compile(r"park\b|zoo|botanical", re.I)), ("garden", re.compile(r"garden", re.I)),
           ("viewpoint", re.compile(r"viewpoint|lookout|observation|hill\b|mountain|cliff", re.I)))


# classes that make many items famous only among their fans (every office tower of Dubai has 5 wikis)
WEAK = re.compile(r"skyscraper|high-rise|tower block|building|hall\b|residence|mansion|villa|manor|district|quarter|"
                  r"neighbourhood|hill\b|island|lake|canal|bridge|stairway|steps|spring|dam\b|mill\b|windmill|cemetery|"
                  r"market|fountain|statue|sculpture|memorial|tower", re.I)
STRONG = re.compile(r"church|cathedral|basilica|abbey|monastery|temple|shrine|pagoda|stupa|mosque|synagogue|museum|"
                    r"gallery|palace|castle|ch[aâ]teau|fortress|citadel|square|plaza|piazza|park\b|garden|monument|"
                    r"ruin|archaeological|amphitheat|theat(re|er)|opera|mausoleum|tomb|old town|historic|heritage|"
                    r"zoo|aquarium|botanical|gate|wat\b|lighthouse|viewpoint|lookout|beach", re.I)


def weak(types: list[str], tl: dict) -> bool:
    names = [tl.get(t, ["", "", ""])[0] for t in types]
    return not any(STRONG.search(n) for n in names if n) and any(WEAK.search(n) for n in names if n)


def classify(types: list[str], tl: dict) -> str | None:
    """'park', 'garden', 'viewpoint', 'historic' or None (not a sight), from the item's classes."""
    names = [tl.get(t, ["", "", ""])[0] for t in types]
    names = [n for n in names if n]
    if not names or any(NOT_SIGHT.search(n) for n in names) or not any(SIGHT.search(n) for n in names):
        return None
    for k, rx in KIND_OF:
        if any(rx.search(n) for n in names):
            return k
    return "historic"


def city(ccs: list[str]) -> None:
    """The city walks of the drawn cities and towns of these countries (all when none)."""
    import city_walks as cw
    import goal_walks as gw
    bs = json.loads((CACHE / "near-bases.json").read_text(encoding="utf-8"))
    have = json.loads((CACHE / "near-sights.json").read_text(encoding="utf-8"))
    done = set(have["done"])
    items = have["items"]
    tl = labels({t for r in items.values() for t in r["types"]})
    kinds = {q: classify(r["types"], tl) for q, r in items.items()}
    lab = labels([q for q, k in kinds.items() if k])
    pool_all = []
    for q, r in items.items():
        en, desc, mul = lab.get(q, ["", "", ""])
        name = en or mul
        if not kinds[q] or not name or cw.NOT_THERE.search(desc) or cw.NOT_A_SIGHT.search(name + " " + desc):
            continue
        if re.search(r"\b(street|road|avenue|boulevard)\b", name + " " + desc, re.I) and r["n"] < 8:
            continue
        if any(re.search(r"skyscraper|high-rise|tower block|office building", tl.get(t, [""])[0]) for t in r["types"]) and r["n"] < 40:
            continue  # Dubai's office towers: only the Burj Khalifa and its peers
        if weak(r["types"], tl) and r["n"] < 15 or re.search(r"\b(hotel|office|residential|tower \d|towers?)\b", desc, re.I) and r["n"] < 15:
            continue  # an office tower, a hall, a villa: a sight only when famous
        pool_all.append({**r, "name": name, "label": name[:90], "kind": kinds[q]})
    pool_all.sort(key=lambda s: -s["n"])  # one name, one stop (the Upper and the Lower Belvedere)
    seen: dict[str, list] = {}
    uniq = []
    for s in pool_all:
        k = s["label"].lower()
        if any(bt.km((s["lat"], s["lon"]), q) < 1.5 for q in seen.get(k, [])):
            continue
        seen.setdefault(k, []).append((s["lat"], s["lon"]))
        uniq.append(s)
    pool_all = uniq
    print(f"{len(pool_all)} sights of {len(items)} items", flush=True)
    grid: dict[tuple[int, int], list] = {}
    for s in pool_all:
        grid.setdefault((int(s["lat"] * 5), int(s["lon"] * 5)), []).append(s)
    want = {c.upper() for c in ccs}
    by_cc: dict[str, list] = {}
    for b in bs:
        if b["id"] in done and (not want or b["cc"] in want):
            by_cc.setdefault(b["cc"], []).append(b)
    for cc, cbs in sorted(by_cc.items()):
        used: set = set()
        jobs = []
        for b in cbs:
            a, c = int(b["lat"] * 5), int(b["lon"] * 5)
            span = int(b["radius"] / 20) + 1
            pool = [s for i in range(-span, span + 1) for j in range(-span, span + 1) for s in grid.get((a + i, c + j), ())]
            jobs += [(b, w) for w in cw.chains(b, pool, used)]
        print(f"{cc}: {len(cbs)} bases, {len(jobs)} walks to route", flush=True)
        if not jobs:
            continue
        gw._prefetch_climate([(w[0]["lat"], w[0]["lon"]) for _, w in jobs])
        out, k = [], Counter()
        for b, w in jobs:
            k[b["name"]] += 1
            r = cw.build_city(cc, b, w, k[b["name"]])
            if r:
                r[0]["sources"] = (["https://www.openstreetmap.org/"]
                                   + [f"https://www.wikidata.org/wiki/{s['wiki']}" for s in w])[:8]
                out.append(r)
        gw._write(cc, f"{cc.lower()}-city", out,
                  "City walks through famous sights (generated by tools/trails/near_walks.py from Wikidata, CC0, "
                  "routed by the FOSSGIS OSRM foot router on OpenStreetMap, ODbL, and the Copernicus DEM; never edit by hand).")

OSRM = "https://routing.openstreetmap.de"
_osrm_last = [0.0]


def osrm(path: str) -> dict:
    """The FOSSGIS OSRM servers (OpenStreetMap, ODbL), gently: one request at a time, 0.4 s apart."""
    time.sleep(max(0.0, _osrm_last[0] + 0.4 - time.time()))
    _osrm_last[0] = time.time()
    return bt.get(OSRM + path)


def _goals() -> list[tuple[float, float]]:
    """Where the app's walks already arrive: every trek and walk of tiers A and B and of the world."""
    from app import trails
    from app.trails import world
    out = [(p.lat, p.lon) for t in trails.trails() for p in t.points if p.role == "goal"]
    return out + [(r[2], r[3]) for r in world.dots()]


def sight_places(ccs: set[str]) -> list[dict]:
    """The drawn sights a short walk can reach: a landmark or nature place drawn as one spot (radius
    up to 8 km), not in a town (the city walks pass those)."""
    from app import art, globe
    towns = [p for p in globe.by_id().values() if p["kind"] in ("city", "town")]
    out = []
    for p in globe.by_id().values():
        lm = art.by_id().get(p.get("art") or "")
        if not lm or p["kind"] not in ("landmark", "nature") or lm.radius_km > 8 or (ccs and p["country"] not in ccs):
            continue
        if p["kind"] == "nature" and not POINTY.search(p["name"] + " " + lm.label):
            continue
        if any(t["country"] == p["country"] and abs(t["lat"] - lm.lat) < .05
                                           and bt.km((t["lat"], t["lon"]), (lm.lat, lm.lon)) <= 2.5 for t in towns):
            continue
        if any(q["scene"] == lm.id for q in out):
            continue
        out.append({"id": p["id"], "name": p["name"], "cc": p["country"], "kind": p["kind"], "scene": lm.id,
                    "lat": lm.lat, "lon": lm.lon})
    return out


def _base(lat: float, lon: float, cc: str, towns: list) -> tuple[str, float, float] | None:
    """The town to sleep in: the app's nearest city or town within 40 km, else GeoNames' biggest
    place within 30 km: (name, lat, lon)."""
    from app import globe
    app = [(bt.km((lat, lon), (p["lat"], p["lon"])), p["name"], p["lat"], p["lon"]) for p in globe.by_id().values()
           if p["country"] == cc and p["kind"] in ("city", "town") and abs(p["lat"] - lat) < .5]
    app = [x for x in app if x[0] <= 40]
    if app:
        return min(app)[1:]
    gn = [(t[4], t[0], t[1], t[2]) for t in towns if t[3] == cc and abs(t[1] - lat) < .3
          and bt.km((lat, lon), (t[1], t[2])) <= 30]
    if gn:
        return max(gn)[1:]
    far = [(bt.km((lat, lon), (t[1], t[2])), t[0], t[1], t[2]) for t in towns if t[3] == cc and abs(t[1] - lat) < 1]
    far = [x for x in far if x[0] <= 80]
    return min(far)[1:] if far else None


# a drawn nature place that is one spot you walk to (not a fjord, a bay, a lake, a valley or a park)
POINTY = re.compile(r"fall|foss|cascad|cascata|chute|salto|waterfall|viewpoint|lookout|mirador|belvedere|"
                    r"overlook|outlook|point\b|cave|grotto|grotta|cueva|arch\b|bridge|rock\b|pillar|stack|"
                    r"gorge|canyon|spring|geyser|hver|crater|cliff|beach|playa|praia|plage|blue eye|pool|"
                    r"tree|sinkhole|cenote|hole|dune|glacier|icefall|pass\b|summit|top\b", re.I)


SIGHT_DROPS: Counter = Counter()


def _car_off(lat: float, lon: float) -> float:
    c = osrm(f"/routed-car/nearest/v1/driving/{lon:.5f},{lat:.5f}?number=1")
    return c["waypoints"][0]["distance"] if c.get("code") == "Ok" else 1e9


def sight_walk(p: dict, towns: list) -> tuple[dict, dict] | None:
    """The walk a visitor does: the foot route from the town to the sight, cut where a car can no
    longer follow it (the trailhead), there and back, when that takes 8 to 50 minutes each way
    (0.5 to 3.5 km)."""
    la, lo = p["lat"], p["lon"]
    f = osrm(f"/routed-foot/nearest/v1/foot/{lo:.5f},{la:.5f}?number=1")
    if f.get("code") != "Ok" or f["waypoints"][0]["distance"] > 250:
        SIGHT_DROPS["no path near the sight"] += 1
        return None
    flo, fla = f["waypoints"][0]["location"]
    if _car_off(fla, flo) <= 30:
        SIGHT_DROPS["a car drives there"] += 1
        return None
    base = _base(fla, flo, p["cc"], towns)
    if not base:
        SIGHT_DROPS["no base"] += 1
        return None
    r = osrm(f"/routed-foot/route/v1/foot/{base[2]:.5f},{base[1]:.5f};{flo:.5f},{fla:.5f}?overview=full&geometries=geojson")
    if r.get("code") != "Ok":
        SIGHT_DROPS["no walk from the town"] += 1
        return None
    full = [(a, b) for b, a in r["routes"][0]["geometry"]["coordinates"]]
    back = [0.0]  # km from the sight, walking back towards the town
    for x, y in zip(full[::-1], full[::-1][1:]):
        back.append(back[-1] + bt.km(x, y))
    rev = full[::-1]

    def at(d: float) -> int:
        return next((i for i, v in enumerate(back) if v >= d), len(back) - 1)
    head = None
    last = 0.0
    for d in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
        if d > back[-1]:
            break
        if _car_off(*rev[at(d)]) <= 25:
            for e in [last + 0.1 * k for k in range(1, int((d - last) / 0.1) + 1)]:  # where exactly
                if e < d and _car_off(*rev[at(e)]) <= 25:
                    d = e
                    break
            head = at(d)
            break
        last = d
    if head is None:
        SIGHT_DROPS["too long" if back[-1] > 3.5 else "a car drives there"] += 1
        return None
    if back[head] < 0.5:
        SIGHT_DROPS["too short"] += 1
        return None
    line = rev[:head + 1][::-1]
    base = base[0]
    cc = p["cc"]
    slug = p["id"][len(cc) + 1:] if p["id"].lower().startswith(cc.lower() + "-") else p["id"]
    tid = f"{cc.lower()}-sight-{cw_slug(slug)}"
    pts = [{"id": "start", "name": "Road end", "lat": line[0][0], "lon": line[0][1], "role": "start"},
           {"id": "goal", "name": p["name"][:80], "lat": line[-1][0], "lon": line[-1][1], "role": "goal", "scene": p["scene"]}]
    t = {"id": tid, "name": f"Walk to {p['name']}"[:80], "country": cc, "base": base[:60], "region": "",
         "kind": "day", "days": 1, "shape": "out_and_back", "router": "osrm", "points": pts, "tier": "B"}
    real, real_ele = bt.from_osm, bt.elevations
    bt.from_osm = lambda rel: line
    bt.elevations = bt.tile_elevations
    t["osm"] = 1  # build() reads the line through from_osm
    try:
        g = bt.build(t)
    except Exception as e:
        SIGHT_DROPS["build failed"] += 1
        print(f"  {tid}: {type(e).__name__}: {e}")
        return None
    finally:
        bt.from_osm, bt.elevations = real, real_ele
        t.pop("osm")
    g["id"] = tid
    h = g["walk_hours"]
    up = round(g["gain_m"] / 2)
    if p["kind"] == "landmark" and up < 40 and g["one_way_km"] < 1.2:
        SIGHT_DROPS["a flat few steps to a monument"] += 1  # the Summer Palace from its car park is no walk
        return None
    t.update({
        "difficulty": ot._difficulty(1, h, g["gain_m"], g["max_m"]),
        "months": [],  # below, once the climate of all the country's walks is fetched
        "hours": [max(0.5, round(h * 0.85 * 2) / 2), max(0.5, round(h * 1.15 * 2) / 2)],
        "why": (f"A short walk to {p['name']}: {g['one_way_km']:.1f} km each way"
                + (f", +{up:,} m" if up >= 30 else ", nearly flat")
                + f", from where the road ends, near {base}.")[:300],
        "sources": ["https://www.openstreetmap.org/", "https://routing.openstreetmap.de/"],
    })
    sc = ot.scores(t["name"], g, 1, h, True, False)
    if p["kind"] == "landmark":
        sc.update({"culture": max(sc["culture"], 4), "history": max(sc["history"], 4),
                   "nature": min(sc["nature"], 3)})
    t["scores"] = sc
    return t, g


def cw_slug(s: str) -> str:
    import city_walks as cw
    return cw._slug(s, 40) or "sight"


def sights_walks(ccs: list[str]) -> None:
    """tail/<cc>-sights.json: a short walk to each drawn sight that needs one."""
    import goal_walks as gw
    want = {c.upper() for c in ccs}
    places = sight_places(want)
    goals = _goals()
    grid: dict[tuple[int, int], list] = {}
    for a, b in goals:
        grid.setdefault((int(a * 20), int(b * 20)), []).append((a, b))
    towns = geonames()
    by_cc: dict[str, list] = {}
    for p in places:
        k = (int(p["lat"] * 20), int(p["lon"] * 20))
        near = [g for i in (-1, 0, 1) for j in (-1, 0, 1) for g in grid.get((k[0] + i, k[1] + j), ())]
        if any(bt.km(g, (p["lat"], p["lon"])) <= 0.5 for g in near):
            SIGHT_DROPS["a walk already goes there"] += 1
            continue
        by_cc.setdefault(p["cc"], []).append(p)
    print(f"{len(places)} drawn sights, {sum(map(len, by_cc.values()))} to try; {dict(SIGHT_DROPS)}", flush=True)
    for cc, ps in sorted(by_cc.items()):
        out = []
        for p in ps:
            r = ot._safe(sight_walk, p, towns)
            if r:
                out.append(r)
        if out:
            gw._prefetch_climate([(t["points"][0]["lat"], t["points"][0]["lon"]) for t, _ in out])
            for t, g in out:
                t["months"] = ot._months(t["points"][0]["lat"], t["points"][0]["lon"], g["max_m"], cc, g["min_m"])
            gw._write(cc, f"{cc.lower()}-sights", out,
                      "Short walks from the nearest road to a drawn sight (generated by tools/trails/near_walks.py, "
                      "routed by the FOSSGIS OSRM foot router on OpenStreetMap, ODbL, and the Copernicus DEM; never edit by hand).")
        print(f"{cc}: {len(out)}/{len(ps)} sight walks; so far {dict(SIGHT_DROPS)}", flush=True)


NOT_ON_FOOT = {"us-city-new-york-city-1": "Liberty Island to Ellis Island is a ferry, not mapped as one"}


def tidy() -> None:
    """After `city`: drop the walks the foot router sends over a ferry (Venice, Stockholm, Suomenlinna)
    and the ones a later rule rules out (a stop that is an event or a venue), without routing again."""
    from app import trails  # noqa: F401  (the path)
    have = json.loads((CACHE / "near-sights.json").read_text(encoding="utf-8"))["items"]
    tl = labels([])
    lab = json.loads((CACHE / "near-labels.json").read_text(encoding="utf-8"))
    bad_names = {lab[q][0] for q, r in have.items() if q in lab and lab[q][0] and classify(r["types"], tl) is None}
    out = ot.ROOT / "backend/app/trails/tail"
    n = k = 0
    for f in sorted(out.glob("*-city.json")):
        if f.name[:2].upper() in DONE:
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        keep = []
        for t in doc["trails"]:
            k += 1
            g = doc["geo"][t["id"]]
            if any(bt.km((p["lat"], p["lon"]), (q["lat"], q["lon"])) > 0.8 for p, q in zip(t["points"], g["points"])):
                doc["geo"].pop(t["id"])
                n += 1
                continue  # a sight the router could not reach (the test's rule)
            c = ";".join(f"{p['lon']:.5f},{p['lat']:.5f}" for p in t["points"])
            r = osrm(f"/routed-foot/route/v1/foot/{c}?overview=false&steps=true")
            ferry = r.get("code") == "Ok" and any(st["mode"] != "walking" for leg in r["routes"][0]["legs"] for st in leg["steps"])
            if ferry or t["id"] in NOT_ON_FOOT or any(p["name"] in bad_names for p in t["points"]):
                doc["geo"].pop(t["id"], None)
                n += 1
                continue
            keep.append(t)
        doc["trails"] = keep
        if keep:
            f.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        else:
            f.unlink()
    print(f"tidy: {n} of {k} city walks dropped")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "bases":
        bases()
    elif cmd == "sights":
        fetch_sights()
    elif cmd == "city":
        city(sys.argv[2:])
    elif cmd == "tidy":
        tidy()
    elif cmd == "sightwalks":
        sights_walks(sys.argv[2:])
