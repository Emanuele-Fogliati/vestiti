"""Stop illustrations that show the place itself (Machu Picchu, Cusco cathedral, ...).

A library of hand-drawn landmark scenes, organised by country:
  catalog/<cc>.json          the places of one country (slug, label, coordinates, radius, aliases,
                             palette = the place's real colours for the --il-* tokens)
  landmarks/<cc>/<slug>.svg  one flat SVG fragment per place, drawn to docs/LANDMARK_STYLE.md
render.py gives a scene the official look (palette, comic outline, paper shadow) when it is served.
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
    palette: tuple[tuple[str, str], ...] = ()
    # matched only when they are the whole name: "Rome" gets the Colosseum, "Catacombs of Rome" does not
    names: tuple[str, ...] = ()
    # a gateway town shows the sight it is the base for ("Aguas Calientes" = Machu Picchu), unless the
    # trip also has that sight as a stop of its own: then the town shows its own scene
    gateway: str = ""


# letters NFKD cannot split into base + accent: "Tromsø" must read "tromso", not "troms"
_FOLD = str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "đ": "d", "ð": "d", "ł": "l", "þ": "th",
                       "ı": "i", "ħ": "h"})


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower().translate(_FOLD)) if not unicodedata.combining(c))
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
                                aliases=tuple(_norm(a) for a in d["aliases"]),
                                palette=tuple(d.get("palette", {}).items()),
                                names=tuple(_norm(a) for a in d.get("names", [])),
                                gateway=d.get("gateway", "")))
    return tuple(out)


def svg_path(landmark_id: str) -> Path | None:
    m = re.fullmatch(r"([a-z]{2})-([a-z0-9-]+)", landmark_id)
    return SVG_DIR / m[1] / f"{m[2]}.svg" if m else None


@lru_cache
def by_id() -> dict[str, Landmark]:
    return {lm.id: lm for lm in landmarks()}


@lru_cache
def svg(landmark_id: str) -> str | None:
    f = svg_path(landmark_id)
    return f.read_text(encoding="utf-8") if f is not None and f.is_file() else None


def rendered(landmark_id: str) -> str | None:
    """The scene with the official look, as the app shows it (see render.py)."""
    body = svg(landmark_id)
    if body is None:
        return None
    from app.art.render import render
    lm = by_id().get(landmark_id)
    return render(landmark_id, body, dict(lm.palette) if lm else None)


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(min(1.0, a)))


NAMESAKE_KM = 250  # a stop named after a landmark but farther than this is a different place


@lru_cache
def _alias_index() -> tuple[dict[str, list[tuple[int, Landmark]]], dict[str, list[tuple[int, Landmark]]], int]:
    """Every alias and every exact name -> the landmarks that use it (with their catalog order),
    and the most words an alias has. Looking a text's word runs up here is what makes matching
    6,900 globe places take milliseconds instead of 20 seconds (one scan of 5,000 landmarks each)."""
    aliases: dict[str, list[tuple[int, Landmark]]] = {}
    names: dict[str, list[tuple[int, Landmark]]] = {}
    longest = 1
    for i, lm in enumerate(landmarks()):
        for a in lm.aliases:
            aliases.setdefault(a, []).append((i, lm))
            longest = max(longest, a.count(" ") + 1)
        for a in lm.names:
            names.setdefault(a, []).append((i, lm))
    return aliases, names, longest


def _named(text: str, lat: float | None = None, lon: float | None = None) -> list[Landmark]:
    """Landmarks whose alias appears as whole words in the text, in order of appearance.

    Two landmarks named at the same position ("red fort of agra" / "red fort") go nearest first,
    then the longer, more specific alias ("golden temple of dambulla" beats "golden temple")."""
    n = _norm(text)
    t = f" {n} "
    aliases, names, longest = _alias_index()
    best: dict[int, tuple[int, int, Landmark]] = {}  # catalog order -> (position, -length, landmark)

    def hit(i: int, lm: Landmark, at: tuple[int, int]) -> None:
        if i not in best or at < best[i][:2]:
            best[i] = (*at, lm)

    words = n.split(" ") if n else []
    for i in range(len(words)):
        for j in range(i + 1, min(len(words), i + longest) + 1):
            a = " ".join(words[i:j])
            for k, lm in aliases.get(a, ()):
                hit(k, lm, (t.find(f" {a} "), -len(a)))
    for k, lm in names.get(n, ()):
        hit(k, lm, (0, -len(n)))
    near = (lambda lm: _km(lat, lon, lm.lat, lm.lon)) if lat is not None and lon is not None else (lambda lm: 0)
    hits = sorted(best.items())  # catalog order first, as the plain scan found them
    return [lm for _, _, lm in sorted((h for _, h in hits), key=lambda h: (h[0], near(h[2]), h[1]))]


def named_near(text: str, lat: float | None, lon: float | None, country: str | None = None) -> Landmark | None:
    """The landmark a thing to do names ("Laguna de los Tres", "Perito Moreno glacier"), in the
    stop's country and near it, or None: never the nearest one by distance alone."""
    cc = (country or "").upper()
    for lm in _named(text, lat, lon):
        if cc and lm.country != cc:
            continue
        if lat is not None and lon is not None and _km(lat, lon, lm.lat, lm.lon) > NAMESAKE_KM:
            continue
        return lm
    return None


def _nearest(lat: float, lon: float, country: str = "") -> Landmark | None:
    best = None
    for lm in landmarks():
        if country and lm.country != country:
            continue
        d = _km(lat, lon, lm.lat, lm.lon)
        if d <= lm.radius_km and (best is None or d < best[0]):
            best = (d, lm)
    return best[1] if best else None


def match(name: str, lat: float | None, lon: float | None, notes: str | None = None,
          taken: set[str] | frozenset[str] = frozenset(), country: str | None = None,
          elsewhere: set[str] | frozenset[str] = frozenset(), gateway: bool = True) -> Landmark | None:
    """The landmark for one stop: named in the stop's name, else the nearest one within its radius.

    When that landmark is already used by an earlier stop of the trip (Cusco twice), a different
    landmark named in the stop's notes wins (the second Cusco stop is the Rainbow Mountain day).
    A stop in a known country never gets another country's landmark (Aguas Calientes, Mexico
    is not Machu Picchu).

    A gateway town gets the sight it leads to, unless that sight is taken or is another stop's own
    place (elsewhere): a trip with both "Aguas Calientes" and "Machu Picchu" shows the town and the ruins."""
    cc = (country or "").upper()
    named = [lm for lm in _named(name, lat, lon) if not cc or lm.country == cc]
    if lat is not None and lon is not None:  # a namesake far away is another place (Venice Beach)
        named = [lm for lm in named if _km(lat, lon, lm.lat, lm.lon) <= NAMESAKE_KM]
    own = next(iter(named), None)
    if own is None and lat is not None and lon is not None:
        own = _nearest(lat, lon, cc)
    if gateway and own is not None and own.gateway and own.gateway not in taken and own.gateway not in elsewhere:
        own = by_id().get(own.gateway, own)
    if own is not None and own.id in taken and notes:
        other = next((lm for lm in _named(notes) if lm.id not in taken and (not cc or lm.country == cc)), None)
        if other is not None:
            return other
    return own


def assign(stops) -> list[Landmark | None]:
    """One landmark (or None) per stop, in trip order. stops: objects with name, latitude, longitude, notes."""
    stops = list(stops)
    raw = [match(s.name, getattr(s, "latitude", None), getattr(s, "longitude", None),
                 country=getattr(s, "country_code", None), gateway=False) for s in stops]
    taken: set[str] = set()
    out = []
    for i, s in enumerate(stops):
        elsewhere = {lm.id for j, lm in enumerate(raw) if lm is not None and j != i}
        lm = match(s.name, getattr(s, "latitude", None), getattr(s, "longitude", None),
                   getattr(s, "notes", None), taken, getattr(s, "country_code", None), elsewhere)
        if lm is not None:
            taken.add(lm.id)
        out.append(lm)
    return out
