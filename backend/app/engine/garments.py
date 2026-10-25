"""Clothing slots (what the layer strategy reasons about) and reference warmth values.

Garment clo values are approximations of ISO 9920 tables, rounded. They are used for
the reference kit and for wardrobe items the user describes only as light/medium/warm.
Real products carry their own clo estimate in specs.clo (see catalog/classify.py).
"""
from __future__ import annotations

from dataclasses import dataclass

LEVELS = ["light", "medium", "warm", "very_warm"]


@dataclass(frozen=True)
class Slot:
    key: str
    code: str  # L1 base, L2 mid/insulation, L3 shell, LEG, FT feet, EXT extremities
    name: str
    torso: bool = False
    insulating: bool = True


SLOTS: list[Slot] = [
    Slot("shell_top", "L3", "Shell jacket", torso=True),
    Slot("insulation_top", "L2", "Insulated jacket", torso=True),
    Slot("mid_top", "L2", "Fleece / mid layer", torso=True),
    Slot("base_top", "L1", "Base layer top", torso=True),
    Slot("base_bottom", "L1", "Base layer bottom"),
    Slot("trousers", "LEG", "Trousers / shorts"),
    Slot("shell_bottom", "L3", "Shell pants"),
    Slot("headwear", "EXT", "Beanie"),
    Slot("gloves", "EXT", "Gloves"),
    Slot("sun_hat", "EXT", "Sun hat", insulating=False),
    Slot("socks", "FT", "Socks"),
    Slot("footwear", "FT", "Footwear"),
]
SLOT_BY_KEY = {s.key: s for s in SLOTS}
SLOT_KEYS = [s.key for s in SLOTS]

REF_CLO: dict[str, dict[str, float]] = {
    "base_top": {"light": 0.09, "medium": 0.15, "warm": 0.22, "very_warm": 0.28},
    "base_bottom": {"light": 0.08, "medium": 0.12, "warm": 0.16, "very_warm": 0.20},
    "mid_top": {"light": 0.22, "medium": 0.32, "warm": 0.40, "very_warm": 0.48},
    "insulation_top": {"light": 0.45, "medium": 0.60, "warm": 0.80, "very_warm": 1.00},
    "shell_top": {"light": 0.10, "medium": 0.14, "warm": 0.18, "very_warm": 0.22},
    "trousers": {"light": 0.06, "medium": 0.20, "warm": 0.26, "very_warm": 0.32},
    "shell_bottom": {"light": 0.06, "medium": 0.08, "warm": 0.10, "very_warm": 0.12},
    "headwear": {"light": 0.02, "medium": 0.04, "warm": 0.05, "very_warm": 0.06},
    "gloves": {"light": 0.02, "medium": 0.04, "warm": 0.06, "very_warm": 0.08},
    "sun_hat": {"light": 0.01, "medium": 0.01, "warm": 0.01, "very_warm": 0.01},
    "socks": {"light": 0.02, "medium": 0.03, "warm": 0.04, "very_warm": 0.05},
    "footwear": {"light": 0.02, "medium": 0.04, "warm": 0.06, "very_warm": 0.08},
}

# Footwear types, from least to most technical
FOOTWEAR_TYPES = ["sandal", "sneaker", "trail_runner", "hiking_boot", "mountaineering_boot"]


def ref_clo(slot: str, level: str = "medium") -> float:
    return REF_CLO[slot][level]


def level_for_clo(slot: str, clo: float) -> str:
    """Closest warmth level for a clo value (used to label products)."""
    table = REF_CLO[slot]
    return min(table, key=lambda lv: abs(table[lv] - clo))


@dataclass
class KitItem:
    """One concrete garment in a kit: a product, an owned item, or the reference spec."""

    slot: str
    clo: float
    name: str
    source: str = "reference"  # reference | product | owned | rental
    waterproof: bool = False
    windproof: bool = False
    down: bool = False
    price: float = 0.0
    ref_id: str | None = None
    weight_g: float | None = None
    footwear_type: str | None = None
    ankle_support: bool = False
    level: str | None = None
    insulated: bool = False


def reference_item(slot: str, level: str) -> KitItem:
    return KitItem(
        slot=slot,
        clo=ref_clo(slot, level),
        name=f"{level.replace('_', ' ')} {SLOT_BY_KEY[slot].name.lower()}",
        waterproof=slot in ("shell_top", "shell_bottom"),
        windproof=slot in ("shell_top", "shell_bottom"),
        level=level,
    )
