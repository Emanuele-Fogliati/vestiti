"""City walks (Manu, 2026-11-14: "aggiungi anche quelli cittadini", so a traveller can plan the whole
trip in detail): walks on foot through the famous sights of each city and town of the trekking countries.

OpenStreetMap has very few waymarked city walks in these countries, so we make them from open data:
- sights: named OSM objects with a Wikidata id and a sight tag (tools/trails/pbf_sights.js on the
  country extract; for NZ, which has no extract, Wikidata items of sight classes), ranked by the
  number of Wikipedia languages of their Wikidata item;
- bases: the app's cities and towns, and GeoNames cities of 100,000+ people;
- a walk: from the most famous sight not yet walked, the next sight is the best of those within
  1.2 km (fame over distance), up to 7 stops and 6 km in a straight line; 3 stops or more, 1.5 km or
  more; up to 8 walks in a city of a million people, 4 over 300,000, 3 in other cities, 1 in a town (sights
  within 15 km and 10 walks for 5 million people, 10, 6, 4 or 2.5 km of the centre); routed on foot by the FOSSGIS OSRM foot router (OSM);
- numbers (km, climb, hours, months) as every tier-B walk; the six scores by rule (culture and
  history high, effort low); the pictures are the app's drawings of the sights it passes.

  node tools/trails/pbf_sights.js <cc>.osm.pbf <cc>.sights.json      # per country
  python3 tools/trails/city_walks.py <sights dir> <sitelinks.json> PE CL AR IS NZ JP VN NA
     -> backend/app/trails/tail/<cc>-city.json
"""
from __future__ import annotations

from collections import Counter
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

import build_trails as bt
import goal_walks as gw
import osm_tail as ot

HOP_KM, MAX_STRAIGHT_KM, MAX_STOPS = 1.2, 6.0, 7
DROPS: Counter = Counter()
# Wikidata descriptions that are not a sight you can walk to: a statue tagged with its person's item,
# a vehicle type, a firm, a place that has closed (Manu's walks must still be there)
NOT_THERE = re.compile(
    r"^(\S+\s){0,3}(politician|author|writer|poet|novelist|composer|painter|sculptor|general|military officer|soldier|"
    r"lawyer|journalist|singer|actor|actress|priest|folk saint|first lady|businessman|engineer|explorer|physician|"
    r"president|emperor|servant of)\b|^human settlement|^genus|aircraft|broadcaster|theatre company|park chain|"
    r"^(tramcar|bus|tram|trolleybus)|^(family|given) name|\b\d{4}\s*[–-]\s*\d{4}\)?$|"
    r"^former (\w+ )?(museum|theme park|amusement park|railway station|mine|seaplane base|office building|temple|"
    r"buddhist temple|fort|lighthouse)\b", re.I)
NOT_A_SIGHT = re.compile(r"\bINN\b|school|college|kindergarten|police|courthouse|council|university|hospital|station|airport|stadium|office|hotel|bank|"
                         r"学校|大学|病院|駅|空港|事務所|ホテル|銀行|colegio|escuela|hospital|estaci[oó]n", re.I)


def _slug(s: str, n: int = 30) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:n].strip("-")


def _label(s: dict, links: dict) -> str:
    """The English name when Wikidata has one, else the local name (with the English after it)."""
    en = (links.get(s["wiki"]) or [0, ""])[1] or s.get("en") or ""
    name = s["name"]
    if en and not gw._latin(name):
        return f"{en} ({name})"[:90] if len(en) + len(name) < 60 else en[:90]
    return (en or name)[:90]


def sights(cc: str, src: Path, links: dict) -> list[dict]:
    raw = json.loads((src / f"{cc.lower()}.sights.json").read_text(encoding="utf-8"))["sights"]
    best: dict[str, dict] = {}
    for s in raw:
        n = (links.get(s["wiki"]) or [s.get("n", 0)])[0]
        desc = (links.get(s["wiki"]) or ["", "", "", ""])[3] if len(links.get(s["wiki"]) or []) > 3 else ""
        if n < 3 or NOT_A_SIGHT.search(s["name"] + " " + desc) or NOT_THERE.search(desc):
            continue
        if re.search(r"\b(street|road|avenue|calle|avenida|jir[oó]n)\b|通り|通$", s["name"] + " " + ((links.get(s["wiki"]) or [0, ""])[1] or ""), re.I) and n < 8:
            continue  # a street is a sight only when famous (Takeshita-dori, Florida)
        if s["wiki"] not in best or s["osm"].startswith("w"):
            best[s["wiki"]] = {**s, "n": n, "label": _label(s, links)}
    return list(best.values())


def bases(cc: str) -> list[dict]:
    from app import globe
    towns = [t for t in ot._towns() if t[3] == cc]
    out = [{"name": p["name"], "lat": p["lat"], "lon": p["lon"], "city": p["kind"] == "city"}
           for p in globe.by_id().values() if p["country"] == cc and p["kind"] in ("city", "town")]
    for t in towns:
        if t[4] >= 100_000 and all(bt.km((t[1], t[2]), (b["lat"], b["lon"])) > 12 for b in out):
            out.append({"name": t[0], "lat": t[1], "lon": t[2], "city": True})
    for b in out:  # people: the biggest GeoNames place within 6 km (a city's wards are listed apart)
        b["pop"] = max([t[4] for t in towns if abs(t[1] - b["lat"]) < .06 and bt.km((t[1], t[2]), (b["lat"], b["lon"])) <= 6] or [0])
        b["radius"], b["walks"] = ((15, 10) if b["pop"] >= 5_000_000 else (10, 8) if b["pop"] >= 1_000_000 else (6, 4) if b["pop"] >= 300_000
                                   else (4, 3) if b["city"] else (2.5, 1))
    # a quarter of a bigger city (Shibuya in Tokyo, Recoleta in Buenos Aires) walks its own streets only;
    # bigger first, and an exact tie of people (both take Tokyo's) goes to the app's city over its town
    out.sort(key=lambda b: (-b["pop"], -b["city"]))
    for i, b in enumerate(out):
        if any(bt.km((a["lat"], a["lon"]), (b["lat"], b["lon"])) <= a["radius"] for a in out[:i] if not a.get("quarter")):
            b["quarter"] = True
            b["radius"], b["walks"] = 2.0, 2
    return out


def chains(base: dict, pool: list[dict], used: set) -> list[list[dict]]:
    r = base["radius"]
    near = [s for s in pool if s["wiki"] not in used and bt.km((base["lat"], base["lon"]), (s["lat"], s["lon"])) <= r]
    out, tried = [], set()
    for _ in range(4 * base["walks"] + 6):
        if len(out) >= base["walks"]:
            break
        left = sorted((s for s in near if s["wiki"] not in used), key=lambda s: -s["n"])
        seeds = [s for s in left if s["wiki"] not in tried]
        if len(left) < 3 or not seeds:
            break
        walk = [seeds[0]]
        tried.add(seeds[0]["wiki"])
        straight = 0.0
        while len(walk) < MAX_STOPS:
            here = (walk[-1]["lat"], walk[-1]["lon"])
            cand = [(bt.km(here, (s["lat"], s["lon"])), s) for s in left if s not in walk]
            cand = [(d, s) for d, s in cand if 0.08 < d <= HOP_KM and straight + d <= MAX_STRAIGHT_KM
                    and all(bt.km((w["lat"], w["lon"]), (s["lat"], s["lon"])) > 0.08 for w in walk)]
            if not cand:
                break
            d, s = max(cand, key=lambda x: math.log(1 + x[1]["n"]) / (0.3 + x[0]))
            walk.append(s)
            straight += d
        if len(walk) >= 3 and straight >= 1.2 and sum(s["n"] for s in walk) >= 4 * len(walk):
            out.append(walk)
            used.update(s["wiki"] for s in walk)
        else:
            DROPS["too few sights"] += 1
    return out


def build_city(cc: str, base: dict, walk: list[dict], k: int) -> tuple[dict, dict] | None:
    from app import art
    pts = []
    for i, s in enumerate(walk):
        pid = _slug(s["label"]) or f"stop-{i + 1}"
        if len(pid) < 1 or any(p["id"] == pid for p in pts):
            pid = f"stop-{i + 1}"
        pts.append({"id": pid, "name": s["label"] if len(s["label"]) >= 3 else f"{s['label']} (sight)",
                    "lat": s["lat"], "lon": s["lon"], "role": "point"})
    pts[0]["role"], pts[-1]["role"] = "start", "goal"
    first, last = walk[0]["label"].split(" (")[0], walk[-1]["label"].split(" (")[0]
    name = f"{base['name']}: {first} to {last}"
    if len(name) > 80:
        name = f"{base['name']} walk from {first}"[:80]
    tid = f"{cc.lower()}-city-{_slug(base['name'], 24)}-{k}"
    t = {"id": tid, "name": name, "country": cc, "base": base["name"][:60], "region": "", "kind": "day",
         "days": 1, "shape": "one_way", "router": "osrm", "points": pts, "tier": "B", "style": "city"}
    real = bt.elevations
    bt.elevations = bt.tile_elevations
    try:
        g = bt.build(t)
    except Exception as e:
        DROPS[f"route failed"] += 1
        print(f"  {tid}: {type(e).__name__}: {e}")
        return None
    finally:
        bt.elevations = real
    straight = sum(bt.km((a["lat"], a["lon"]), (b["lat"], b["lon"])) for a, b in zip(walk, walk[1:]))
    if g["km"] > max(2.2 * straight, straight + 3) or g["km"] > 12:
        DROPS["detour"] += 1
        return None
    g["id"] = tid
    h = g["walk_hours"]
    t.update({
        "difficulty": "easy" if g["gain_m"] < 250 else "moderate",
        "months": ot._months(walk[0]["lat"], walk[0]["lon"], g["max_m"], cc, g["min_m"]),
        "hours": [max(0.5, round(h * 2) / 2), max(1.0, round((h + 0.4 * len(walk)) * 2) / 2)],
        "why": (f"A city walk of {g['km']:.1f} km on foot past {len(walk)} of {base['name']}'s best-known sights: "
                + ", ".join(s["label"].split(" (")[0] for s in walk))[:300],
        "sources": (["https://www.openstreetmap.org/"]
                    + [f"https://www.wikidata.org/wiki/{s['wiki']}" for s in walk])[:8],
    })
    seen = set()
    for p in pts:
        lm = art._nearest(p["lat"], p["lon"], cc)
        if lm and lm.id not in seen and bt.km((p["lat"], p["lon"]), (lm.lat, lm.lon)) <= 0.4:
            p["scene"] = lm.id
            seen.add(lm.id)
    e = 0 if h < 1.5 else 1 if h < 3 else 2
    fame = sum(s["n"] for s in walk)
    green = any(s["kind"] in ("park", "garden", "viewpoint") or re.search(r"park|garden|domain|parque|jard[ií]n|公園|庭園", s["label"], re.I)
                for s in walk)
    t["scores"] = {"effort": e, "nature": 1 if green else 0,
                   "culture": 5 if fame >= 150 else 4, "relax": 3 if e < 2 else 2,
                   "history": 5 if sum(1 for s in walk if s["kind"] not in ("park", "garden", "viewpoint", "attraction")) >= 4
                   else 4 if fame >= 60 else 3,
                   "landscape": 3 if green or g["max_m"] - g["min_m"] > 80 else 2}
    return t, g


def main(src: str, links_f: str, ccs: list[str]) -> None:
    links = json.loads(Path(links_f).read_text(encoding="utf-8"))
    for cc in ccs:
        pool = sights(cc, Path(src), links)
        bs = bases(cc)
        used: set = set()
        jobs = [(b, w) for b in bs for w in chains(b, pool, used)]
        print(f"{cc}: {len(pool)} sights, {len(bs)} bases, {len(jobs)} walks to route", flush=True)
        gw._prefetch_climate([(w[0]["lat"], w[0]["lon"]) for _, w in jobs])
        out, k = [], Counter()
        for n, (b, w) in enumerate(jobs):
            k[b["name"]] += 1
            r = build_city(cc, b, w, k[b["name"]])
            if r:
                out.append(r)
            if n % 50 == 49:
                print(f"  {n + 1}/{len(jobs)}", flush=True)
        gw._write(cc, f"{cc.lower()}-city", out,
                  "City walks through famous sights (generated by tools/trails/city_walks.py from OpenStreetMap, "
                  "ODbL, Wikidata, CC0, routed by the FOSSGIS OSRM foot router, and the Copernicus DEM; never edit by hand).")
        print(f"{cc}: {len(out)} city walks; dropped {dict(DROPS)}", flush=True)
        DROPS.clear()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
    main(sys.argv[1], sys.argv[2], [c.upper() for c in sys.argv[3:]])
