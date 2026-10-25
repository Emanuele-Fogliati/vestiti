"""Place search. Open-Meteo geocoding (GeoNames data, free), with a small offline
gazetteer so the app still works without network."""
from __future__ import annotations

import json
import logging
import math
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


# names GeoNames does not resolve to the place travellers mean
ALIASES = {"cuzco": "Cusco", "cuzco city": "Cusco", "cusco city": "Cusco"}
FEATURE_BONUS = {"PPLC": 1.0, "PPLA": 0.7, "PPLA2": 0.4, "PPLA3": 0.2, "PPL": 0.1}
_cache: dict[tuple, list[dict]] = {}


def search(q: str, limit: int = 8, client: httpx.Client | None = None,
           country: str | None = None) -> list[dict]:
    """Place search. country is an ISO-2 code that restricts the results to one country."""
    s = get_settings()
    if not q or len(q.strip()) < 2:
        return []
    q = ALIASES.get(_norm(q.strip()), q.strip())
    if s.weather_enabled:
        key = (_norm(q), limit, country)
        if client is None and key in _cache:
            return [dict(x) for x in _cache[key]]
        own = client is None
        client = client or httpx.Client(timeout=s.weather_timeout_s)
        try:
            params = {"name": q, "count": limit, "language": "en", "format": "json"}
            if country:
                params["countryCode"] = country
            r = client.get(s.openmeteo_geocoding_url, params=params)
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
                "population": x.get("population") or 0,
                "source": "open-meteo",
            } for x in results]
            if own and len(_cache) < 2000:
                _cache[key] = out
            if out or country:
                return out
        except Exception as e:
            log.warning("geocoding failed, using offline gazetteer: %s", e)
            if country:
                return []
        finally:
            if own:
                client.close()
    hits = offline_search(q, limit)
    return [h for h in hits if h.get("country_code") == country] if country else hits


def _km(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["latitude"], a["longitude"], b["latitude"], b["longitude"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(min(1.0, math.sqrt(h)))


def _score(c: dict, rank: int, countries: set[str], near: list[dict]) -> float:
    s = -0.5 * rank + 0.25 * math.log10((c.get("population") or 0) + 1)
    s += FEATURE_BONUS.get(c.get("feature") or "", 0.0)
    if countries and c.get("country_code") in countries:
        s += 2.0
    if near:
        # a stop is almost always within a day's travel of the stops around it
        s -= min(4.0, min(_km(c, n) for n in near) / 400)
    return s


def resolve_trip(names: list[str], limit: int = 5, client: httpx.Client | None = None) -> list[list[dict]]:
    """Geocode the stops of one trip together: a name is read in the trip's country and near
    the stops around it, so "Aguas Calientes" after Cusco is the Peruvian one, not Mexico's.
    Returns the candidates for each stop, best first."""
    cands = [search(n, limit=10, client=client) for n in names]
    votes: dict[str, float] = {}
    for cs in cands:
        seen = set()
        for rank, c in enumerate(cs):
            cc = c.get("country_code")
            if cc and cc not in seen:
                seen.add(cc)
                votes[cc] = votes.get(cc, 0) + (1.0 if rank == 0 else 0.5)
    countries: set[str] = set()
    if votes and len(names) > 1:
        top = max(votes.values())
        # a trip can cross borders (Patagonia): keep every country with real support
        countries = {cc for cc, v in votes.items() if v >= max(1.5, top / 2)}
    if countries:
        for i, (n, cs) in enumerate(zip(names, cands)):
            if not any(c.get("country_code") in countries for c in cs[:3]):
                for cc in sorted(countries, key=lambda k: -votes[k]):
                    extra = search(n, limit=10, client=client, country=cc)
                    known = {(c["latitude"], c["longitude"]) for c in cs}
                    cs.extend(c for c in extra if (c["latitude"], c["longitude"]) not in known)
                cands[i] = cs
    ranked = [list(enumerate(cs)) for cs in cands]
    chosen: list[dict | None] = [None] * len(names)
    for _ in range(2):  # pass 1 without neighbours known, pass 2 with them
        for i, rs in enumerate(ranked):
            if not rs:
                continue
            near = [chosen[j] for j in (i - 1, i + 1) if 0 <= j < len(names) and chosen[j]]
            best = max(rs, key=lambda rc: _score(rc[1], rc[0], countries, near))
            chosen[i] = best[1]
    out = []
    for i, cs in enumerate(cands):
        if not chosen[i]:
            out.append([])
            continue
        rest = [c for c in cs if c is not chosen[i]]
        out.append([chosen[i]] + rest[: limit - 1])
    return out
