"""Add the stops that have no normal yet to backend/app/globe/climate.json, reading only those
points of TerraClimate over OPeNDAP (no 2 GB download). Same data, same rules as
build_climate.py: TerraClimate 1991-2020 monthly normals at 1/24 degree, public domain (CC0;
Abatzoglou et al. 2018), the nearest land cell for a stop on the coast, temperatures moved from
the cell's height to the stop's height (6.5 °C per km). Never WorldClim.

The stops: the recommended trips (backend/app/inspire/recommended.json) whose places are more
than NORMALS_KM from any normal, so the trip clothes come from the real climate and not from the
rough latitude guess (Opus check, 2026-11-16: Bariloche, Huaraz, Easter Island had none).

    python tools/globe/add_climate_points.py
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
LAPSE = 6.5 / 1000  # °C per metre, as build_climate.py
CELLS_PER_DEG = 24  # 1/24 degree


def key(lat: float, lon: float) -> str:
    return f"{lat:.3f},{lon:.3f}"

OUT = ROOT / "backend/app/globe/climate.json"
BASE = "https://thredds.northwestknowledge.net/thredds/dodsC/TERRACLIMATE_ALL"
VARS = ("tmin", "tmax", "ppt", "vap")
WIN = 6  # cells each side: about 25 km, for a stop whose own cell is sea
NORMALS_KM = 100.0


def get(url: str) -> str:
    for k in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return r.read().decode()
        except Exception:  # noqa: BLE001 - a busy server: wait and retry
            if k == 3:
                raise
            time.sleep(3 * (k + 1))
    return ""


def scale(path: str, var: str) -> tuple[float, float, float]:
    das = get(f"{BASE}/{path}.das")
    block = das[das.index(f"    {var} {{"):]
    block = block[:block.index("    }")]
    sf = float(re.search(r"scale_factor ([-\d.eE]+)", block).group(1))
    off = float(re.search(r"add_offset ([-\d.eE]+)", block).group(1))
    fill = float(re.search(r"_FillValue ([-\d.eE]+)", block).group(1))
    return sf, off, fill


def window(path: str, var: str, r0: int, c0: int, months: bool) -> list:
    t = "[0:1:11]" if months else ""
    q = f"{var}{t}[{r0 - WIN}:1:{r0 + WIN}][{c0 - WIN}:1:{c0 + WIN}]"
    txt = get(f"{BASE}/{path}.ascii?{q}")
    body = txt.split("---------------------------------------------")[-1]
    rows = []
    for line in body.splitlines():
        m = re.match(r"^\[(\d+)\](?:\[(\d+)\])?, (.*)$", line.strip())
        if m and line.strip().startswith(f"{var}.") is False:
            rows.append((int(m.group(1)), int(m.group(2)) if m.group(2) else None, [float(x) for x in m.group(3).split(",")]))
    return rows


def nearest(grid: list[list[float]], fill: float) -> tuple[int, int] | None:
    best = None
    n = len(grid)
    for r in range(n):
        for c in range(len(grid[r])):
            if grid[r][c] != fill and not math.isnan(grid[r][c]):
                d = (r - WIN) ** 2 + (c - WIN) ** 2
                if best is None or d < best[0]:
                    best = (d, r, c)
    return (best[1], best[2]) if best else None


def point(lat: float, lon: float, height: float) -> list[list[float]] | None:
    r0 = int((90 - lat) * CELLS_PER_DEG)
    c0 = int((lon + 180) * CELLS_PER_DEG)
    sf, off, fill = scale("layers/terraclim_dem.nc", "elevation")
    dem_rows = window("layers/terraclim_dem.nc", "elevation", r0, c0, months=False)
    dem = [vals for _, _, vals in dem_rows]
    vals = {}
    rc = None
    for v in VARS:
        path = f"climatology/TerraClimate_19912020_{v}.nc"
        vsf, voff, vfill = scale(path, v)
        rows = window(path, v, r0, c0, months=True)
        by_m: dict[int, list[list[float]]] = {}
        for m, r, xs in rows:
            by_m.setdefault(m, []).append(xs)
        if rc is None:
            rc = nearest(by_m[0], vfill)
            if rc is None:
                return None
        vals[v] = [by_m[m][rc[0]][rc[1]] * vsf + voff for m in range(12)]
    cell_h = dem[rc[0]][rc[1]] * sf + off if dem and dem[rc[0]][rc[1]] != fill else None
    shift = (cell_h - height) * LAPSE if cell_h is not None and not math.isnan(cell_h) else 0.0
    return [[round(vals["tmin"][m] + shift, 1), round(vals["tmax"][m] + shift, 1), round(vals["ppt"][m]),
             round(vals["vap"][m], 2)] for m in range(12)]


def km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, x)))


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()
    doc = json.loads(OUT.read_text(encoding="utf-8"))
    have = {k: tuple(map(float, k.split(","))) for k in doc["stops"]}
    rec = json.loads((ROOT / "backend/app/inspire/recommended.json").read_text(encoding="utf-8"))
    todo = {}
    for it in rec["itineraries"]:
        for s in it["stops"]:
            if any(abs(la - s["lat"]) <= 1.5 and km(s["lat"], s["lon"], la, lo) <= NORMALS_KM for la, lo in have.values()):
                continue
            todo[key(s["lat"], s["lon"])] = (s["name"], s["lat"], s["lon"], s["elevation_m"])
    for k, (name, lat, lon, h) in sorted(todo.items()):
        months = point(lat, lon, h)
        if months is None:
            print(f"  {name}: no land cell nearby")
            continue
        doc["stops"][k] = months
        have[k] = (lat, lon)
        print(f"  {name} ({h} m): Jan {months[0][:3]}  Jul {months[6][:3]}")
    OUT.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"{len(todo)} stops added -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
