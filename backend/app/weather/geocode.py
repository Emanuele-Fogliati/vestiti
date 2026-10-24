"""Place search. Open-Meteo geocoding (GeoNames data, free), with a small offline
gazetteer so the app still works without network."""
from __future__ import annotations

import json
import logging
import unicodedata
from functools import lru_cache
from pathlib import Path

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
GAZETTEER = Path(__file__).resolve().parents[2] / "seed" / "gazetteer.json"


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


@lru_cache
def _gazetteer() -> list[dict]:
    try:
        return json.loads(GAZETTEER.read_text(encoding="utf-8"))["places"]
    except FileNotFoundError:
        return []


def offline_search(q: str, limit: int = 8) -> list[dict]:
    nq = _norm(q.strip())
    if not nq:
        return []
    hits = [p for p in _gazetteer() if _norm(p["name"]).startswith(nq)]
    hits += [p for p in _gazetteer() if nq in _norm(p["name"]) and p not in hits]
    return [{**p, "source": "offline"} for p in hits[:limit]]


def search(q: str, limit: int = 8, client: httpx.Client | None = None) -> list[dict]:
    s = get_settings()
    if not q or len(q.strip()) < 2:
        return []
    if s.weather_enabled:
        own = client is None
        client = client or httpx.Client(timeout=s.weather_timeout_s)
        try:
            r = client.get(s.openmeteo_geocoding_url,
                           params={"name": q.strip(), "count": limit, "language": "en",
                                   "format": "json"})
            r.raise_for_status()
            results = r.json().get("results") or []
            out = [{
                "name": x["name"],
                "admin": x.get("admin1"),
                "country": x.get("country"),
                "country_code": x.get("country_code"),
                "latitude": x["latitude"],
                "longitude": x["longitude"],
                "elevation_m": x.get("elevation") or 0.0,
                "feature": x.get("feature_code"),
                "source": "open-meteo",
            } for x in results]
            if out:
                return out
        except Exception as e:
            log.warning("geocoding failed, using offline gazetteer: %s", e)
        finally:
            if own:
                client.close()
    return offline_search(q, limit)
