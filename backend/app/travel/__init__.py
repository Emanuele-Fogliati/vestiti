"""Getting from one stop to the next (Manu, 2026-11-12).

No airline gives a small app its seats: Aerolíneas Argentinas has no public API, the free
Amadeus API closed in 2026, and selling tickets (Duffel) would make the app a travel agency.
So for every leg the board gives:
- a guess of how you get there (same area, by road, by road or flight, flight) and how long;
- for flights, the nearest airports and links with the route and date already filled in:
  Google Flights, Skyscanner, the domestic airlines of the country, and Aviasales with the
  partner marker when TRAVELPAYOUTS_MARKER is set (a commission on bookings);
- prices seen recently for that route and those days, only with a Travelpayouts token
  (TRAVELPAYOUTS_TOKEN). They are cached prices, not live seats: the page says so.
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
HERE = Path(__file__).resolve().parent


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, a)))


@lru_cache
def airports() -> list[dict]:
    doc = json.loads((HERE / "airports.json").read_text(encoding="utf-8"))
    return [dict(zip(doc["fields"], r)) for r in doc["airports"]]


@lru_cache
def by_code() -> dict[str, dict]:
    return {a["iata"]: a for a in airports()}


# a bigger airport a bit further away beats a tiny one next door (more flights, lower prices)
SIZE_KM = {"L": 0.0, "M": 40.0, "S": 120.0}
AIRPORT_MAX_KM = 300.0


def nearest_airport(lat: float, lon: float, country: str | None = None) -> dict | None:
    best, score = None, None
    for a in airports():
        d = km(lat, lon, a["lat"], a["lon"])
        if d > AIRPORT_MAX_KM:
            continue
        s = d + SIZE_KM.get(a["size"], 120.0) + (0 if not country or a["country"] == country else 150)
        if score is None or s < score:
            best, score = a, s
    return best


def search_airports(q: str, limit: int = 8) -> list[dict]:
    from app.guide import _norm
    q = (q or "").strip()
    if len(q) < 2:
        return []
    up = q.upper()
    n = _norm(q)
    hits = []
    for a in airports():
        if a["iata"] == up:
            hits.append((0, a))
        elif _norm(a["city"] or "").startswith(n):
            hits.append((1 + "LMS".index(a["size"]), a))
        elif n in _norm(a["name"]):
            hits.append((4 + "LMS".index(a["size"]), a))
    hits.sort(key=lambda x: x[0])
    return [a for _, a in hits[:limit]]


# The main airlines flying inside each country, for the leg's "airline sites" links. Only
# their home pages: deep links into airline booking forms break without notice.
DOMESTIC = {
    "AR": [("Aerolíneas Argentinas", "https://www.aerolineas.com.ar"), ("JetSMART", "https://jetsmart.com"),
           ("Flybondi", "https://flybondi.com")],
    "CL": [("LATAM", "https://www.latamairlines.com"), ("Sky Airline", "https://www.skyairline.com"),
           ("JetSMART", "https://jetsmart.com")],
    "PE": [("LATAM", "https://www.latamairlines.com"), ("Sky Airline", "https://www.skyairline.com"),
           ("JetSMART", "https://jetsmart.com")],
    "BR": [("LATAM", "https://www.latamairlines.com"), ("GOL", "https://www.voegol.com.br"),
           ("Azul", "https://www.voeazul.com.br")],
    "CO": [("Avianca", "https://www.avianca.com"), ("LATAM", "https://www.latamairlines.com")],
    "EC": [("LATAM", "https://www.latamairlines.com"), ("Avianca", "https://www.avianca.com")],
    "BO": [("BoA", "https://www.boa.bo")],
    "MX": [("Aeroméxico", "https://aeromexico.com"), ("Volaris", "https://www.volaris.com"),
           ("Viva Aerobus", "https://www.vivaaerobus.com")],
    "IT": [("ITA Airways", "https://www.ita-airways.com")],
    "ES": [("Iberia", "https://www.iberia.com"), ("Vueling", "https://www.vueling.com")],
    "IS": [("Icelandair", "https://www.icelandair.com")],
    "NO": [("SAS", "https://www.flysas.com"), ("Norwegian", "https://www.norwegian.com"),
           ("Widerøe", "https://www.wideroe.no")],
    "JP": [("JAL", "https://www.jal.co.jp"), ("ANA", "https://www.ana.co.jp")],
    "VN": [("Vietnam Airlines", "https://www.vietnamairlines.com"), ("VietJet", "https://www.vietjetair.com")],
    "TH": [("Thai Airways", "https://www.thaiairways.com"), ("AirAsia", "https://www.airasia.com")],
    "ID": [("Garuda Indonesia", "https://www.garuda-indonesia.com"), ("AirAsia", "https://www.airasia.com")],
    "IN": [("Air India", "https://www.airindia.com"), ("IndiGo", "https://www.goindigo.in")],
    "NP": [("Buddha Air", "https://www.buddhaair.com"), ("Yeti Airlines", "https://www.yetiairlines.com")],
    "NZ": [("Air New Zealand", "https://www.airnewzealand.com")],
    "AU": [("Qantas", "https://www.qantas.com"), ("Virgin Australia", "https://www.virginaustralia.com")],
}


def flight_links(origin: str, dest: str, day: date) -> list[dict]:
    """Search pages with the route and the date already filled in."""
    s = get_settings()
    q = f"Flights from {origin} to {dest} on {day.isoformat()} one way"
    links = [
        {"label": "Google Flights", "url": "https://www.google.com/travel/flights?q=" + quote(q)},
        {"label": "Skyscanner", "url": f"https://www.skyscanner.net/transport/flights/{origin.lower()}/"
                                      f"{dest.lower()}/{day.strftime('%y%m%d')}/"},
    ]
    if s.travelpayouts_marker:
        links.append({"label": "Aviasales", "url": f"https://www.aviasales.com/search/{origin}"
                      f"{day.strftime('%d%m')}{dest}1?marker={quote(s.travelpayouts_marker)}",
                      "partner": True})
    a, b = by_code().get(origin), by_code().get(dest)
    if a and b and a["country"] == b["country"]:
        links += [{"label": n, "url": u, "airline": True} for n, u in DOMESTIC.get(a["country"], [])]
    return links


# ---------------------------------------------------------------- legs
ROAD_KMH = 60.0  # buses in Patagonia and the Andes, stops and borders included
ROAD_FACTOR = 1.3  # roads are longer than the straight line


def guess(a: dict | None, b: dict | None) -> dict:
    """How you probably go from a to b ({lat, lon, country}), and how long it takes.
    None for a or b is home: a flight."""
    if a is None or b is None:
        return {"mode": "flight", "km": None, "hours": None}
    d = km(a["lat"], a["lon"], b["lat"], b["lon"])
    if d <= 15:
        return {"mode": "local", "km": round(d), "hours": None}
    road_h = d * ROAD_FACTOR / ROAD_KMH
    border = bool(a.get("country") and b.get("country") and a["country"] != b["country"])
    if d <= 450:
        return {"mode": "road", "km": round(d), "hours": round(road_h + (1 if border else 0), 1),
                "border": border}
    if d <= 800:
        return {"mode": "road_or_flight", "km": round(d), "hours": round(road_h + (1 if border else 0), 1),
                "border": border}
    return {"mode": "flight", "km": round(d), "hours": None, "border": border}


# ---------------------------------------------------------------- prices (Travelpayouts)
_PRICE_CACHE: dict[tuple, tuple[float, list]] = {}
_PRICE_TTL_S = 6 * 3600


def prices(origin: str, dest: str, day: date, client: httpx.Client | None = None) -> list[dict] | None:
    """Prices seen recently for this route around this day (±2 days), cheapest first.
    None when prices are off (no token) or the service did not answer."""
    s = get_settings()
    if not s.travelpayouts_token:
        return None
    key = (origin, dest, day.strftime("%Y-%m"))
    hit = _PRICE_CACHE.get(key)
    if hit and time.time() - hit[0] < _PRICE_TTL_S:
        rows = hit[1]
    else:
        own = client is None
        client = client or httpx.Client(timeout=s.travelpayouts_timeout_s)
        try:
            r = client.get("https://api.travelpayouts.com/aviasales/v3/prices_for_dates", params={
                "origin": origin, "destination": dest, "departure_at": day.strftime("%Y-%m"),
                "one_way": "true", "currency": "eur", "sorting": "price", "limit": 100,
                "token": s.travelpayouts_token})
            r.raise_for_status()
            rows = r.json().get("data") or []
        except Exception as e:  # noqa: BLE001 - prices are a bonus, links still work
            log.warning("travelpayouts prices failed: %s", e)
            return None
        finally:
            if own:
                client.close()
        _PRICE_CACHE[key] = (time.time(), rows)
    out = []
    for row in rows:
        try:
            d = date.fromisoformat(str(row["departure_at"])[:10])
        except (KeyError, ValueError):
            continue
        if abs((d - day).days) <= 2:
            link = row.get("link")
            url = None
            if link:
                url = "https://www.aviasales.com" + link
                if s.travelpayouts_marker:
                    url += ("&" if "?" in url else "?") + "marker=" + quote(s.travelpayouts_marker)
            out.append({"date": d.isoformat(), "price": row.get("price"), "currency": "EUR",
                        "airline": row.get("airline"), "transfers": row.get("transfers"), "url": url})
    best: dict[str, dict] = {}
    for p in out:  # the cheapest per day
        if p["date"] not in best or (p["price"] or 1e9) < (best[p["date"]]["price"] or 1e9):
            best[p["date"]] = p
    return sorted(best.values(), key=lambda p: p["date"])


