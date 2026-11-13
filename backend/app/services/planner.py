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
    warm_zone,
    zone_key,
    zone_name,
)
from app.config import get_settings
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
    known = w.specs or {}  # data of the model it was matched to, when it was
    if w.waterproof and w.category in ("shell_top", "shell_bottom"):
        # unknown rating: assume an average membrane
        specs["waterproof_mm"] = known.get("waterproof_mm") or 10000
    if known.get("fill_power"):
        specs["fill_power"] = known["fill_power"]
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
                         review_count=p.review_count, network=p.network, gender=p.gender,
                         checked_at=p.checked_at.date().isoformat() if p.checked_at else None)


MARKET_CURRENCY = {"us": "USD", "eu": "EUR"}


def market_of(user: User | None) -> str:
    m = (user.market if user else None) or get_settings().default_market
    return m if m in MARKET_CURRENCY else "us"


@dataclass
class Computed:
    stages: list[StageInput]
    conds: list[Condition]
    reqs: dict[str, SlotRequirement]
    zone: dict | None = None  # hot places and their lighter pieces (strategy.warm_zone)


class Planner:
    def __init__(self, db: Session, user: User, trip: Trip, weather: WeatherService | None = None):
        self.db = db
        self.user = user
        self.trip = trip
        self.weather = weather or WeatherService(db)
        self._computed: Computed | None = None
        self.prefer_names: list[str] = list(user.preferred_brands or [])
        self.prefer = frozenset(b.lower() for b in self.prefer_names)
        self.market = market_of(user)
        self.currency = MARKET_CURRENCY[self.market]
        O.CURRENCY.set(self.currency)

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
            zone = warm_zone(stages, conds, reqs) if conds else None
            self._computed = Computed(stages, conds, reqs, zone)
        return self._computed

    def candidates(self, reqs) -> dict[str, list[O.CatalogItem]]:
        q = select(Product).where(Product.active.is_(True), Product.market == self.market)
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
        # a kit has one currency: rentals priced in another one are left out
        rows = self.db.scalars(select(RentalPartner).where(
            RentalPartner.active.is_(True), RentalPartner.currency == self.currency)).all()
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
                                 evenings=self.user.evenings or "sometimes",
                                 prefer_names=self.prefer_names)
                 for t in O.TIERS}
        if c.zone:
            zc, zo = self.candidates(c.zone["reqs"]), self.owned(c.zone["reqs"])
            for t, tp in tiers.items():
                lines, zch = O.zone_lines(t, c.zone, zc, zo, sels, self.prefer_names,
                                          main_items=tp["items"])
                O.add_zone_lines(tp, lines)
                tp["_zone_choices"] = zch
        return c, {"tiers": tiers, "candidates": cands, "owned": owned}

    def zones(self, c: Computed) -> list[dict]:
        if not c.zone:
            return []
        return [{"key": c.zone["key"], "stages": c.zone["stages"], "names": c.zone["names"],
                 "slots": [zone_key(s) for s in c.zone["slots"]]}]

    def plans(self) -> dict:
        if not self.trip.stops:
            return self._empty()
        c, data = self.tiers()
        tiers = data["tiers"]
        for t in tiers.values():
            self._where(c, t)
            t.pop("_choices", None)
            t.pop("_brand_swaps", None)
            t.pop("_zone_choices", None)
        tier_advice(tiers)
        return {
            "empty": False,
            "tiers": tiers,
            "comparison": [{"tier": t, "total": tiers[t]["totals"]["total"],
                            "status": tiers[t]["warmth"]["status"]} for t in O.TIERS],
            "requirements": {k: O.requirement_json(r) for k, r in c.reqs.items() if r.needed},
            "questions": clarifying_questions(c.stages),
            "zones": self.zones(c),
            "currency": self.currency,
            "model_note": MODEL_NOTE,
            "catalog_note": self._catalog_note(),
        }

    def _zone_kit(self, c: Computed, t: dict) -> dict | None:
        zch = t.get("_zone_choices") or {}
        if not (c.zone and zch):
            return None
        light = {s: ch.kit_item(c.zone["reqs"][s]) for s, ch in zch.items()}
        return {"stages": c.zone["stages"], "kit": {s: k for s, k in light.items() if k}}

    def _where(self, c: Computed, t: dict) -> None:
        """Each piece of the bag says where it is used: one status per stop, in trip
        order (worn / on at stops / in the bag / not needed), and a sentence."""
        kit = O._kit(t["_choices"], c.reqs)
        ev = evaluate(c.stages, c.conds, kit, self._zone_kit(c, t))
        stages = ev["stages"]
        t["stops"] = [{"index": s["index"], "name": s["name"], "start": s["start"],
                       "end": s["end"]} for s in stages]
        for line in t["items"]:
            use = [s["slots"].get(line["slot"], {}).get("status", "none") for s in stages]
            line["where"] = use
            line["where_text"] = where_text(use, [s["name"] for s in stages])

    def strategy(self, tier: str = "medium") -> dict:
        if not self.trip.stops:
            return self._empty()
        c, data = self.tiers()
        t = data["tiers"][tier]
        choices = t.pop("_choices")
        t.pop("_brand_swaps", None)
        zone = self._zone_kit(c, t)
        t.pop("_zone_choices", None)
        kit = O._kit(choices, c.reqs)
        ev = evaluate(c.stages, c.conds, kit, zone)
        for st in ev["stages"]:
            st["upgrades"] = {}
            for mode in ("moving", "rest"):
                if st["modes"][mode]["margin"] < 0:
                    st["upgrades"][mode] = O.cheapest_upgrade(
                        c.stages, c.conds, choices, c.reqs, data["candidates"], st["index"], mode,
                        prefer=self.prefer)
                else:
                    st["upgrades"][mode] = None
        ev.pop("dresses", None)
        light = (zone or {}).get("kit") or {}
        slots = []
        for s in SLOTS:  # a hot-day piece sits right under the piece it stands in for
            if s.key in kit:
                slots.append({"key": s.key, "code": s.code, "name": s.name, "torso": s.torso})
            if s.key in light:
                slots.append({"key": zone_key(s.key), "code": s.code, "zone": c.zone["key"],
                              "name": zone_name(s.key, c.zone["reqs"][s.key]), "torso": s.torso})
        return {
            "empty": False,
            "tier": tier,
            "slots": slots,
            "kit": {k: {"name": v.name, "clo": v.clo, "source": v.source, "ref_id": v.ref_id,
                        "waterproof": v.waterproof, "windproof": v.windproof}
                    for k, v in {**kit, **{zone_key(s): x for s, x in light.items()}}.items()},
            "zones": self.zones(c),
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
        base = slot.split("@")[0]
        if "@" in slot:  # a hot-day piece: rated against the hot places' needs, light only
            zreqs = (c.zone or {}).get("reqs") or {}
            req = zreqs.get(base)
            if req is None:
                return {"items": [], "brands": []}
            items = [i for i in self.candidates(zreqs).get(base, []) if base == "footwear"
                     or float(i.specs.get("clo") or 0) <= 1.5 * REF_CLO[base]["light"]]
        else:
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
            # best fit first, the traveller's brands ahead of equally good ones
            "fit": lambda i: (-round(i.fit.score, 2), i.brand.lower() not in self.prefer, i.price),
            "warmth": lambda i: (-float(i.specs.get("clo", 0)), i.price),
            "weight": lambda i: (i.specs.get("weight_g") or 99999, i.price),
            "rating": lambda i: (-(i.rating or 0), -i.review_count),
            "waterproof": lambda i: (-(i.specs.get("waterproof_mm") or 0), i.price),
        }
        items.sort(key=keys.get(sort, keys["fit"]))
        return {"slot": slot, "slot_name": (zone_name(base, req) if "@" in slot
                                            else SLOT_BY_KEY[slot].name),
                "requirement": O.requirement_json(req), "brands": brands,
                "preferred_brands": self.prefer_names,
                "items": [{**i.as_dict(), "preferred_brand": i.brand.lower() in self.prefer}
                          for i in items]}

    def _catalog_note(self) -> str | None:
        seed = self.db.scalar(select(Product.id).where(Product.source == "seed",
                                                       Product.active.is_(True)).limit(1))
        if seed:
            return ("Real products from real shops: price and stock were read from the shop's "
                    "page on the date shown under each piece (\"indicative price\" = not "
                    "checked yet). Warmth and waterproofing figures are our estimates.")
        return None


_RANK = {"covered": 2, "marginal": 1, "cold": 0}


def _names(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def where_text(use: list[str], names: list[str]) -> str:
    """'On every day of the trip.' / 'On in Cortina and Val Gardena; in the bag the rest
    of the trip.' One sentence a traveller can pack by."""
    if not use:
        return ""
    if all(u == "worn" for u in use):
        return "Worn every day of the trip."
    if all(u == "none" for u in use):
        return "Not needed on this trip."
    if all(u in ("worn", "stops") for u in use) and "stops" in use and "worn" not in use:
        return "On at stops and in the evening, every day of the trip."
    if len(set(use)) == 1 and use[0] == "pack":
        return "In the bag the whole trip, just in case."
    parts = []
    for status, label in (("worn", "worn"), ("stops", "on at stops and in the evening"),
                          ("pack", "in the bag, just in case,")):
        at = [n for n, u in zip(names, use) if u == status]
        if at:
            parts.append(f"{label} in {_names(at)}")
    rest = [n for n, u in zip(names, use) if u == "none"]
    text = "; ".join(parts)
    if rest:
        text += "; not needed in " + _names(rest) if len(rest) <= 2 else "; not needed elsewhere"
    return text[0].upper() + text[1:] + "."


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
                                  f"{name}: {name} is only {O._money(gap)} more and its pieces are "
                                  f"better. Consider {name}."}
    tiers["premium"]["advice"] = None
