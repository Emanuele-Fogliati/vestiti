"""Places for the home globe and the trip maps.

places.json comes from the reading of organised trips (tools/globe/build_places.py): every place
with its country, kind, coordinates (checked against the country's borders) and how many of the
trips we read visit it. The more trips visit a place, the further out on the globe it shows.

Each place gets its landmark scene only when the library has one named after it (Cusco gets the
cathedral; a village near Cusco gets none), and the ready-made itineraries that stop there.
"""
from __future__ import annotations

import gzip
import json
from functools import lru_cache
from pathlib import Path

from app import art, inspire

HERE = Path(__file__).resolve().parent


def _norm(s: str) -> str:
    return art._norm(s)


@lru_cache
def payload() -> dict:
    doc = json.loads((HERE / "places.json").read_text(encoding="utf-8"))
    its = list(inspire.itineraries())
    # place names each itinerary passes through (stops and the places visited from them)
    in_it: list[set[str]] = [
        {_norm(n) for s in it.stops for n in [s.name, *(v.name for v in s.visits)]} for it in its]
    places = []
    for pid, name, cc, kind, lat, lon, trips in doc["places"]:
        lm = next((m for m in art._named(name) if m.country == cc), None)
        hits = [i for i, names in enumerate(in_it) if cc in its[i].countries and _norm(name) in names]
        places.append([pid, name, cc, kind, lat, lon, trips, lm.id if lm else None,
                       lm.label if lm else None, hits])
    return {
        "inventory_trips": doc["inventory_trips"],
        "fields": ["id", "name", "country", "kind", "lat", "lon", "trips", "art", "art_label", "itineraries"],
        "itineraries": [{"slug": it.slug, "title": it.title} for it in its],
        "places": places,
    }


@lru_cache
def payload_bytes() -> tuple[bytes, bytes]:
    raw = json.dumps(payload(), ensure_ascii=False, separators=(",", ":")).encode()
    return raw, gzip.compress(raw, 9)
