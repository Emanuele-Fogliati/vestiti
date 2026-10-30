"""Place search. The verified place registry first (app.places.registry: country, coordinates
and elevation checked against public sources), then Open-Meteo geocoding (GeoNames data, free).
Offline, the registry alone answers."""
from __future__ import annotations

import logging
import math
import unicodedata

import httpx

from app.config import get_settings
from app.places import registry
from app.places.verify import Check, check_stops, expected_countries

log = logging.getLogger(__name__)


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def offline_search(q: str, limit: int = 8) -> list[dict]:
    return [registry.as_result(p) for p in registry.prefix(q, limit)]


FEATURE_BONUS = {"REG": 1.5, "PPLC": 1.0, "PPLA": 0.7, "PPLA2": 0.4, "PPLA3": 0.2, "PPL": 0.1}
_cache: dict[tuple, list[dict]] = {}


def _known(q: str, country: str | None) -> list[dict]:
    """Registry places with exactly this name: 'Machu Picchu' is the Peruvian one, placed at
    Aguas Calientes where you sleep, whatever GeoNames lists first."""
    hits = [p for p in registry.lookup(q) if not country or p.country_code == country]
    return [registry.as_result(p, name=q if p.kind != "town" else None) for p in hits]


def search(q: str, limit: int = 8, client: httpx.Client | None = None,
           country: str | None = None) -> list[dict]:
    """Place search. country is an ISO-2 code that restricts the results to one country."""
    s = get_settings()
    if not q or len(q.strip()) < 2:
        return []
    q = q.strip()
    known = _known(q, country)
    online: list[dict] = []
    if s.weather_enabled:
        key = (_norm(q), limit, country)
        if client is None and key in _cache:
            online = [dict(x) for x in _cache[key]]
        else:
            own = client is None
            client = client or httpx.Client(timeout=s.weather_timeout_s)
            try:
                params = {"name": q, "count": limit, "language": "en", "format": "json"}
                if country:
                    params["countryCode"] = country
                r = client.get(s.openmeteo_geocoding_url, params=params)
                r.raise_for_status()
                online = [{
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
                } for x in r.json().get("results") or []]
                if own and len(_cache) < 2000:
                    _cache[key] = online
            except Exception as e:
                log.warning("geocoding failed, using the place registry: %s", e)
                if not known:
                    online = [h for h in offline_search(q, limit)
                              if not country or h["country_code"] == country]
            finally:
                if own:
                    client.close()
    elif not known:
        online = [h for h in offline_search(q, limit) if not country or h["country_code"] == country]
    # an online twin of a registry place (same town) adds nothing
    online = [o for o in online if not any(_km(o, k) < 5 for k in known)]
    return (known + online)[:max(limit, len(known))]


def _km(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["latitude"], a["longitude"], b["latitude"], b["longitude"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(min(1.0, math.sqrt(h)))


def _score(c: dict, rank: int, countries: set[str], near: list[dict],
           altitude: float | None = None) -> float:
    s = -0.5 * rank + 0.25 * math.log10((c.get("population") or 0) + 1)
    s += FEATURE_BONUS.get(c.get("feature") or "", 0.0)
    if countries and c.get("country_code") in countries:
        s += 2.0
    if near:
        # a stop is almost always within a day's travel of the stops around it
        s -= min(4.0, min(_km(c, n) for n in near) / 400)
    if altitude and c.get("elevation_m"):
        # "quota 3827" in the program: the Titicaca at 234 m in the Amazon is another place
        s -= min(3.0, abs(altitude - c["elevation_m"]) / 500)
    return s


def resolve_trip(names: list[str], limit: int = 5, client: httpx.Client | None = None,
                 text: str | None = None, altitudes: list[float | None] | None = None) -> list[list[dict]]:
    """Candidates for each stop, best first (see resolve_and_check)."""
    return resolve_and_check(names, limit, client, text, altitudes)[0]


def resolve_and_check(names: list[str], limit: int = 5, client: httpx.Client | None = None,
                      text: str | None = None, altitudes: list[float | None] | None = None,
                      ) -> tuple[list[list[dict]], list[Check], set[str]]:
    """Geocode the stops of one trip together and check the result.

    A name is read in the trip's countries (named in the text or shared by the other stops),
    near the stops around it and at the altitude the program gives, so "Aguas Calientes" after
    Cusco is the Peruvian one, not Mexico's. A stop that still fails a check (another country,
    thousands of km from its neighbours, wrong altitude) is searched again inside the trip's
    countries; if nothing fits, its Check says why and the app asks the traveller.
    Returns (candidates per stop best first, a Check per stop, the trip's countries)."""
    altitudes = altitudes or [None] * len(names)
    cands = [search(n, limit=10, client=client) for n in names]
    votes: dict[str, float] = {}
    for cs in cands:
        seen = set()
        for rank, c in enumerate(cs):
            cc = c.get("country_code")
            if cc and cc not in seen:
                seen.add(cc)
                votes[cc] = votes.get(cc, 0) + (1.0 if rank == 0 else 0.5)
    possible = [{c.get("country_code") for c in cs[:5] if c.get("country_code")} for cs in cands]
    named = expected_countries(text, [], possible)
    for cc in named:
        votes[cc] = votes.get(cc, 0) + 2.0
    countries: set[str] = set(named)
    if votes and len(names) > 1:
        top = max(votes.values())
        # a trip can cross borders (Patagonia): keep every country with real support
        countries |= {cc for cc, v in votes.items() if v >= max(1.5, top / 2)}
    ranks = [list(range(len(cs))) for cs in cands]

    def widen(i: int, among: set[str]):
        """Search stop i again inside each of the trip's countries."""
        known = {(round(c["latitude"], 3), round(c["longitude"], 3)) for c in cands[i]}
        for cc in sorted(among, key=lambda k: -votes.get(k, 0)):
            # ranked within the country's own list: the 2nd Peruvian "Aguas Calientes"
            # is not 12th just because ten foreign ones came first
            for r, c in enumerate(search(names[i], limit=10, client=client, country=cc)):
                k = (round(c["latitude"], 3), round(c["longitude"], 3))
                if k not in known:
                    known.add(k)
                    cands[i].append(c)
                    ranks[i].append(r)

    if countries:
        for i, cs in enumerate(cands):
            if not any(c.get("country_code") in countries for c in cs[:3]):
                widen(i, countries)

    chosen: list[dict | None] = [None] * len(names)

    def pick(i: int, pool=None):
        rs = pool if pool is not None else list(zip(ranks[i], cands[i]))
        if not rs:
            return None
        near = [chosen[j] for j in (i - 1, i + 1) if 0 <= j < len(names) and chosen[j]]
        return max(rs, key=lambda rc: _score(rc[1], rc[0], countries, near, altitudes[i]))[1]

    for _ in range(2):  # pass 1 without neighbours known, pass 2 with them
        for i in range(len(names)):
            chosen[i] = pick(i)

    def checks():
        idx = [i for i, c in enumerate(chosen) if c]
        got = check_stops([chosen[i] for i in idx], countries, [altitudes[i] for i in idx])
        out = [Check() for _ in names]
        for i, c in zip(idx, got):
            out[i] = c
        return out

    result = checks()
    # second chance for what failed: the best candidate that passes, searching the trip's
    # countries if needed. Only one stop at a time, so a wrong stop cannot drag a right one.
    for i, c in enumerate(result):
        if c.status == "ok" or not chosen[i]:
            continue
        if countries:
            widen(i, countries)
        before = chosen[i]
        for _, alt in sorted(zip(ranks[i], cands[i]), key=lambda rc: -_score(
                rc[1], rc[0], countries, [chosen[j] for j in (i - 1, i + 1)
                                          if 0 <= j < len(names) and chosen[j]], altitudes[i])):
            chosen[i] = alt
            if checks()[i].status == "ok":
                break
        else:
            chosen[i] = before
        result = checks()
    out = []
    for i, cs in enumerate(cands):
        if not chosen[i]:
            out.append([])
            continue
        rest = [c for c in cs if c is not chosen[i]]
        # the alternatives worth offering first: those in the trip's countries
        rest.sort(key=lambda c: c.get("country_code") not in countries)
        out.append([chosen[i]] + rest[: limit - 1])
    return out, result, countries
