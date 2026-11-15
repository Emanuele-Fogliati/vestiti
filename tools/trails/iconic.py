"""The treks known the world over (Manu, 2026-11-14): seen from space on the globe (rank 6), and
the list of the ones worth a drawing later. Hand-picked in iconic.tsv (global fame, not local),
matched here to the app's treks by name near the place:

  python tools/trails/iconic.py     # -> backend/app/trails/world/_iconic.json

A name matches when one of its `match` words is in the trek's name and the trek ends within 300 km
of the listed point; the nearest of the best-known wins. No match: listed with id null (the trek is
not in OpenStreetMap as a route, or its continent is not built yet).
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def km(a, b) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, h)))


def candidates() -> list[tuple[str, str, float, float, int, bool]]:
    """[id, name, lat, lon, rank, has drawing]: the app's treks (A, B) and the world's."""
    from app import trails
    from app.trails import world
    out = []
    for t in trails.trails():
        g = next((p for p in reversed(t.points) if p.role == "goal"), t.points[-1])
        out.append((t.id, t.name, g.lat, g.lon, 5 if t.tier == "A" else 3, any(p.scene for p in t.points)))
    out += [(r[0], r[1], r[2], r[3], r[6], False) for r in world.dots()]
    return out


def main() -> None:
    rows = list(csv.DictReader((HERE / "iconic.tsv").open(encoding="utf-8"), delimiter="\t"))
    cands = candidates()
    res = []
    for r in rows:
        pat = re.compile("|".join(re.escape(w) for w in r["match"].split("|")), re.I)
        at = (float(r["lat"]), float(r["lon"]))
        hits = [(c, km(at, (c[2], c[3]))) for c in cands if pat.search(c[1])]
        hits = [h for h in hits if h[1] <= 300]
        best = min(hits, key=lambda h: (-h[0][4], h[1]))[0] if hits else None
        res.append({"region": r["region"], "country": r["country"], "name": r["name"],
                    "id": best[0] if best else None, "trek": best[1] if best else None,
                    "drawn": bool(best and best[5])})
    out = ROOT / "backend/app/trails/world/_iconic.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"_doc": "The world's iconic treks (tools/trails/iconic.tsv, matched by iconic.py): "
                                       "rank 6 on the globe; the ones to draw later.", "treks": res},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sum(1 for x in res if x['id'])}/{len(res)} matched")


if __name__ == "__main__":
    main()
