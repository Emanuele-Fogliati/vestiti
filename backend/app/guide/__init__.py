"""Place guide: a short, inviting description of a place and a fun fact about it.

Shown on every stop of the recommended itineraries and on any trip stop whose name we
know (so a trip the traveller types in gets it too). Each fun fact has a source in
places.json: add places there, with a source, and check the fact before adding it.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl

HERE = Path(__file__).resolve().parent


class PlaceGuide(BaseModel):
    names: list[str] = Field(min_length=1)
    country: str = Field(min_length=2, max_length=2)
    blurb: str = Field(min_length=20, max_length=240)
    fun_fact: str = Field(min_length=20, max_length=240)
    source: HttpUrl


class GuideOut(BaseModel):
    blurb: str
    fun_fact: str
    source: str


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


@lru_cache
def guides() -> tuple[PlaceGuide, ...]:
    data = json.loads((HERE / "places.json").read_text(encoding="utf-8"))
    return tuple(PlaceGuide.model_validate(d) for d in data)


@lru_cache
def _index() -> dict[str, list[PlaceGuide]]:
    out: dict[str, list[PlaceGuide]] = {}
    for g in guides():
        for n in g.names:
            out.setdefault(_norm(n), []).append(g)
    return out


def _candidates(name: str) -> list[str]:
    """'Colca Canyon (Chivay)' -> the whole name, 'Colca Canyon', 'Chivay';
    'Cusco, Peru' -> 'Cusco'."""
    out = [name]
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", name)
    if m:
        out += [m.group(1), m.group(2)]
    out += [p for p in re.split(r"[,/]", name) if p.strip()][:1]
    return [_norm(c) for c in out if c and c.strip()]


def lookup(name: str, country_code: str | None = None) -> GuideOut | None:
    idx = _index()
    for c in _candidates(name):
        for g in idx.get(c, []):
            if country_code and g.country != country_code.upper():
                continue  # "Vik" in Norway is not Vík in Iceland
            return GuideOut(blurb=g.blurb, fun_fact=g.fun_fact, source=str(g.source))
    return None
