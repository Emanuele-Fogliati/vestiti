"""Country names and codes: which countries a trip text talks about ("Perù e Bolivia")."""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

SEED = Path(__file__).resolve().parents[2] / "seed" / "countries.json"

# regions travellers name instead of a country: the countries they lie in
REGIONS = {
    "patagonia": ["AR", "CL"], "tierra del fuego": ["AR", "CL"], "terra del fuoco": ["AR", "CL"],
    "atacama": ["CL"], "isola di pasqua": ["CL"], "easter island": ["CL"], "rapa nui": ["CL"],
    "galapagos": ["EC"], "lapponia": ["FI", "SE", "NO"], "lapland": ["FI", "SE", "NO"],
    "laponia": ["FI", "SE", "NO"], "scandinavia": ["NO", "SE", "DK"], "lofoten": ["NO"],
    "himalaya": ["NP", "IN", "BT"], "tibet": ["CN"], "bali": ["ID"], "borneo": ["MY", "ID", "BN"],
    "kilimanjaro": ["TZ"], "serengeti": ["TZ"], "zanzibar": ["TZ"], "dolomiti": ["IT"],
    "dolomites": ["IT"], "sicilia": ["IT"], "sardegna": ["IT"], "toscana": ["IT"],
    "canarie": ["ES"], "canary islands": ["ES"], "baleari": ["ES"], "azzorre": ["PT"],
    "azores": ["PT"], "madeira": ["PT"], "corsica": ["FR"], "creta": ["GR"], "crete": ["GR"],
    "cicladi": ["GR"], "cappadocia": ["TR"], "dalmazia": ["HR"], "hawaii": ["US"],
    "alaska": ["US"], "yucatan": ["MX"], "tasmania": ["AU"], "siberia": ["RU"],
    "uyuni": ["BO"],
    "svalbard": ["SJ"],
}


def norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


@lru_cache
def _data() -> dict[str, dict]:
    return json.loads(SEED.read_text(encoding="utf-8"))["countries"]


@lru_cache
def _index() -> dict[str, tuple[str, ...]]:
    idx: dict[str, tuple[str, ...]] = {}
    for cc, d in _data().items():
        for n in d["names"]:
            idx[n] = (cc,)
    for n, ccs in REGIONS.items():
        idx.setdefault(n, tuple(ccs))
    return idx


def name(cc: str | None) -> str | None:
    """English name of an ISO code ("PE" -> "Peru")."""
    if not cc:
        return None
    d = _data().get(cc.upper())
    return d["name"] if d else cc.upper()


def is_code(cc: str | None) -> bool:
    return bool(cc) and cc.upper() in _data()


def mentioned(text: str | None) -> dict[str, int]:
    """Countries a text names, directly or through a region, with how many times."""
    if not text:
        return {}
    t = f" {norm(text)} "
    out: dict[str, int] = {}
    for n, ccs in _index().items():
        k = t.count(f" {n} ")
        if k:
            for cc in ccs:
                out[cc] = out.get(cc, 0) + k
    return out
