"""Hiking and foot route relations of an OpenStreetMap extract (ODbL), read locally, in the same
row format as the Waymarked Trails census of osm_tail.py (so its filters and build reuse them).

Overpass and the Waymarked API cannot list a whole continent (Manu 2026-11-14: every trek in the
world), so each country extract is cut first with osmium-tool and read here:

  osmium tags-filter country.osm.pbf r/route=hiking,foot -o routes.pbf
  python tools/trails/pbf_routes.py routes.pbf census.json

Row: {id, name, group, tags, length (m), sub, bbox [lon0, lat0, lon1, lat1], sac, line [[lat, lon]]}.
`group` is the network letter Waymarked uses: I(nternational), N(ational), R(egional), L(ocal).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import osmium

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_trails as bt  # noqa: E402

SAC = {"hiking": 1, "mountain_hiking": 2, "demanding_mountain_hiking": 3, "alpine_hiking": 4,
       "demanding_alpine_hiking": 5, "difficult_alpine_hiking": 6}
GROUP = {"iwn": "I", "nwn": "N", "rwn": "R", "lwn": "L"}


def _km(a, b) -> float:
    la = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(la))


def assemble(ways: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    """The member ways into one walkable line. OSM members are often out of order (Waymarked
    sorts them; a plain chain in member order jumps about), so: start at a dead end, follow the
    ways that touch the line's end (the earlier member first), and when none does, jump to the
    nearest unused way within 15 km (a gap in the mapping or the start of a variant)."""
    if not ways:
        return []
    from collections import defaultdict

    def key(p):
        return (round(p[0], 6), round(p[1], 6))
    ends = defaultdict(list)
    for i, w in enumerate(ways):
        ends[key(w[0])].append(i)
        ends[key(w[-1])].append(i)
    used = [False] * len(ways)
    first, flip = 0, False
    for i, w in enumerate(ways):
        if len(ends[key(w[0])]) == 1:
            first, flip = i, False
            break
        if len(ends[key(w[-1])]) == 1:
            first, flip = i, True
            break
    line = list(ways[first][::-1] if flip else ways[first])
    used[first] = True
    left = len(ways) - 1
    while left:
        k = key(line[-1])
        cand = [i for i in ends[k] if not used[i]]
        if cand:
            i = min(cand)
            w = ways[i] if key(ways[i][0]) == k else ways[i][::-1]
            line += w[1:]
        else:
            end = line[-1]
            best, bi, rev = 15.0, None, False
            for i, w in enumerate(ways):
                if used[i]:
                    continue
                for r, p in ((False, w[0]), (True, w[-1])):
                    d = _km(end, p)
                    if d < best:
                        best, bi, rev = d, i, r
            if bi is None:
                break
            i = bi
            line += ways[i][::-1] if rev else ways[i]
        used[i] = True
        left -= 1
    return line


def read(pbf: str):
    rels: dict[int, dict] = {}
    need: set[int] = set()
    for o in osmium.FileProcessor(pbf, osmium.osm.RELATION):
        t = {k: v for k, v in o.tags}
        if t.get("route") not in ("hiking", "foot"):
            continue
        ways = [m.ref for m in o.members if m.type == "w"]
        subs = [m.ref for m in o.members if m.type == "r"]
        rels[o.id] = {"tags": t, "ways": ways, "sub": bool(subs)}
        need.update(ways)
    from array import array
    geo: dict[int, tuple] = {}  # way -> (flat float32 lat, lon, ..., sac): a continent fits in memory
    for o in osmium.FileProcessor(pbf, osmium.osm.NODE | osmium.osm.WAY).with_locations("flex_mem"):
        if not o.is_way() or o.id not in need:
            continue
        a = array("f")
        for n in o.nodes:
            loc = n.location
            if loc.valid():
                a.append(loc.lat)
                a.append(loc.lon)
        if len(a) >= 4:
            geo[o.id] = (a, SAC.get(o.tags.get("sac_scale", ""), 0))
    for rid, r in rels.items():
        ws = [([(a[i], a[i + 1]) for i in range(0, len(a), 2)], s) for a, s in (geo[w] for w in r["ways"] if w in geo)]
        seen, length, sac = set(), 0.0, 0
        for w, (pts, s) in zip([w for w in r["ways"] if w in geo], ws):
            if w in seen:
                continue
            seen.add(w)
            length += sum(_km(a, b) for a, b in zip(pts, pts[1:]))
            sac = max(sac, s)
        # only a possible trek keeps its line (a continent's containers and walks under 4 km would
        # not fit in memory): 4-250 km, named, not a container of other routes
        maybe = 4000 <= length * 1000 <= 250000 and not r["sub"] and (r["tags"].get("name") or r["tags"].get("name:en"))
        line = assemble([p for p, _ in ws]) if ws and maybe else []
        allp = [p for pts, _ in ws for p in pts]
        box = ([min(p[1] for p in allp), min(p[0] for p in allp), max(p[1] for p in allp), max(p[0] for p in allp)]
               if allp else None)
        t = r["tags"]
        yield ({"id": rid, "name": t.get("name") or t.get("name:en") or "", "group": GROUP.get(t.get("network", "")),
                    "tags": t, "length": round(length * 1000), "sub": r["sub"], "bbox": box, "sac": sac,
                    "line": [(round(a, 5), round(b, 5)) for a, b in line]})


if __name__ == "__main__":
    n = 0
    with open(sys.argv[2], "w", encoding="utf-8") as f:  # a JSON list, written row by row
        f.write("[")
        for row in read(sys.argv[1]):
            f.write(("," if n else "") + json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
        f.write("]")
    print(f"{sys.argv[1]}: {n} relations")
