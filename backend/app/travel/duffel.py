"""Flights from Duffel (duffel.com): every flight of a day for one leg, and booking.

Manu, 2026-11-12: multi-city trips, and for each leg every flight of the day ("one hour
earlier, one hour later"), not the few a search site decides to show. And booking inside the app.

- Search: one request per leg (a one-way "offer request"), so each leg shows every flight of
  its day, in time order, and the traveller picks per leg. A second request with all legs
  together prices them as one ticket, to compare.
- Booking: only with a TEST token (duffel_test_...): Duffel takes the money from the account
  balance, so a live booking would spend real money with nobody paying it back. Going live
  needs Manu's Duffel account, a way to take the traveller's payment (Duffel Payments) and the
  terms of a ticket seller: see docs/FLIGHTS.md.

DUFFEL_ACCESS_TOKEN empty = no search, no booking: the board falls back to links.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
API = "https://api.duffel.com"
MAX_OFFERS = 120
_CACHE: dict[tuple, tuple[float, list]] = {}
_TTL_S = 10 * 60  # offers expire after ~20-30 minutes


class DuffelError(RuntimeError):
    pass


def enabled() -> bool:
    return bool(get_settings().duffel_access_token)


def test_mode() -> bool:
    return get_settings().duffel_access_token.startswith("duffel_test_")


def _client(client: httpx.Client | None) -> tuple[httpx.Client, bool]:
    if client is not None:
        return client, False
    s = get_settings()
    return httpx.Client(base_url=API, timeout=s.duffel_timeout_s, headers={
        "Authorization": f"Bearer {s.duffel_access_token}", "Duffel-Version": "v2",
        "Accept": "application/json", "Content-Type": "application/json"}), True


def _post(path: str, body: dict, client: httpx.Client | None = None, params: dict | None = None) -> dict:
    c, own = _client(client)
    try:
        r = c.post(path, json={"data": body}, params=params)
        if r.status_code >= 400:
            try:
                errs = r.json().get("errors") or []
                msg = "; ".join(e.get("message", "") for e in errs) or r.text[:200]
            except ValueError:
                msg = r.text[:200]
            raise DuffelError(msg)
        return r.json()["data"]
    except httpx.HTTPError as e:
        raise DuffelError(f"The flight service did not answer: {e}") from e
    finally:
        if own:
            c.close()


def _get(path: str, client: httpx.Client | None = None) -> dict:
    c, own = _client(client)
    try:
        r = c.get(path)
        if r.status_code >= 400:
            raise DuffelError(r.text[:200])
        return r.json()["data"]
    except httpx.HTTPError as e:
        raise DuffelError(f"The flight service did not answer: {e}") from e
    finally:
        if own:
            c.close()


def _minutes(iso: str | None) -> int | None:
    """'PT3H15M' -> 195."""
    if not iso:
        return None
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", iso)
    if not m:
        return None
    d, h, mi = (int(x or 0) for x in m.groups())
    return d * 1440 + h * 60 + mi


def _slice(sl: dict) -> dict:
    segs = sl.get("segments") or []
    return {
        "origin": (sl.get("origin") or {}).get("iata_code"),
        "destination": (sl.get("destination") or {}).get("iata_code"),
        "departs": segs[0]["departing_at"] if segs else None,
        "arrives": segs[-1]["arriving_at"] if segs else None,
        "minutes": _minutes(sl.get("duration")),
        "stops": max(0, len(segs) - 1),
        "segments": [{
            "from": (g.get("origin") or {}).get("iata_code"), "to": (g.get("destination") or {}).get("iata_code"),
            "departs": g.get("departing_at"), "arrives": g.get("arriving_at"),
            "airline": (g.get("marketing_carrier") or {}).get("name"),
            "flight": f"{(g.get('marketing_carrier') or {}).get('iata_code', '')} "
                      f"{g.get('marketing_carrier_flight_number', '')}".strip(),
        } for g in segs],
    }


def _offer(o: dict) -> dict:
    cond = o.get("conditions") or {}
    change = cond.get("change_before_departure") or {}
    refund = cond.get("refund_before_departure") or {}
    return {
        "id": o["id"], "price": float(o["total_amount"]), "currency": o["total_currency"],
        "airline": (o.get("owner") or {}).get("name"),
        "expires_at": o.get("expires_at"),
        "slices": [_slice(s) for s in o.get("slices") or []],
        "passenger_ids": [p["id"] for p in o.get("passengers") or []],
        "changeable": change.get("allowed"), "refundable": refund.get("allowed"),
        "bags": _bags(o),
    }


def _bags(o: dict) -> int | None:
    """Checked bags included for the first passenger on the first segment, if Duffel says."""
    try:
        seg = o["slices"][0]["segments"][0]
        for b in seg["passengers"][0].get("baggages") or []:
            if b.get("type") == "checked":
                return int(b.get("quantity") or 0)
        return 0
    except (KeyError, IndexError, TypeError):
        return None


def _dedupe(offers: list[dict]) -> list[dict]:
    """The same flights sold at several fares: keep the cheapest of each."""
    best: dict[str, dict] = {}
    for o in offers:
        key = "|".join(f"{g['flight']}@{g['departs']}" for s in o["slices"] for g in s["segments"])
        if key not in best or o["price"] < best[key]["price"]:
            best[key] = o
    return list(best.values())


def search(slices: list[dict], adults: int = 1, cabin: str = "economy",
           client: httpx.Client | None = None) -> list[dict]:
    """Offers for these slices ([{origin, destination, date}]), one per set of flights, in
    departure order of the first slice."""
    if not enabled() and client is None:
        raise DuffelError("Flight search is not set up (no Duffel token).")
    key = (tuple((s["origin"], s["destination"], str(s["date"])) for s in slices), adults, cabin)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL_S and client is None:
        return hit[1]
    data = _post("/air/offer_requests", {
        "slices": [{"origin": s["origin"], "destination": s["destination"],
                    "departure_date": str(s["date"])} for s in slices],
        "passengers": [{"type": "adult"} for _ in range(max(1, adults))],
        "cabin_class": cabin, "max_connections": 1,
    }, client=client, params={"return_offers": "true", "supplier_timeout": "20000"})
    offers = _dedupe([_offer(o) for o in (data.get("offers") or [])])
    offers.sort(key=lambda o: (o["slices"][0]["departs"] or "", o["price"]))
    offers = offers[:MAX_OFFERS]
    if client is None:
        _CACHE[key] = (time.time(), offers)
    return offers


def book(offer_id: str, passengers: list[dict], client: httpx.Client | None = None) -> dict:
    """Book one offer for these passengers. TEST tokens only (see the module doc)."""
    if client is None and not test_mode():
        raise DuffelError("Booking is in test mode only: a live Duffel account and payments are not set up yet.")
    offer = _get(f"/air/offers/{offer_id}", client=client)  # the latest price
    ids = [p["id"] for p in offer.get("passengers") or []]
    if len(ids) != len(passengers):
        raise DuffelError(f"This offer is for {len(ids)} traveller(s): give {len(ids)} name(s).")
    order = _post("/air/orders", {
        "type": "instant", "selected_offers": [offer_id],
        "passengers": [{**p, "id": pid} for p, pid in zip(passengers, ids)],
        "payments": [{"type": "balance", "currency": offer["total_currency"], "amount": offer["total_amount"]}],
    }, client=client)
    return {"order_id": order["id"], "booking_reference": order.get("booking_reference"),
            "price": float(order.get("total_amount") or offer["total_amount"]),
            "currency": order.get("total_currency") or offer["total_currency"],
            "slices": [_slice(s) for s in order.get("slices") or offer.get("slices") or []],
            "test": test_mode() or client is not None}


def day_ok(d: date) -> bool:
    return d >= date.today()
