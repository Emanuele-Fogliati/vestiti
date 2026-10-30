"""Which places sit inside a city: Florence's sights belong to Florence.

From far away the globe shows the places a traveller names when they say where they go
(Florence, Cusco, Machu Picchu). The sights inside a city (the Uffizi, Ponte Vecchio,
Qorikancha) show only once you zoom on that city, and when you plan a trip you can add the
whole city or single sights in it (Manu, 2026-10-26).

A place is inside a city or town when:
  - it is close to the centre (12 km for a city, 5 km for a town: Tambomachay is part of a
    Cusco city tour, Teotihuacan is a day out from Mexico City),
  - it is in the same country (a city state counts as part of the city around it: the Vatican
    is in Rome),
  - fewer organised trips go there than to the city, so a place that is a destination of its
    own stays one: Machu Picchu is not "in" Aguas Calientes, Petra is not "in" Wadi Musa.
A town can be inside a city (a suburb), a city only when it is a city state (Vatican City).
There is one level only: a sight in the Vatican belongs to Rome.
"""
from __future__ import annotations

import math

RADIUS_KM = {"city": 12.0, "town": 5.0}
TOWN_IN_CITY_KM = 6.0  # a town this close to a bigger city is a part of it
# a city state's places belong to the city around it
CITY_STATES = {"VA": "IT", "SM": "IT", "MC": "FR"}
# a place this much more visited than the city it stands in is a destination of its own:
# (place trips) > SELF_STANDING * (city trips) keeps it on the world view
SELF_STANDING = 1.0


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, a)))


def _can_hold(city: dict, p: dict) -> bool:
    if city is p or city["kind"] not in RADIUS_KM:
        return False
    if city["country"] != p["country"] and CITY_STATES.get(p["country"]) != city["country"]:
        return False
    if p["kind"] == "city" and not (p["country"] in CITY_STATES and city["kind"] == "city"):
        return False
    if p["kind"] == "town" and city["kind"] != "city":
        return False
    if p["trips"] > SELF_STANDING * city["trips"]:
        return False
    limit = TOWN_IN_CITY_KM if p["kind"] == "town" else RADIUS_KM[city["kind"]]
    return km(p["lat"], p["lon"], city["lat"], city["lon"]) <= limit


def parents(places: list[dict]) -> dict[str, str]:
    """{place id: id of the city or town it is inside}. places: dicts with id, kind, country,
    lat, lon, trips. Top-level places are left out."""
    # a grid of ~0.25 degrees keeps this fast on thousands of places
    cell = lambda lat, lon: (int(math.floor(lat * 4)), int(math.floor(lon * 4)))  # noqa: E731
    grid: dict[tuple[int, int], list[dict]] = {}
    for c in places:
        if c["kind"] in RADIUS_KM:
            grid.setdefault(cell(c["lat"], c["lon"]), []).append(c)
    direct: dict[str, dict] = {}
    for p in places:
        y, x = cell(p["lat"], p["lon"])
        near = [c for dy in (-1, 0, 1) for dx in (-1, 0, 1) for c in grid.get((y + dy, x + dx), [])]
        best = min((c for c in near if _can_hold(c, p)),
                   key=lambda c: km(p["lat"], p["lon"], c["lat"], c["lon"]), default=None)
        if best is not None:
            direct[p["id"]] = best
    out: dict[str, str] = {}
    for pid, c in direct.items():
        seen = {pid}
        while c["id"] in direct and c["id"] not in seen:  # one level: the Vatican's sights go to Rome
            seen.add(c["id"])
            c = direct[c["id"]]
        if c["id"] != pid:
            out[pid] = c["id"]
    return out
