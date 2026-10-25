"""Glue between the database, the weather service and the pure engine."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine import outfit as O
from app.engine.garments import REF_CLO, SLOT_BY_KEY, SLOTS
from app.engine.strategy import (
    Condition,
    SlotRequirement,
    StageInput,
    clarifying_questions,
    conditions_for_stage,
    evaluate,
    requirements,
)
from app.models import Product, RentalPartner, Trip, TripSelection, User, WardrobeItem
from app.weather.service import WeatherService

MODEL_NOTE = ("Warmth numbers come from a simplified heat-balance model (clo). It is an "
              "estimate, not a lab measurement: people differ, and real garments vary. Use it "
              "to compare options, and adjust 'I run cold / warm' in your profile.")


def owned_item(w: WardrobeItem) -> O.CatalogItem:
    clo = w.clo_override if w.clo_override is not None else REF_CLO[w.category][w.warmth]
    specs = {"clo": clo, "waterproof": w.waterproof, "windproof": w.windproof or w.waterproof,
             "insulation": {"synthetic": "synthetic_base" if w.category.startswith("base")
                            else "synthetic"}.get(w.material or "", w.material)}
    if w.waterproof and w.category in ("shell_top", "shell_bottom"):
        specs["waterproof_mm"] = 10000  # unknown rating: assume an average membrane
    if w.category == "footwear":
        specs["footwear_type"] = w.footwear_type or "sneaker"
        specs["ankle_support"] = w.ankle_support
        specs["insulated"] = w.warmth in ("warm", "very_warm")
    return O.CatalogItem(id=w.id, slot=w.category, name=w.name, brand=w.brand or "",
                         price=0.0, specs=specs, source="owned", merchant="Your wardrobe")


def product_item(p: Product) -> O.CatalogItem:
    return O.CatalogItem(id=p.id, slot=p.category, name=p.name, brand=p.brand, price=p.price,
                         specs=p.specs or {}, merchant=p.merchant, currency=p.currency,
                         url=p.url, image_url=p.image_url, rating=p.rating,
                         review_count=p.review_count, network=p.network, gender=p.gender)


@dataclass
class Computed:
    stages: list[StageInput]
    conds: list[Condition]
    reqs: dict[str, SlotRequirement]


class Planner:
    def __init__(self, db: Session, user: User, trip: Trip, weather: WeatherService | None = None):
        self.db = db
        self.user = user
        self.trip = trip
        self.weather = weather or WeatherService(db)
        self._computed: Computed | None = None

    # ------------------------------------------------------------ inputs
    def stage_inputs(self) -> list[StageInput]:
        out = []
        for i, s in enumerate(sorted(self.trip.stops, key=lambda s: (s.position, s.start_date))):
            days = self.weather.days_for(s.latitude, s.longitude, s.elevation_m or 0.0,
                                         s.start_date, s.end_date)
            out.append(StageInput(index=i, stop_id=s.id, name=s.name,
                                  base_elevation_m=s.elevation_m or 0.0, start=s.start_date,
                                  end=s.end_date, activities=s.activities or [{"type": "city"}],
                                  days=days, country_code=s.country_code))
        return out

    def compute(self) -> Computed:
        if self._computed is None:
            stages = self.stage_inputs()
            conds = []
            for st in stages:
                conds += conditions_for_stage(st, personal_offset=self.user.thermal_offset or 0.0,
                                              pace=self.user.pace or "average")
            reqs = requirements(stages, conds) if conds else {}
            self._computed = Computed(stages, conds, reqs)
        return self._computed

    def candidates(self, reqs) -> dict[str, list[O.CatalogItem]]:
        q = select(Product).where(Product.active.is_(True))
        pref = self.user.gender_pref or "any"
        if pref in ("men", "women"):
            q = q.where(Product.gender.in_([pref, "unisex"]))
        items = [product_item(p) for p in self.db.scalars(q).all()]
        return O.group_by_slot(O.rate(reqs, items))

    def owned(self, reqs) -> dict[str, list[O.CatalogItem]]:
        rows = self.db.scalars(select(WardrobeItem).where(WardrobeItem.user_id == self.user.id)).all()
        return O.group_by_slot(O.rate(reqs, [owned_item(w) for w in rows]))

    def selections(self) -> dict[tuple[str, str], dict]:
        rows = self.db.scalars(select(TripSelection).where(TripSelection.trip_id == self.trip.id)).all()
        return {(r.tier, r.slot): {"choice": r.choice, "product_id": r.product_id,
                                   "wardrobe_item_id": r.wardrobe_item_id} for r in rows}

    def partners(self) -> list[O.RentalPartnerData]:
        rows = self.db.scalars(select(RentalPartner).where(RentalPartner.active.is_(True))).all()
        return [O.RentalPartnerData(id=r.id, slug=r.slug, name=r.name, url_template=r.url_template,
                                    countries=r.countries or [], categories=r.categories or [],
                                    daily_rates=r.daily_rates or {}, min_days=r.min_days,
                                    currency=r.currency, is_placeholder=r.is_placeholder,
                                    network=r.network) for r in rows]

    # ------------------------------------------------------------ outputs
    def _empty(self) -> dict:
        return {"empty": True, "message": "Add at least one stop to see a plan.",
                "model_note": MODEL_NOTE}

    def tiers(self) -> tuple[Computed, dict]:
        c = self.compute()
        cands = self.candidates(c.reqs)
        owned = self.owned(c.reqs)
        sels = self.selections()
        partners = self.partners()
        tiers = {t: O.build_tier(t, c.stages, c.conds, c.reqs, cands, owned, sels, partners,
                                 evenings=self.user.evenings or "sometimes")
                 for t in O.TIERS}
        return c, {"tiers": tiers, "candidates": cands, "owned": owned}

    def plans(self) -> dict:
        if not self.trip.stops:
            return self._empty()
        c, data = self.tiers()
        tiers = data["tiers"]
        for t in tiers.values():
            t.pop("_choices", None)
        tier_advice(tiers)
        return {
            "empty": False,
            "tiers": tiers,
            "comparison": [{"tier": t, "total": tiers[t]["totals"]["total"],
                            "status": tiers[t]["warmth"]["status"]} for t in O.TIERS],
            "requirements": {k: O.requirement_json(r) for k, r in c.reqs.items() if r.needed},
            "questions": clarifying_questions(c.stages),
            "currency": "EUR",
            "model_note": MODEL_NOTE,
            "catalog_note": self._catalog_note(),
        }

    def strategy(self, tier: str = "medium") -> dict:
        if not self.trip.stops:
            return self._empty()
        c, data = self.tiers()
        t = data["tiers"][tier]
        choices = t.pop("_choices")
        kit = O._kit(choices, c.reqs)
        ev = evaluate(c.stages, c.conds, kit)
        for st in ev["stages"]:
            st["upgrades"] = {}
            for mode in ("moving", "rest"):
                if st["modes"][mode]["margin"] < 0:
                    st["upgrades"][mode] = O.cheapest_upgrade(
                        c.stages, c.conds, choices, c.reqs, data["candidates"], st["index"], mode)
                else:
                    st["upgrades"][mode] = None
        ev.pop("dresses", None)
        slots = [{"key": s.key, "code": s.code, "name": s.name, "torso": s.torso}
                 for s in SLOTS if s.key in kit]
        return {
            "empty": False,
            "tier": tier,
            "slots": slots,
            "kit": {k: {"name": v.name, "clo": v.clo, "source": v.source, "ref_id": v.ref_id,
                        "waterproof": v.waterproof, "windproof": v.windproof}
                    for k, v in kit.items()},
            "stages": ev["stages"],
            "margins": ev["margins"],
            "status": ev["status"],
            "requirements": {k: O.requirement_json(r) for k, r in c.reqs.items() if r.needed},
            "questions": clarifying_questions(c.stages),
            "totals": t["totals"],
            "model_note": MODEL_NOTE,
        }

    def slot_products(self, slot: str, q: str | None = None, brand: str | None = None,
                      sort: str = "fit", max_price: float | None = None,
                      only_passing: bool = False) -> dict:
        c = self.compute()
        req = c.reqs.get(slot)
        if req is None:
            return {"items": [], "brands": []}
        items = self.candidates(c.reqs).get(slot, [])
        brands = sorted({i.brand for i in items})
        if q:
            ql = q.lower()
            items = [i for i in items if ql in f"{i.brand} {i.name}".lower()]
        if brand:
            items = [i for i in items if i.brand.lower() == brand.lower()]
        if max_price is not None:
            items = [i for i in items if i.price <= max_price]
        if only_passing:
            items = [i for i in items if i.fit.passes]
        keys = {
            "price_asc": lambda i: (i.price, -i.fit.score),
            "price_desc": lambda i: (-i.price, -i.fit.score),
            "fit": lambda i: (-i.fit.score, i.price),
            "warmth": lambda i: (-float(i.specs.get("clo", 0)), i.price),
            "weight": lambda i: (i.specs.get("weight_g") or 99999, i.price),
            "rating": lambda i: (-(i.rating or 0), -i.review_count),
            "waterproof": lambda i: (-(i.specs.get("waterproof_mm") or 0), i.price),
        }
        items.sort(key=keys.get(sort, keys["fit"]))
        return {"slot": slot, "slot_name": SLOT_BY_KEY[slot].name,
                "requirement": O.requirement_json(req), "brands": brands,
                "items": [i.as_dict() for i in items]}

    def _catalog_note(self) -> str | None:
        seed = self.db.scalar(select(Product.id).where(Product.source == "seed",
                                                       Product.active.is_(True)).limit(1))
        if seed:
            return ("Sample catalog: real product names, indicative prices and approximate "
                    "specs. Check the retailer page before you buy.")
        return None


_RANK = {"covered": 2, "marginal": 1, "cold": 0}


def tier_advice(tiers: dict) -> None:
    """When upgrades push a tier close to the next one's price, say so: paying 90% of
    Premium for a patched Medium kit is a bad deal."""
    for low, high in (("cheap", "medium"), ("medium", "premium")):
        a, b = tiers[low], tiers[high]
        ta, tb = a["totals"]["total"], b["totals"]["total"]
        a["advice"] = None
        if tb <= 0 or ta < 0.85 * tb:
            continue
        if _RANK[b["warmth"]["status"]] < _RANK[a["warmth"]["status"]]:
            continue
        gap = round(tb - ta, 2)
        name = high.capitalize()
        a["advice"] = {"tier": high, "extra_cost": gap,
                       "message": f"With the warmth upgrades this kit costs almost as much as "
                                  f"{name}: {name} is only €{gap:,.0f} more and its pieces are "
                                  f"better. Consider {name}."}
    tiers["premium"]["advice"] = None
