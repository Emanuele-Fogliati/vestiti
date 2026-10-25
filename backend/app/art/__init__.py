"""Stop illustrations that show the place itself (Machu Picchu, Cusco cathedral, ...).

A library of hand-drawn landmark scenes, organised by country:
  catalog/<cc>.json          the places of one country (slug, label, coordinates, radius, aliases)
  landmarks/<cc>/<slug>.svg  one SVG fragment per place, drawn to docs/LANDMARK_STYLE.md
A place's id is "<cc>-<slug>" (e.g. "pe-machu-picchu"). A place is drawn once and reused by
every trip that visits it. Stops with no landmark nearby get no art here and the frontend
falls back to the generic terrain scene.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
SVG_DIR = HERE / "landmarks"


@dataclass(frozen=True)
class Landmark:
    id: str
    label: str
    country: str
    lat: float
    lon: float
    radius_km: float
    aliases: tuple[str, ...]


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


CATALOG_DIR = HERE / "catalog"


@lru_cache
def landmarks() -> tuple[Landmark, ...]:
    out = []
    for f in sorted(CATALOG_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        cc = data["country"].upper()
        for d in data["places"]:
            out.append(Landmark(id=f"{cc.lower()}-{d['slug']}", label=d["label"], country=cc, lat=d["lat"],
                                lon=d["lon"], radius_km=d["radius_km"],
                                aliases=tuple(_norm(a) for a in d["aliases"])))
    return tuple(out)


def svg_path(landmark_id: str) -> Path | None:
    m = re.fullmatch(r"([a-z]{2})-([a-z0-9-]+)", landmark_id)
    return SVG_DIR / m[1] / f"{m[2]}.svg" if m else None


@lru_cache
def svg(landmark_id: str) -> str | None:
    f = svg_path(landmark_id)
    return f.read_text(encoding="utf-8") if f is not None and f.is_file() else None


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, a)))


def _named(text: str) -> list[Landmark]:
    """Landmarks whose alias appears as whole words in the text, in order of appearance."""
    t = f" {_norm(text)} "
    hits = []
    for lm in landmarks():
        pos = [t.find(f" {a} ") for a in lm.aliases if f" {a} " in t]
        if pos:
            hits.append((min(pos), lm))
    return [lm for _, lm in sorted(hits, key=lambda h: h[0])]


def _nearest(lat: float, lon: float) -> Landmark | None:
    best = None
    for lm in landmarks():
        d = _km(lat, lon, lm.lat, lm.lon)
        if d <= lm.radius_km and (best is None or d < best[0]):
            best = (d, lm)
    return best[1] if best else None


def match(name: str, lat: float | None, lon: float | None, notes: str | None = None,
          taken: set[str] | frozenset[str] = frozenset()) -> Landmark | None:
    """The landmark for one stop: named in the stop's name, else the nearest one within its radius.

    When that landmark is already used by an earlier stop of the trip (Cusco twice), a different
    landmark named in the stop's notes wins (the second Cusco stop is the Rainbow Mountain day)."""
    own = next(iter(_named(name)), None)
    if own is None and lat is not None and lon is not None:
        own = _nearest(lat, lon)
    if own is not None and own.id in taken and notes:
        other = next((lm for lm in _named(notes) if lm.id not in taken), None)
        if other is not None:
            return other
    return own


def assign(stops) -> list[Landmark | None]:
    """One landmark (or None) per stop, in trip order. stops: objects with name, latitude, longitude, notes."""
    taken: set[str] = set()
    out = []
    for s in stops:
        lm = match(s.name, getattr(s, "latitude", None), getattr(s, "longitude", None),
                   getattr(s, "notes", None), taken)
        if lm is not None:
            taken.add(lm.id)
        out.append(lm)
    return out
