"""Check the key points of the trails against OpenStreetMap names (Nominatim, 1 request a second).
Prints, for each point, the nearest OSM feature with a matching name within ~20 km and how far it is
from the coordinates written in the data. With --fix, writes the OSM coordinates when they are within
`--max` km. Run from the repo root: python tools/trails/geocode.py [--fix] [trail id ...]"""
from __future__ import annotations
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from build_trails import DATA, UA, km  # noqa: E402

def search(q, lat, lon, span=0.2):
    vb = f"{lon-span},{lat+span},{lon+span},{lat-span}"
    u = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "jsonv2", "limit": 5, "viewbox": vb, "bounded": 1})
    time.sleep(1.1)
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60) as r:
        return json.load(r)

def main(args):
    fix = "--fix" in args
    only = [a for a in args if not a.startswith("--")]
    for f in sorted(DATA.glob("*/*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for t in [d]:
            if only and t["id"] not in only:
                continue
            print(t["id"])
            for p in t["points"]:
                qs = [p.get("q") or p["name"].split(",")[0].split(" on ")[0].split(" above ")[0]]
                res = []
                for q in qs:
                    try:
                        res = search(q, p["lat"], p["lon"])
                    except Exception as e:
                        print("   ERR", e)
                    if res:
                        break
                if not res:
                    print(f"   {p['id']:12} {qs[0]!r}: no OSM match")
                    continue
                best = min(res, key=lambda r: km((p["lat"], p["lon"]), (float(r["lat"]), float(r["lon"]))))
                dk = km((p["lat"], p["lon"]), (float(best["lat"]), float(best["lon"])))
                print(f"   {p['id']:12} {qs[0]!r} -> {best['name']} [{best['category']}/{best['type']}] "
                      f"{float(best['lat']):.4f},{float(best['lon']):.4f} ({dk:.2f} km)")
                if fix and dk <= float(p.get("max_fix", 6)):
                    p["lat"], p["lon"] = round(float(best["lat"]), 5), round(float(best["lon"]), 5)
        if fix:
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main(sys.argv[1:])
