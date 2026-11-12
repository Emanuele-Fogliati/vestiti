"""Rebuild backend/app/travel/airports.json from OurAirports (public domain).

    python tools/travel/build_airports.py            # downloads airports.csv
    python tools/travel/build_airports.py file.csv   # or uses a copy you already have

Keeps airports with scheduled service and an IATA code. Size: L large, M medium, S small.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OUT = Path(__file__).resolve().parents[2] / "backend" / "app" / "travel" / "airports.json"
SIZE = {"large_airport": "L", "medium_airport": "M", "small_airport": "S"}


def main() -> None:
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(URL, timeout=60) as r:
            text = r.read().decode("utf-8")
    rows = []
    for a in csv.DictReader(io.StringIO(text)):
        iata = (a.get("iata_code") or "").strip().upper()
        if len(iata) != 3 or not iata.isalpha() or a.get("scheduled_service") != "yes" or a["type"] not in SIZE:
            continue
        rows.append([iata, a["name"].strip(), (a.get("municipality") or "").strip(), a["iso_country"],
                     round(float(a["latitude_deg"]), 4), round(float(a["longitude_deg"]), 4), SIZE[a["type"]]])
    # one row per code: the biggest airport wins
    best: dict[str, list] = {}
    for r in rows:
        if r[0] not in best or "LMS".index(r[6]) < "LMS".index(best[r[0]][6]):
            best[r[0]] = r
    doc = {
        "_doc": ("Airports with scheduled flights and an IATA code, from OurAirports (public domain, "
                 f"https://ourairports.com/data/), downloaded {date.today().isoformat()}. Fields: iata, name, "
                 "city, country, lat, lon, size (L large, M medium, S small). Rebuild with "
                 "tools/travel/build_airports.py."),
        "fields": ["iata", "name", "city", "country", "lat", "lon", "size"],
        "airports": list(best.values()),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(best)} airports -> {OUT}")


if __name__ == "__main__":
    main()
