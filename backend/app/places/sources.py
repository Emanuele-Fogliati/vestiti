"""Independent public sources that say where a place is, used to verify the place registry.

- GeoNames (through Open-Meteo's geocoding API): towns with country code and elevation.
- Wikidata: the country a place is in (P17), its coordinates (P625) and elevation (P2044).
- OpenStreetMap (Nominatim): which country a coordinate falls in (reverse geocoding), and where
  a named place or sight is (search).
- SRTM 90 m elevation model (OpenTopoData): the ground height at a coordinate.
- Wikidata, when it answers (it rate-limits shared IPs): country (P17), coordinates, elevation.

Only the audit uses these (app.places.audit); the app itself reads the verified registry.
Answers are cached on disk so re-running the audit does not hit the services again.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import httpx

UA = "Thruwear-place-audit/1.0 (https://github.com/Emanuele-Fogliati/vestiti)"
WIKIDATA = "https://www.wikidata.org/w/api.php"
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
GEONAMES = "https://geocoding-api.open-meteo.com/v1/search"
NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
SRTM = "https://api.opentopodata.org/v1/srtm90m"


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 12742 * math.asin(math.sqrt(min(1.0, a)))


class Sources:
    def __init__(self, cache: Path | None = None, client: httpx.Client | None = None):
        self.cache_path = cache
        self.cache: dict[str, object] = {}
        if cache and cache.is_file():
            self.cache = json.loads(cache.read_text(encoding="utf-8"))
        self.client = client or httpx.Client(timeout=30, headers={"User-Agent": UA})
        self._last_osm = 0.0

    def save(self):
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache), encoding="utf-8")

    def _get(self, url: str, params: dict, key: str, polite: float = 0.0):
        if key in self.cache:
            return self.cache[key]
        for attempt in range(4):
            if polite:
                wait = self._last_osm + polite - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._last_osm = time.monotonic()
            try:
                r = self.client.get(url, params=params)
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError("busy", request=r.request, response=r)
                r.raise_for_status()
                data = r.json()
                self.cache[key] = data
                return data
            except (httpx.HTTPError, ValueError):
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        return None

    # ------------------------------------------------------------ GeoNames
    def geonames(self, name: str, country: str | None = None, count: int = 10) -> list[dict]:
        params = {"name": name, "count": count, "language": "en", "format": "json"}
        if country:
            params["countryCode"] = country
        data = self._get(GEONAMES, params, f"gn|{name}|{country}|{count}")
        return [{"id": x.get("id"), "name": x["name"], "country_code": x.get("country_code"),
                 "admin": x.get("admin1"), "latitude": x["latitude"], "longitude": x["longitude"],
                 "elevation_m": x.get("elevation") if (x.get("elevation") or 0) > -1000 else None,
                 "feature": x.get("feature_code"),
                 "population": x.get("population") or 0}
                for x in (data or {}).get("results") or []]

    # ------------------------------------------------------------ OpenStreetMap
    def osm_country(self, lat: float, lon: float) -> str | None:
        """ISO code of the country this point is in, None on water or no answer."""
        params = {"format": "json", "lat": f"{lat:.4f}", "lon": f"{lon:.4f}", "zoom": 3,
                  "accept-language": "en"}
        data = self._get(NOMINATIM, params, f"osm|{lat:.4f}|{lon:.4f}", polite=1.1)
        cc = ((data or {}).get("address") or {}).get("country_code")
        return cc.upper() if cc else None

    def osm_search(self, name: str, country: str, limit: int = 5, kind: str | None = None) -> list[dict]:
        """Named places in a country. kind (town | site | lake | region) keeps only what can be
        that: a hotel or a street called "Moray" in Cusco is not the Moray terraces."""
        params = {"q": name, "countrycodes": country.lower(), "format": "json", "limit": limit,
                  "accept-language": "en", "addressdetails": 1}
        data = self._get(NOMINATIM_SEARCH, params, f"osms|{name}|{country}", polite=1.1)
        return [{"name": x.get("name") or x.get("display_name", "").split(",")[0],
                 "country_code": ((x.get("address") or {}).get("country_code") or "").upper() or None,
                 "latitude": float(x["lat"]), "longitude": float(x["lon"]),
                 "kind": f"{x.get('class')}:{x.get('type')}", "osm": f"{x.get('osm_type')}/{x.get('osm_id')}"}
                for x in data or [] if _fits(x.get("class"), x.get("type"), kind)]

    # ------------------------------------------------------------ elevation
    def srtm(self, points: list[tuple[float, float]]) -> list[float | None]:
        """Ground height (m) at each point from the SRTM 90 m model, None where unknown."""
        out: list[float | None] = []
        for k in range(0, len(points), 90):
            chunk = points[k:k + 90]
            locs = "|".join(f"{a:.4f},{b:.4f}" for a, b in chunk)
            data = self._get(SRTM, {"locations": locs}, f"srtm|{locs}", polite=1.1)
            out += [r.get("elevation") for r in (data or {}).get("results", [])] or [None] * len(chunk)
        return out

    # ------------------------------------------------------------ Wikidata
    def _entities(self, ids: list[str]) -> dict:
        out = {}
        todo = [i for i in ids if f"wd|{i}" not in self.cache]
        for k in range(0, len(todo), 40):
            chunk = todo[k:k + 40]
            data = self._get(WIKIDATA, {"action": "wbgetentities", "ids": "|".join(chunk),
                                        "props": "claims|labels", "languages": "en",
                                        "format": "json"}, f"wdb|{'|'.join(chunk)}")
            for qid, ent in (data or {}).get("entities", {}).items():
                self.cache[f"wd|{qid}"] = _slim(ent)
        for i in ids:
            out[i] = self.cache.get(f"wd|{i}")
        return out

    def _iso(self, country_qids: list[str]) -> list[str]:
        ents = self._entities(country_qids)
        return [e["iso"] for e in ents.values() if e and e.get("iso")]

    def wikidata(self, qid: str) -> dict | None:
        ent = self._entities([qid]).get(qid)
        if not ent:
            return None
        return {**ent, "countries": self._iso(ent.get("p17", []))}

    def wikidata_find(self, name: str, country: str, near: tuple[float, float] | None = None,
                      max_km: float = 60) -> dict | None:
        """The Wikidata item called `name` that is in `country` (closest to `near`, if given)."""
        hits = []
        for lang in ("en", "it", "es"):
            data = self._get(WIKIDATA, {"action": "wbsearchentities", "search": name, "language": lang,
                                        "limit": 10, "format": "json"}, f"wds|{name}|{lang}")
            hits += [h["id"] for h in (data or {}).get("search", []) if h["id"] not in hits]
        best = None
        for qid in hits:
            w = self.wikidata(qid)
            if not w or country not in w["countries"] or w.get("lat") is None:
                continue
            d = km(near[0], near[1], w["lat"], w["lon"]) if near else 0.0
            if near and d > max_km:
                continue
            if best is None or d < best[0]:
                best = (d, {**w, "qid": qid})
        return best[1] if best else None


OSM_KINDS = {
    "town": {"place"},
    "site": {"tourism", "historic", "natural", "leisure", "boundary", "place", "heritage", "waterway"},
    "lake": {"natural", "water", "place"},
    "region": {"boundary", "place", "natural", "leisure"},
}
NOT_A_SIGHT = {"hotel", "hostel", "guest_house", "apartment", "motel", "camp_site", "information",
               "house", "yes", "attraction_shop"}


def _fits(cls: str | None, typ: str | None, kind: str | None) -> bool:
    if kind is None:
        return True
    if cls not in OSM_KINDS.get(kind, {cls}):
        return False
    if kind == "lake" and cls == "natural" and typ not in ("water", "bay"):
        return False
    return typ not in NOT_A_SIGHT


def _slim(ent: dict) -> dict:
    claims = ent.get("claims", {})

    def vals(p):
        return [c["mainsnak"].get("datavalue", {}).get("value") for c in claims.get(p, [])
                if c.get("mainsnak", {}).get("snaktype") == "value"
                and c.get("rank") != "deprecated"]
    out: dict = {"label": (ent.get("labels", {}).get("en") or {}).get("value")}
    out["p17"] = [v["id"] for v in vals("P17") if isinstance(v, dict) and "id" in v]
    iso = [v for v in vals("P297") if isinstance(v, str)]
    if iso:
        out["iso"] = iso[0].upper()
    coords = [v for v in vals("P625") if isinstance(v, dict) and "latitude" in v]
    if coords:
        out["lat"], out["lon"] = coords[0]["latitude"], coords[0]["longitude"]
    el = []
    for v in vals("P2044"):
        try:
            unit = v.get("unit", "")
            amount = float(v["amount"])
            if unit.endswith("Q3710"):  # feet
                amount *= 0.3048
            el.append(amount)
        except (TypeError, ValueError, KeyError, AttributeError):
            pass
    if el:
        out["elevation_m"] = el[0]
    return out
