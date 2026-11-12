"""Brands the traveller prefers: spelling them the way the catalog does.

"arcteryx", "north face" or "Quechua" typed or said in the chat must match the catalog's
"Arc'teryx", "The North Face" and "Decathlon", or the preference silently does nothing.
A brand we don't sell is kept as typed, and the profile says it isn't in the catalog yet.
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product

# what people type -> the catalog's brand
ALIASES = {
    "arcteryx": "Arc'teryx", "arcterix": "Arc'teryx", "northface": "The North Face",
    "tnf": "The North Face", "quechua": "Decathlon", "forclaz": "Decathlon",
    "simond": "Decathlon", "wedze": "Decathlon", "kalenji": "Decathlon", "solognac": "Decathlon",
    "fjallraven": "Fjällräven", "hellyhansen": "Helly Hansen", "hh": "Helly Hansen",
    "mountainwarehouse": "Mountain Warehouse", "outdoorresearch": "Outdoor Research",
    "or": "Outdoor Research", "montbel": "Montbell", "mont-bell": "Montbell",
}
HIDDEN = {"generic", "unknown", ""}


def key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def catalog_brands(db: Session) -> list[str]:
    rows = db.scalars(select(Product.brand).where(Product.active.is_(True)).distinct()).all()
    return sorted({b for b in rows if b and b.lower() not in HIDDEN}, key=str.lower)


def canon(db: Session, names: list[str] | None, catalog: list[str] | None = None) -> list[str]:
    """Catalog spelling for each name; unknown names are kept as typed. Order kept,
    duplicates (after mapping) dropped."""
    if not names:
        return []
    catalog = catalog if catalog is not None else catalog_brands(db)
    by_key = {key(b): b for b in catalog}
    out: list[str] = []
    for n in names:
        k = key(n)
        if not k:
            continue
        b = by_key.get(k) or ALIASES.get(k)
        if b is None:
            b = " ".join(n.split())
        if b.lower() not in {x.lower() for x in out}:
            out.append(b)
    return out


def unknown(names: list[str], catalog: list[str]) -> list[str]:
    have = {b.lower() for b in catalog}
    return [n for n in names if n.lower() not in have]
