"""The verified place registry: places whose country, coordinates and elevation were checked
against independent public sources (GeoNames, OpenStreetMap, SRTM; see app.places.audit).

seed/places.json is the source. `python -m app.cli seed` copies it into the `places` table.
A place id is "<cc>-<slug>" (pe-machu-picchu), the same id the landmark art uses.

kind: town (you sleep there), site (a sight: Machu Picchu), lake, region (Sacred Valley).
A sight's weather and altitude are those of its `base`, the town where travellers sleep to
see it: Machu Picchu -> Aguas Calientes, Titicaca -> Puno.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.places.countries import name as country_name
from app.places.countries import norm

SEED = Path(__file__).resolve().parents[2] / "seed" / "places.json"


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    kind: str
    country_code: str
    latitude: float
    longitude: float
    elevation_m: float
    admin: str | None = None
    base: str | None = None
    aliases: tuple[str, ...] = ()
    verified: bool = False
    source: str | None = None


def _place(d: dict) -> Place:
    v = d.get("verified") or {}
    return Place(id=d["id"], name=d["name"], kind=d.get("kind", "town"),
                 country_code=d["country_code"].upper(), latitude=d["latitude"],
                 longitude=d["longitude"], elevation_m=float(d.get("elevation_m") or 0.0),
                 admin=d.get("admin"), base=d.get("base"),
                 aliases=tuple(norm(a) for a in d.get("aliases", [])),
                 verified=bool(v.get("ok")), source=", ".join(v.get("sources", [])) or None)


@lru_cache
def places() -> tuple[Place, ...]:
    try:
        rows = json.loads(SEED.read_text(encoding="utf-8"))["places"]
    except FileNotFoundError:
        return ()
    return tuple(_place(d) for d in rows if d.get("latitude") is not None)


@lru_cache
def _by_id() -> dict[str, Place]:
    return {p.id: p for p in places()}


@lru_cache
def _by_name() -> dict[str, tuple[Place, ...]]:
    idx: dict[str, list[Place]] = {}
    for p in places():
        for n in {norm(p.name), *p.aliases}:
            idx.setdefault(n, []).append(p)
    return {k: tuple(v) for k, v in idx.items()}


def get(place_id: str) -> Place | None:
    return _by_id().get(place_id)


def lookup(q: str) -> tuple[Place, ...]:
    """Verified registry places called exactly this (name or alias): 'Titicaca' -> the Peruvian
    and the Bolivian side. Empty when the registry does not know the name. A place the audit
    could not verify is never used: the online search answers instead."""
    return tuple(p for p in _by_name().get(norm(q), ()) if p.verified)


def prefix(q: str, limit: int = 8) -> list[Place]:
    """Places whose name starts with / contains q, for the offline search box."""
    nq = norm(q)
    if not nq:
        return []
    ok = [p for p in places() if p.verified]
    starts = [p for p in ok if norm(p.name).startswith(nq)]
    inside = [p for p in ok if nq in norm(p.name) and p not in starts]
    return (starts + inside)[:limit]


def as_result(p: Place, name: str | None = None) -> dict:
    """The geocoding result for a registry place. A sight is placed at its base town (weather,
    altitude of the nights) but keeps its own name."""
    at = get(p.base) if p.base else None
    at = at or p
    return {
        "name": name or p.name,
        "admin": at.admin if at is not p else p.admin,
        "country": country_name(p.country_code),
        "country_code": p.country_code,
        "latitude": at.latitude,
        "longitude": at.longitude,
        "elevation_m": at.elevation_m,
        "feature": "REG",
        "population": 0,
        "source": "verified" if p.verified else "registry",
        "place_id": p.id,
        "base": at.name if at is not p else None,
    }


def seed_db(db) -> dict:
    """Copy seed/places.json into the `places` table (insert or update, by id)."""
    from datetime import date as _date

    from app.models import Place as Row
    rows = json.loads(SEED.read_text(encoding="utf-8"))["places"]
    have = {r.id: r for r in db.query(Row).all()}
    created = 0
    for d in rows:
        if d.get("latitude") is None:
            continue
        r = have.get(d["id"])
        if r is None:
            r = Row(id=d["id"])
            db.add(r)
            created += 1
        v = d.get("verified") or {}
        r.name, r.kind, r.country_code = d["name"], d.get("kind", "town"), d["country_code"].upper()
        r.admin, r.base, r.aliases = d.get("admin"), d.get("base"), d.get("aliases", [])
        r.latitude, r.longitude = d["latitude"], d["longitude"]
        r.elevation_m = float(d.get("elevation_m") or 0.0)
        r.verified = bool(v.get("ok"))
        r.verified_on = _date.fromisoformat(v["on"]) if v.get("on") else None
        r.sources, r.problems = v.get("sources", []), v.get("problems", [])
    db.commit()
    return {"places_created": created, "places": len(rows)}
