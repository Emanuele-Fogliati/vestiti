"""Build backend/app/globe/coords.json: exact positions for the places inside cities.

The trip reading gives coordinates to two decimals (about 1 km), so in Florence the Uffizi,
Palazzo Vecchio, the Duomo and the Baptistery all sat on one dot. Zoomed on a city every sight
needs its own spot. This asks Wikidata (CC0) for items whose English label or alias is the
place's name (or one of its local names from the inventory) and keeps the one with coordinates
closest to ours, only when it is within 3 km of where we had it. Anything else keeps the old
position: never moved by guesswork.

    SSL_CERT_FILE=/root/.ccr/ca-bundle.crt python tools/globe/refine_coords.py [manifest.json]

Run from the repo root, with backend/ on the path (it reads the city links from app.globe).
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
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "backend" / "app" / "globe" / "coords.json"
SPARQL = "https://query.wikidata.org/sparql"
UA = "ThruwearBuild/0.1 (https://github.com/Emanuele-Fogliati/vestiti)"
MAX_KM = 3.0
BATCH = 150


def km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, h)))


def lit(s: str) -> str:
    return json.dumps(s, ensure_ascii=False) + "@en"


def query(names: list[str]) -> list[tuple[str, str, float, float]]:
    q = ("SELECT ?name ?item ?c WHERE { VALUES ?name { " + " ".join(lit(n) for n in names) + " } "
         "?item rdfs:label|skos:altLabel ?name . ?item wdt:P625 ?c . }")
    req = urllib.request.Request(SPARQL + "?" + urllib.parse.urlencode({"query": q}),
                                 headers={"Accept": "application/sparql-results+json", "User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                rows = json.load(r)["results"]["bindings"]
            break
        except Exception as e:  # noqa: BLE001
            print("  retry", attempt + 1, e, file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    else:
        return []
    out = []
    for b in rows:
        pt = b["c"]["value"]
        if not pt.startswith("Point("):
            continue
        lon, lat = map(float, pt[6:-1].split())
        out.append((b["name"]["value"], b["item"]["value"].rsplit("/", 1)[-1], lat, lon))
    return out


def main() -> int:
    from app import globe
    man = {}
    if len(sys.argv) > 1:
        man = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["places"]
    # positions as read (globe.by_id() already applies an older coords.json)
    raw = {r[0]: (r[4], r[5]) for r in json.loads((ROOT / "backend/app/globe/places.json").read_text("utf-8"))["places"]}
    kids = [p for p in globe.by_id().values() if p["parent"]]
    names: dict[str, list[str]] = {}
    for p in kids:
        ns = [p["name"], *(man.get(p["id"], {}).get("local") or [])]
        names[p["id"]] = list(dict.fromkeys(n for n in ns if n and len(n) < 120))
    all_names = sorted({n for ns in names.values() for n in ns})
    hits: dict[str, list[tuple[str, float, float]]] = {}
    for i in range(0, len(all_names), BATCH):
        for name, qid, lat, lon in query(all_names[i:i + BATCH]):
            hits.setdefault(name, []).append((qid, lat, lon))
        print(f"{min(i + BATCH, len(all_names))}/{len(all_names)} names", file=sys.stderr)
        time.sleep(1.5)
    out = {}
    for p in kids:
        lat0, lon0 = raw[p["id"]]
        cands = [(km(lat0, lon0, la, lo), q, la, lo) for n in names[p["id"]] for q, la, lo in hits.get(n, [])]
        cands = [c for c in cands if c[0] <= MAX_KM]
        if cands:
            _, q, la, lo = min(cands)
            out[p["id"]] = [round(la, 5), round(lo, 5), q]
    OUT.write_text(json.dumps({
        "_doc": "Exact positions of places inside cities, from Wikidata (CC0), within 3 km of the "
                "position read from the trips. Built by tools/globe/refine_coords.py.",
        "places": dict(sorted(out.items())),
    }, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"refined {len(out)} of {len(kids)} places inside cities", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
