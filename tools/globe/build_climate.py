"""Build backend/app/globe/climate.json: the normal weather of every stop of the globe routes,
month by month, so the globe can show which routes have good weather in the month you pick.

Source: TerraClimate monthly normals 1991-2020 at 1/24 degree (about 4 km), public domain
(CC0; Abatzoglou et al. 2018, Scientific Data 5:170191, https://www.climatologylab.org/terraclimate.html).
Not WorldClim: its terms forbid commercial use and redistribution without permission.
Temperatures are moved from the grid cell's height to the stop's own height (6.5 °C per km),
so Cusco at 3,400 m is not read as the warmer valley around it.

Usage (download from https://thredds.northwestknowledge.net/thredds/catalog/TERRACLIMATE_ALL/:
climatology/TerraClimate_19912020_{tmax,tmin,ppt,vap}.nc and layers/terraclim_dem.nc, in one folder):
    python tools/globe/build_climate.py /path/to/terraclimate [--out backend/app/globe/climate.json]
Needs: numpy, netCDF4.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
LAPSE = 6.5 / 1000  # °C per metre
CELLS_PER_DEG = 24  # 1/24 degree


def stops() -> dict[str, float]:
    """Every stop of the routes and of the ready-made itineraries: "lat,lon" -> elevation."""
    out: dict[str, float] = {}
    for r in json.loads((ROOT / "backend/app/globe/routes.json").read_text(encoding="utf-8"))["routes"]:
        for s in r["stops"]:
            out[key(s["lat"], s["lon"])] = s["elevation_m"]
    for f in sorted((ROOT / "backend/app/inspire/itineraries").glob("*.json")):
        for s in json.loads(f.read_text(encoding="utf-8"))["stops"]:
            out[key(s["lat"], s["lon"])] = s["elevation_m"]
    return out


def key(lat: float, lon: float) -> str:
    return f"{lat:.3f},{lon:.3f}"


class Grid:
    def __init__(self, a: np.ma.MaskedArray):
        self.a = np.ma.filled(a.astype("float32"), np.nan)

    def at(self, lat: float, lon: float) -> float | None:
        """The cell value; a stop on the coast whose cell is sea takes the nearest land cell
        (up to about 50 km away)."""
        r0 = int((90 - lat) * CELLS_PER_DEG)
        c0 = int((lon + 180) * CELLS_PER_DEG)
        for rad in range(0, 13):
            best = None
            for dr in range(-rad, rad + 1):
                for dc in range(-rad, rad + 1):
                    r, c = r0 + dr, (c0 + dc) % self.a.shape[1]
                    if 0 <= r < self.a.shape[0] and not np.isnan(self.a[r, c]):
                        d = dr * dr + dc * dc
                        if best is None or d < best[0]:
                            best = (d, self.a[r, c])
            if best:
                return float(best[1])
        return None


def read(path: Path, var: str, month: int | None = None) -> Grid:
    with netCDF4.Dataset(path) as d:
        v = d[var]
        return Grid(v[month] if month is not None else v[:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("terraclimate")
    ap.add_argument("--out", default=str(ROOT / "backend/app/globe/climate.json"))
    a = ap.parse_args()
    tc = Path(a.terraclimate)
    heights = stops()
    where = {k: tuple(map(float, k.split(","))) for k in heights}
    elev = read(tc / "terraclim_dem.nc", "elevation")
    shift = {}
    for k, (lat, lon) in where.items():
        cell_h = elev.at(lat, lon)
        shift[k] = (cell_h - heights[k]) * LAPSE if cell_h is not None else 0.0
    del elev
    vals: dict[str, list[list[float | None]]] = {k: [[None] * 4 for _ in range(12)] for k in where}
    for i, v in enumerate(("tmin", "tmax", "ppt", "vap")):
        for m in range(12):  # a month at a time: a whole variable does not fit in memory
            g = read(tc / f"TerraClimate_19912020_{v}.nc", v, m)
            for k, (lat, lon) in where.items():
                vals[k][m][i] = g.at(lat, lon)
    out, missing = {}, []
    for k, months in sorted(vals.items()):
        if any(x is None for row in months for x in row):
            missing.append(k)
            continue
        out[k] = [[round(lo + shift[k], 1), round(hi + shift[k], 1), round(pr), round(vp, 2)] for lo, hi, pr, vp in months]
    doc = {"_doc": "Normal weather per stop and month: [min °C, max °C, rain mm, vapour pressure kPa]. TerraClimate "
                   "1991-2020 normals, 1/24 degree, public domain (CC0; Abatzoglou et al. 2018), "
                   "moved to the stop's height. Built by tools/globe/build_climate.py; do not edit by hand.",
           "stops": out}
    Path(a.out).write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} stops, {len(missing)} without data: {missing[:10]}")


if __name__ == "__main__":
    main()
