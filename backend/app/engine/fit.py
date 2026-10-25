"""Star rating (1-5) of how well one garment fits one slot requirement of one trip.

The score is a weighted mix of warmth match, weather protection, breathability, weight
and shopper rating. A hard requirement that is not met (e.g. not waterproof when the trip
needs it) caps the item at 2 stars and the optimizer will not pick it automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.engine.garments import FOOTWEAR_TYPES, SLOT_BY_KEY

TYPICAL_WEIGHT_G = {
    "base_top": 180, "base_bottom": 160, "mid_top": 350, "insulation_top": 420,
    "shell_top": 380, "trousers": 380, "shell_bottom": 280, "headwear": 70, "gloves": 90,
    "sun_hat": 90, "socks": 70, "footwear": 950,
}
WARMTH_SLOTS = {"base_top", "base_bottom", "mid_top", "insulation_top", "trousers", "headwear",
                "gloves"}


@dataclass
class ItemSpec:
    slot: str
    clo: float
    waterproof_mm: int = 0
    waterproof: bool = False
    windproof: bool = False
    breathability_g: int | None = None
    weight_g: float | None = None
    packable: bool = False
    insulation: str | None = None  # down | synthetic | fleece | merino | synthetic_base | cotton
    footwear_type: str | None = None
    ankle_support: bool = False
    insulated: bool = False
    rating: float | None = None
    review_count: int = 0


@dataclass
class FitResult:
    stars: float
    score: float
    passes: bool
    issues: list[str] = field(default_factory=list)
    positives: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"stars": self.stars, "score": round(self.score, 3), "passes": self.passes,
                "issues": self.issues, "positives": self.positives}


def score_item(req, item: ItemSpec) -> FitResult:
    """req is a strategy.SlotRequirement."""
    parts: list[tuple[float, float]] = []  # (weight, value)
    issues: list[str] = []
    positives: list[str] = []
    passes = True
    name = SLOT_BY_KEY[req.slot].name.lower()

    # hard requirements
    waterproof = item.waterproof or item.waterproof_mm >= 5000
    if req.waterproof and not waterproof:
        passes = False
        issues.append(f"not waterproof, and this trip needs a waterproof {name}")
    if req.slot == "footwear" and req.footwear_type:
        have = FOOTWEAR_TYPES.index(item.footwear_type) if item.footwear_type in FOOTWEAR_TYPES else 1
        need = FOOTWEAR_TYPES.index(req.footwear_type)
        if have < need:
            passes = False
            issues.append(f"too light for the terrain: you need at least a "
                          f"{req.footwear_type.replace('_', ' ')}")
            parts.append((0.35, 0.2))
        elif have == need:
            parts.append((0.35, 1.0))
            positives.append("right type for your activities")
        else:
            parts.append((0.35, 0.75))
            issues.append("more technical (and heavier) than the trip needs")
        if req.ankle_support and not item.ankle_support:
            passes = False
            issues.append("no ankle support for hard terrain")
        if req.insulated:
            if item.insulated:
                positives.append("insulated for sub-zero days")
            else:
                parts.append((0.15, 0.4))
                issues.append("not insulated: cold feet below -5 °C")

    # warmth
    if req.slot in WARMTH_SLOTS and req.ref_clo > 0:
        ratio = item.clo / req.ref_clo
        if ratio < 1:
            v = max(0.0, 1 - (1 - ratio) * 2)
            issues.append(f"less warm than the plan assumes ({item.clo:.2f} vs {req.ref_clo:.2f} clo)")
        elif ratio <= 1.5:
            v = 1.0
            positives.append("warmth matches the plan")
        else:
            v = max(0.6, 1 - (ratio - 1.5) * 0.5)
            issues.append("warmer than needed: may be bulky")
        parts.append((0.35, v))

    # weather protection
    if req.slot in ("shell_top", "shell_bottom"):
        if req.waterproof:
            grade = req.waterproof_grade_mm or 10000
            mm = item.waterproof_mm or (10000 if item.waterproof else 0)
            if mm >= grade:
                v = 1.0
                positives.append(f"{mm:,} mm waterproof rating")
            elif mm >= grade / 2:
                v = 0.7
                issues.append(f"{mm:,} mm: fine for showers, may wet out in long rain")
            else:
                v = 0.3
            parts.append((0.3, v))
        if req.windproof:
            parts.append((0.1, 1.0 if (item.windproof or waterproof) else 0.5))
    if req.slot == "footwear" and req.waterproof:
        if waterproof:
            parts.append((0.2, 1.0))
            positives.append("waterproof")
        else:
            parts.append((0.2, 0.3))
            issues.append("not waterproof: wet feet on rainy trail days")

    # breathability
    if req.breathable_high:
        if req.slot == "shell_top":
            b = item.breathability_g
            v = 0.6 if b is None else (1.0 if b >= 15000 else 0.75 if b >= 10000 else 0.45)
            if b and b >= 15000:
                positives.append("very breathable for hard efforts")
            parts.append((0.15, v))
        elif item.insulation == "cotton":
            parts.append((0.2, 0.15))
            issues.append("cotton holds sweat and chills you at stops")
        elif item.insulation in ("merino", "synthetic_base", "fleece", "synthetic"):
            parts.append((0.15, 1.0))
            positives.append(f"{item.insulation.replace('_base', '')} handles sweat")

    # weight / packability
    if req.packable or req.slot in ("footwear",):
        typical = TYPICAL_WEIGHT_G.get(req.slot, 300)
        if item.weight_g:
            r = item.weight_g / typical
            v = 1.0 if r <= 0.8 else 0.75 if r <= 1.2 else 0.5
            if r <= 0.8:
                positives.append(f"light ({item.weight_g:.0f} g)")
            parts.append((0.1, v))
        if item.packable and req.packable:
            parts.append((0.05, 1.0))
            positives.append("packs small")

    # shopper rating (shrunk towards neutral with few reviews)
    if item.rating is not None:
        conf = min(item.review_count / 50.0, 1.0)
        v = 0.6 * (1 - conf) + conf * max(0.0, min(1.0, (item.rating - 3.0) / 2.0))
        parts.append((0.15, v))
    else:
        parts.append((0.05, 0.6))

    total_w = sum(w for w, _ in parts) or 1.0
    score = sum(w * v for w, v in parts) / total_w
    stars = round((1 + 4 * score) * 2) / 2
    if not passes:
        stars = min(stars, 2.0)
    return FitResult(stars=stars, score=score, passes=passes, issues=issues, positives=positives)
