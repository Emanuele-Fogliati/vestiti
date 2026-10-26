"""Build backend/app/globe/places.json: the places the globe shows, with coordinates checked.

Input: the place inventory (manifest.json from the tour-operator reading: every place with its
country, kind, coordinates and how many organised trips visit it) and Natural Earth 1:10m
country borders. A place is kept only when its coordinates fall inside its own country (or
within 30 km of its coast or border, for islands, beaches and border towns). Places that land
in another country or in the open sea are dropped and listed, never moved by guesswork.

    pip install shapely pyshp
    python tools/globe/build_places.py manifest.json ne_10m_admin_0_countries.shp \
        [--registry backend/seed/places.json] [--min-trips 3]

The verified place registry (when present) wins over the inventory for coordinates.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import shapefile  # pyshp
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

OUT = Path(__file__).resolve().parents[2] / "backend" / "app" / "globe" / "places.json"
TOLERANCE_DEG = 0.27  # ~30 km
# Territories Natural Earth draws inside their sovereign country's polygon.
PART_OF = {"SJ": "NO", "RE": "FR", "GP": "FR", "MQ": "FR", "GF": "FR", "YT": "FR", "BQ": "NL"}


def _key(name: str) -> str:
    """Sacsayhuamán and Sacsayhuaman are the same place."""
    s = "".join(c for c in unicodedata.normalize("NFKD", name.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def countries(shp: str):
    r = shapefile.Reader(shp)
    names = [f[0] for f in r.fields[1:]]
    geoms, codes = [], []
    for sr in r.iterShapeRecords():
        rec = dict(zip(names, sr.record))
        cc = rec.get("ISO_A2_EH") or rec.get("ISO_A2")
        if not cc or cc == "-99":
            continue
        geoms.append(shape(sr.shape.__geo_interface__).buffer(0))
        codes.append(cc.upper())
    return geoms, codes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("borders")
    ap.add_argument("--registry", help="verified place registry (backend/seed/places.json)")
    ap.add_argument("--min-trips", type=int, default=3)
    a = ap.parse_args()

    man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    places, n_trips = man["places"], len(man["trips"])
    reg = {}
    if a.registry and Path(a.registry).is_file():
        for p in json.loads(Path(a.registry).read_text(encoding="utf-8"))["places"]:
            if (p.get("verified") or {}).get("ok"):
                reg[p["id"]] = (p["latitude"], p["longitude"])

    geoms, codes = countries(a.borders)
    by_cc: dict[str, list] = {}
    for g, c in zip(geoms, codes):
        by_cc.setdefault(c, []).append(g)
    tree = STRtree(geoms)

    kept, dropped, fixed = [], [], 0
    for pid, p in places.items():
        if p.get("trips", 0) < a.min_trips or p.get("lat") is None:
            continue
        cc = p["country"].upper()
        lat, lon = p["lat"], p["lon"]
        if pid in reg:
            lat, lon = reg[pid]
            fixed += 1
        pt = Point(lon, lat)
        own = by_cc.get(cc, []) + by_cc.get(PART_OF.get(cc, ""), []) or None
        if own is None:  # a country Natural Earth has no polygon for (tiny states): keep only if not inside another
            inside = [codes[i] for i in tree.query(pt, predicate="within")]
            if inside:
                dropped.append((pid, p["name"], cc, f"inside {inside[0]}"))
                continue
        elif not any(g.distance(pt) <= TOLERANCE_DEG for g in own):
            inside = [codes[i] for i in tree.query(pt, predicate="within")]
            dropped.append((pid, p["name"], cc, f"inside {inside[0]}" if inside else "in the sea"))
            continue
        kept.append([pid, p["name"], cc, p["kind"], round(lat, 3), round(lon, 3), p["trips"]])

    kept.sort(key=lambda r: -r[6])
    # the same place read twice under two ids (drake-passage, drake-passage-2): keep the most visited
    seen: dict[tuple[str, str], list] = {}
    unique = []
    for r in kept:
        twin = next((o for o in seen.get((_key(r[1]), r[2]), []) if abs(o[4] - r[4]) + abs(o[5] - r[5]) < 0.5), None)
        if twin is None:
            seen.setdefault((_key(r[1]), r[2]), []).append(r)
            unique.append(r)
    kept = unique
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "_doc": "Places for the globe and the trip maps, from the reading of organised trips. "
                "Built by tools/globe/build_places.py; coordinates checked against the country's borders.",
        "inventory_trips": n_trips,
        "fields": ["id", "name", "country", "kind", "lat", "lon", "trips"],
        "places": kept,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"kept {len(kept)} places ({fixed} with registry coordinates), dropped {len(dropped)}", file=sys.stderr)
    for d in dropped:
        print("  dropped", *d, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
