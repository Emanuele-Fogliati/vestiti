"""Build the recommended trips (Manu, 2026-11-16: "per ogni posto un viaggio raccomandato da 1, 2,
3, 4 settimane, per ogni mese"; then "viaggi che possono andare su più nazioni") from the
ready-made routes of app/guide/trips.json that belong to a journey: a travel region as tour
operators cut it (Patagonia on both sides of the border, Atacama with Uyuni, Peru with Bolivia).

Each route (zones to sleep in, nights, in order, one per season band) becomes an itinerary of
app.inspire: the days filled from the hand-written guide of each zone (app.guide.todo: the things
in the order not to miss, several a day when their hours fit, a spare day for the weather where
the zone keeps one), only the things in season in that band; the activities of each stop come
from the things planned there, so the clothes (app.inspire.wear) follow what you actually do.
Nothing is copied from the operators' trips: their merged patterns only say what to see on the
way. Deterministic: same data in, same file out.

    cd backend && PYTHONPATH=. python ../tools/guide/build_recommended.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.guide import ready  # noqa: E402
from app.inspire.build import build  # noqa: E402

OUT = ROOT / "backend" / "app" / "inspire" / "recommended.json"


def main() -> None:
    its = [build(t) for t in ready.trips() if t.journey]
    its.sort(key=lambda x: (x["destination"], x["weeks"], -len(x["best_months"]), x["slug"]))
    doc = {"_doc": ("Recommended trips built by tools/guide/build_recommended.py from app/guide/trips.json and the "
                    "hand-written zone guides. Do not edit by hand: change the routes or the guides and run the tool."),
           "itineraries": its}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(its)} recommended trips -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
