"""How organised trips really go: where they sleep, for how long, in which order, and what they
see in one day from each place (patterns.json.gz, tools/guide/build_patterns.py).

Derived facts only, read from the trips of the inventory. The counts behind them never leave the
server (Manu, 2026-10-26).
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Trip:
    operator: str
    length: int
    stays: tuple[tuple[str, int], ...]  # (place id, days), in order


@lru_cache
def _doc() -> dict:
    f = HERE / "patterns.json.gz"
    if not f.is_file():
        return {"places": [], "operators": [], "trips": [], "outings": {}, "way": {}}
    with gzip.open(f, "rt", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache
def trips() -> tuple[Trip, ...]:
    d = _doc()
    ps, ops = d["places"], d["operators"]
    return tuple(Trip(ops[o], n, tuple((ps[i], days) for i, days in st)) for o, n, st in d["trips"])


@lru_cache
def outings() -> dict[str, tuple[tuple[tuple[str, ...], int, int], ...]]:
    """{place you sleep in: ((sights seen together on one day out), weight, days it takes)}, most
    done first. Days > 1: a trek or a trip with nights away (the Inca Trail)."""
    d = _doc()
    ps = d["places"]
    return {ps[int(k)]: tuple((tuple(ps[i] for i in g[0]), g[1], g[2] if len(g) > 2 else 1) for g in v)
            for k, v in d["outings"].items()}


@lru_cache
def way() -> dict[tuple[str, str], tuple[str, ...]]:
    """{(from, to): sights trips see on the way}."""
    d = _doc()
    ps = d["places"]
    out = {}
    for k, v in d["way"].items():
        a, b = k.split(">")
        out[(ps[int(a)], ps[int(b)])] = tuple(ps[i] for i in v)
    return out
