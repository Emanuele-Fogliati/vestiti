"""Turn trip requirements into cheap / medium / premium kits.

Rules (product decisions, not tuning):
- Owned items that meet the hard requirements are reused in every tier, at zero cost,
  and the plan says so plainly. Honesty beats basket size.
- Cheap = the cheapest item that passes and has at least 3 stars.
  Medium = best fit in the middle price band. Premium = best fit in the top band.
- If a tier leaves you cold somewhere, the optimizer applies the cheapest upgrade that
  closes the gap (never on slots the user locked by hand) and says what it changed.
- Rental is suggested when an item is needed for half the trip or less and renting
  costs under 70% of buying.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.engine import thermal
from app.engine.fit import FitResult, ItemSpec, score_item
from app.engine.garments import SLOT_BY_KEY, SLOTS, KitItem, reference_item
from app.engine.strategy import (
    Condition,
    SlotRequirement,
    StageInput,
    dress,
    evaluate,
)

TIERS = ["cheap", "medium", "premium"]
UPGRADE_SLOTS = ["insulation_top", "mid_top", "base_top", "base_bottom", "shell_top", "trousers",
                 "headwear", "gloves", "shell_bottom"]


@dataclass
class CatalogItem:
    id: str
    slot: str
    name: str
    brand: str
    price: float
    specs: dict
    source: str = "product"  # product | owned
    merchant: str = ""
    currency: str = "EUR"
    url: str = ""
    image_url: str | None = None
    rating: float | None = None
    review_count: int = 0
    network: str = "direct"
    gender: str = "unisex"
    fit: FitResult | None = None

    def spec(self) -> ItemSpec:
        s = self.specs or {}
        return ItemSpec(
            slot=self.slot, clo=float(s.get("clo", 0.0)),
            waterproof_mm=int(s.get("waterproof_mm") or 0),
            waterproof=bool(s.get("waterproof", False)),
            windproof=bool(s.get("windproof", False)),
            breathability_g=s.get("breathability_g"), weight_g=s.get("weight_g"),
            packable=bool(s.get("packable", False)), insulation=s.get("insulation"),
            footwear_type=s.get("footwear_type"), ankle_support=bool(s.get("ankle_support")),
            insulated=bool(s.get("insulated")), rating=self.rating,
            review_count=self.review_count,
        )

    def kit_item(self) -> KitItem:
        s = self.specs or {}
        return KitItem(
            slot=self.slot, clo=float(s.get("clo", 0.0)), name=f"{self.brand} {self.name}".strip(),
            source=self.source, waterproof=bool(s.get("waterproof")) or int(
                s.get("waterproof_mm") or 0) >= 5000,
            windproof=bool(s.get("windproof")) or int(s.get("waterproof_mm") or 0) >= 5000,
            down=s.get("insulation") == "down", price=self.price if self.source == "product" else 0.0,
            ref_id=self.id, weight_g=s.get("weight_g"), footwear_type=s.get("footwear_type"),
            ankle_support=bool(s.get("ankle_support")), insulated=bool(s.get("insulated")),
        )

    def as_dict(self) -> dict:
        return {
            "id": self.id, "source": self.source, "slot": self.slot, "name": self.name,
            "brand": self.brand, "merchant": self.merchant, "price": round(self.price, 2),
            "currency": self.currency, "image_url": self.image_url, "specs": self.specs,
            "rating": self.rating, "review_count": self.review_count, "network": self.network,
            "gender": self.gender, "fit": self.fit.as_dict() if self.fit else None,
        }


@dataclass
class RentalPartnerData:
    id: str
    slug: str
    name: str
    url_template: str
    countries: list[str]
    categories: list[str]
    daily_rates: dict[str, float]
    min_days: int = 1
    currency: str = "EUR"
    is_placeholder: bool = True
    network: str = "direct"


@dataclass
class Choice:
    slot: str
    kind: str  # product | owned | rent | none
    item: CatalogItem | None = None
    rental: dict | None = None
    locked: bool = False
    note: str | None = None

    def kit_item(self, req: SlotRequirement) -> KitItem | None:
        if self.kind in ("product", "owned") and self.item:
            return self.item.kit_item()
        if self.kind == "rent":
            it = reference_item(self.slot, req.level)
            it.source = "rental"
            it.waterproof = it.waterproof or req.waterproof
            it.name = f"Rental {SLOT_BY_KEY[self.slot].name.lower()}"
            return it
        return None

    def cost(self) -> float:
        if self.kind == "product" and self.item:
            return self.item.price
        if self.kind == "rent" and self.rental:
            return self.rental["price"]
        return 0.0


def rate(reqs: dict[str, SlotRequirement], items: list[CatalogItem]) -> list[CatalogItem]:
    out = []
    for it in items:
        req = reqs.get(it.slot)
        if req is None:
            continue
        it.fit = score_item(req, it.spec())
        out.append(it)
    return out


def pick_for_tier(cands: list[CatalogItem], tier: str) -> CatalogItem | None:
    ok = [c for c in cands if c.fit.passes and c.fit.stars >= 3] or [
        c for c in cands if c.fit.passes] or list(cands)
    if not ok:
        return None
    if tier == "cheap":
        return min(ok, key=lambda c: (c.price, -c.fit.score))
    prices = sorted(c.price for c in ok)
    lo = prices[len(prices) // 3]
    hi = prices[(2 * len(prices)) // 3]
    if tier == "medium":
        band = [c for c in ok if lo <= c.price <= hi] or ok
        mid = prices[len(prices) // 2]
        # a good-enough fit at a middle price, not the best fit at the top of the band:
        # "medium" has to stay a medium budget
        top = max(c.fit.score for c in band)
        good = [c for c in band if c.fit.score >= top - 0.05]
        return min(good, key=lambda c: (abs(c.price - mid), -c.fit.score))
    band = [c for c in ok if c.price >= hi] or ok
    return max(band, key=lambda c: (round(c.fit.score, 2), c.rating or 0, c.price))


def rental_options(req: SlotRequirement, stages: list[StageInput],
                   partners: list[RentalPartnerData]) -> list[dict]:
    countries = {s.country_code for s in stages if s.index in req.stages and s.country_code}
    days_dates = [s for s in stages if s.index in req.stages]
    if not days_dates:
        return []
    start = min(s.start for s in days_dates)
    end = max(s.end for s in days_dates)
    out = []
    for p in partners:
        if req.slot not in p.categories or req.slot not in p.daily_rates:
            continue
        if "*" not in p.countries and not (countries & set(p.countries)):
            continue
        days = max(req.days_needed, p.min_days, 1)
        price = round(p.daily_rates[req.slot] * days, 2)
        out.append({
            "partner_id": p.id, "partner": p.name, "slot": req.slot, "days": days,
            "daily_rate": p.daily_rates[req.slot], "price": price, "currency": p.currency,
            "is_placeholder": p.is_placeholder, "start": start.isoformat(), "end": end.isoformat(),
            "country": sorted(countries)[0] if countries else None,
        })
    return sorted(out, key=lambda r: r["price"])


def _kit(choices: dict[str, Choice], reqs) -> dict[str, KitItem]:
    kit = {}
    for slot, ch in choices.items():
        it = ch.kit_item(reqs[slot])
        if it:
            kit[slot] = it
    return kit


def _worst(stages, conds, kit, stage_index: int, mode: str) -> tuple[Condition, float]:
    sc = [c for c in conds if c.stage_index == stage_index]
    worst, wm = None, None
    for c in sc:
        if c.mode != mode:
            continue
        start = None
        if mode == "rest":
            mv = next((m for m in sc if m.mode == "moving" and m.date == c.date
                       and m.activity.key == c.activity.key), None)
            start = dress(kit, mv).worn if mv else None
        d = dress(kit, c, start)
        if wm is None or d.margin < wm:
            worst, wm = c, d.margin
    return worst, wm if wm is not None else 0.0


def _margin_for(conds, kit, cond: Condition) -> float:
    start = None
    if cond.mode == "rest":
        mv = next((m for m in conds if m.mode == "moving" and m.date == cond.date
                   and m.stage_index == cond.stage_index and m.activity.key == cond.activity.key),
                  None)
        start = dress(kit, mv).worn if mv else None
    return dress(kit, cond, start).margin


def cheapest_upgrade(
    stages, conds, choices: dict[str, Choice], reqs, candidates: dict[str, list[CatalogItem]],
    stage_index: int, mode: str, ceiling: dict[str, float] | None = None,
    max_cost: float | None = None, min_value: float = 0.0,
) -> dict | None:
    """The swap that buys the most warmth per euro for the gap (a fleece before a €400
    shell). When no swap helps any more, the cheapest extra layer the kit does not have
    yet (e.g. rain trousers for a cold boat ride). ceiling caps the price per slot, so a
    budget tier is not quietly turned into the premium one."""
    kit = _kit(choices, reqs)
    cond, margin = _worst(stages, conds, kit, stage_index, mode)
    if cond is None or margin >= 0:
        return None
    best = _best_change(conds, choices, reqs, candidates, kit, cond, margin, False, ceiling, max_cost,
                        min_value) \
        or _best_change(conds, choices, reqs, candidates, kit, cond, margin, True, ceiling, max_cost,
                        min_value)
    if best is None:
        return None
    return {
        "stage_index": stage_index, "mode": mode, "slot": best["slot"],
        "slot_name": SLOT_BY_KEY[best["slot"]].name, "item": best["item"].as_dict(),
        "gain_clo": best["gain"], "extra_cost": best["cost"], "closes": best["closes"],
        "added": best["added"],
        "margin_before": round(margin, 2), "margin_after": best["new_margin"],
        "condition": {"date": cond.date.isoformat(), "where": cond.where,
                      "feels_like_c": cond.feels_like_c},
    }


def _best_change(conds, choices, reqs, candidates, kit, cond, margin, add: bool,
                 ceiling: dict[str, float] | None = None,
                 max_cost: float | None = None, min_value: float = 0.0) -> dict | None:
    best, best_value = None, -1.0
    for slot in UPGRADE_SLOTS:
        if slot not in reqs:
            continue
        if add != (not reqs[slot].needed and slot not in choices):
            continue
        ch = choices.get(slot)
        if ch and ch.locked:
            continue
        current_clo = kit[slot].clo if slot in kit else -1
        current_cost = ch.cost() if ch else 0.0
        for c in candidates.get(slot, []):
            if not c.fit or not c.fit.passes or c.source != "product":
                continue
            if ceiling and c.price > ceiling.get(slot, float("inf")) + 1e-6:
                continue
            if float(c.specs.get("clo", 0)) <= current_clo + 1e-6:
                continue
            trial = dict(kit)
            trial[slot] = c.kit_item()
            new_margin = _margin_for(conds, trial, cond)
            gain = new_margin - margin
            if gain <= 0.005:
                continue
            cost = round(c.price - current_cost, 2)
            if max_cost is not None and cost > max_cost + 1e-6:
                continue
            closes = thermal.warmth_status(new_margin + cond.required, cond.required) != "cold"
            cand = {"slot": slot, "item": c, "gain": round(gain, 2), "cost": cost,
                    "closes": closes, "new_margin": round(new_margin, 2), "added": add}
            # warmth per euro, counting only the part of the gain that the gap needs:
            # overshooting by 0.8 clo is not worth paying for
            value = min(gain, -margin) / (max(cost, 0.0) + 5.0)
            if value < min_value:
                continue
            if value > best_value + 1e-9 or (abs(value - best_value) <= 1e-9 and cost < best["cost"]):
                best, best_value = cand, value
    return best


def build_tier(
    tier: str,
    stages: list[StageInput],
    conds: list[Condition],
    reqs: dict[str, SlotRequirement],
    candidates: dict[str, list[CatalogItem]],
    owned: dict[str, list[CatalogItem]],
    selections: dict[tuple[str, str], dict],
    partners: list[RentalPartnerData],
    max_auto_upgrades: int = 12,
) -> dict:
    choices: dict[str, Choice] = {}
    owned_notes: list[dict] = []
    for slot, req in reqs.items():
        if not req.needed:
            continue
        sel = selections.get((tier, slot))
        cands = candidates.get(slot, [])
        mine = sorted(owned.get(slot, []), key=lambda c: -c.fit.score)
        best_owned = next((o for o in mine if o.fit.passes), None)
        if sel:
            kind = sel["choice"]
            if kind == "product":
                item = next((c for c in cands if c.id == sel.get("product_id")), None)
                if item:
                    choices[slot] = Choice(slot, "product", item, locked=True)
                    continue
            elif kind == "owned":
                item = next((o for o in mine if o.id == sel.get("wardrobe_item_id")), None)
                if item:
                    choices[slot] = Choice(slot, "owned", item, locked=True)
                    continue
            elif kind == "rent":
                opts = rental_options(req, stages, partners)
                if opts:
                    choices[slot] = Choice(slot, "rent", rental=opts[0], locked=True)
                    continue
            elif kind == "skip":
                choices[slot] = Choice(slot, "none", locked=True,
                                       note="You chose to skip this item.")
                continue
        if best_owned:
            choices[slot] = Choice(slot, "owned", best_owned)
            continue
        if mine:
            owned_notes.append({"slot": slot, "item": mine[0].as_dict(),
                                "verdict": "not_suitable",
                                "message": f"Your {mine[0].name} won't do here: "
                                           + "; ".join(mine[0].fit.issues) + "."})
        pick = pick_for_tier(cands, tier)
        choices[slot] = Choice(slot, "product", pick) if pick else Choice(
            slot, "none", note="No product in the catalog fits this yet.")

    # warmth optimisation: best warmth per euro until no stage is "cold", never above the
    # next tier's pick for that piece
    nxt = {"cheap": "medium", "medium": "premium"}.get(tier)
    ceiling = None
    if nxt:
        ceiling = {}
        for slot, cs in candidates.items():
            top = pick_for_tier(cs, nxt)
            if top:
                ceiling[slot] = top.price
    steps = []
    original = {k: (c.item.as_dict() if c.item else None, c.cost()) for k, c in choices.items()}
    # an evening outside in town is partly the traveller's choice: spend a little on it,
    # not €250 (the rest is explained in the shortfall)
    evening_budget = round(AVOIDABLE_BUDGET * sum(c.cost() for c in choices.values()), 2)
    done: set[tuple[int, str]] = set()
    for _ in range(max_auto_upgrades + 2 * len(stages)):
        if len(steps) >= max_auto_upgrades:
            break
        kit_now = _kit(choices, reqs)
        ev = evaluate(stages, conds, kit_now)
        cold = sorted((s["modes"][m]["margin"], s["index"], m) for s in ev["stages"]
                      for m in ("moving", "rest")
                      if s["modes"][m]["status"] == "cold" and (s["index"], m) not in done)
        if not cold:
            break
        _, si, mode = cold[0]
        soft = avoidable(_worst(stages, conds, kit_now, si, mode)[0])
        up = cheapest_upgrade(stages, conds, choices, reqs, candidates, si, mode, ceiling,
                              max_cost=evening_budget if soft else None,
                              min_value=AVOIDABLE_MIN_VALUE if soft else 0.0)
        if not up:
            done.add((si, mode))
            continue
        if soft:
            evening_budget -= max(up["extra_cost"], 0.0)
        slot = up["slot"]
        new_item = next(c for c in candidates[slot] if c.id == up["item"]["id"])
        steps.append({**up, "stage_name": stages_name(stages, si)})
        choices[slot] = Choice(slot, "product", new_item,
                               note="added for warmth" if up["added"] else "auto-upgraded for warmth")
    auto = _merge_upgrades(steps, original, choices, tier)

    kit = _kit(choices, reqs)
    ev = evaluate(stages, conds, kit)
    items = []
    buy = rent = owned_value = 0.0
    weight = 0.0
    for s in SLOTS:
        slot = s.key
        if slot not in choices:
            continue
        ch = choices[slot]
        req = reqs[slot]
        rentals = rental_options(req, stages, partners)
        tier_pick = pick_for_tier(candidates.get(slot, []), tier) if candidates.get(slot) else None
        rent_suggestion = None
        if rentals and ch.kind == "product" and ch.item:
            r0 = rentals[0]
            if req.trip_days and req.days_needed / req.trip_days <= 0.5 and \
                    r0["price"] < 0.7 * ch.item.price:
                rent_suggestion = {**r0, "saving": round(ch.item.price - r0["price"], 2)}
        if ch.kind == "product" and ch.item:
            buy += ch.item.price
        elif ch.kind == "rent" and ch.rental:
            rent += ch.rental["price"]
        elif ch.kind == "owned" and tier_pick:
            owned_value += tier_pick.price
        kit_item = kit.get(slot)
        if kit_item and kit_item.weight_g:
            weight += kit_item.weight_g
        verdict = None
        if ch.kind == "owned" and ch.item:
            stars = ch.item.fit.stars
            verdict = ("fine" if stars >= 3 else "works")
            owned_notes.append({
                "slot": slot, "item": ch.item.as_dict(), "verdict": verdict,
                "message": (f"Your {ch.item.name} is fine for this trip ({stars:g}★). "
                            "No need to buy one.") if verdict == "fine" else
                           (f"Your {ch.item.name} works ({stars:g}★) but is not ideal: "
                            + "; ".join(ch.item.fit.issues) + ".")})
        items.append({
            "slot": slot, "code": s.code, "slot_name": s.name, "kind": ch.kind,
            "locked": ch.locked, "note": ch.note,
            "item": ch.item.as_dict() if ch.item else None, "rental": ch.rental,
            "rent_suggestion": rent_suggestion, "rental_options": rentals[:3],
            "alternatives": len(candidates.get(slot, [])),
            "owned_alternatives": [o.as_dict() for o in owned.get(slot, [])],
            "requirement": requirement_json(req),
            "cost": round(ch.cost(), 2), "owned_verdict": verdict,
        })
    owned_fine = len([n for n in owned_notes if n["verdict"] == "fine"])
    return {
        "tier": tier,
        "items": items,
        "totals": {"buy": round(buy, 2), "rent": round(rent, 2), "total": round(buy + rent, 2),
                   "owned_value_saved": round(owned_value, 2),
                   "items_to_buy": sum(1 for i in items if i["kind"] == "product"),
                   "items_owned": sum(1 for i in items if i["kind"] == "owned"),
                   "items_rented": sum(1 for i in items if i["kind"] == "rent"),
                   "weight_g": round(weight)},
        "warmth": {"status": ev["status"], "margins": ev["margins"],
                   "stages": [{"index": s["index"], "name": s["name"],
                               "moving": {k: s["modes"]["moving"][k] for k in ("required", "provided", "margin", "status")},
                               "rest": {k: s["modes"]["rest"][k] for k in ("required", "provided", "margin", "status")}}
                              for s in ev["stages"]]},
        "auto_upgrades": auto,
        "shortfall": shortfall(stages, conds, kit, ev, tier),
        "owned_notes": owned_notes,
        "owned_fine_count": owned_fine,
        "_choices": choices,
    }


def _merge_upgrades(steps: list[dict], original: dict, choices: dict[str, Choice], tier: str) -> list[dict]:
    """One line per slot: the tier's first pick, the item the kit ends with, the net cost.
    A slot can be upgraded several times while the gap moves between stops."""
    out: dict[str, dict] = {}
    for st in steps:
        slot = st["slot"]
        line = out.setdefault(slot, {"slot": slot, "from": original.get(slot, (None, 0.0))[0],
                                     "gain_clo": 0.0, "steps": 0, "worst": st})
        line["gain_clo"] = round(line["gain_clo"] + st["gain_clo"], 2)
        line["steps"] += 1
        if st["margin_before"] < line["worst"]["margin_before"]:
            line["worst"] = st
    result = []
    for slot, line in out.items():
        ch = choices[slot]
        before = original.get(slot, (None, 0.0))[1]
        net = round(ch.cost() - before, 2)
        w = line.pop("worst")
        added = line["from"] is None
        what = (f"added a {SLOT_BY_KEY[slot].name.lower()}" if added else
                f"swapped the {tier} pick for a warmer"
                + (" and cheaper" if net < 0 else "") + " one")
        line.update({
            "to": ch.item.as_dict() if ch.item else None, "extra_cost": net, "added": added,
            "reason": f"{SLOT_BY_KEY[slot].name}: {what}. Without it you were "
                      f"{-w['margin_before']:.2f} clo short at {w['stage_name']} "
                      f"({'moving' if w['mode'] == 'moving' else 'at rest'}, "
                      f"{w['condition']['feels_like_c']:.0f} °C feels-like). "
                      + ("Costs " + _money(net) if net > 0 else
                         "Saves " + _money(-net) if net < 0 else "Same price") + ".",
        })
        result.append(line)
    return result


AVOIDABLE_REST = {"city", "beach", "boat", "desert"}
AVOIDABLE_BUDGET = 0.15  # share of the tier's cost that may go to town evenings
AVOIDABLE_MIN_VALUE = 0.0004  # clo per euro: 0.1 clo for €250 is the least worth paying


def avoidable(cond: Condition | None) -> bool:
    """A cold moment the traveller can simply walk away from (an evening outdoors in town),
    unlike a summit break, a camp night or an early game drive."""
    return bool(cond and cond.mode == "rest" and cond.activity.key in AVOIDABLE_REST
                and cond.where == "evening outdoors")


def shortfall(stages, conds, kit, ev, tier: str) -> dict | None:
    """When even the upgrades leave a stop cold: where, how much, and what would close it."""
    cold = sorted((s["modes"][m]["margin"], s["index"], m) for s in ev["stages"]
                  for m in ("moving", "rest") if s["modes"][m]["status"] == "cold")
    if not cold:
        return None
    rows = [(m, si, mode, _worst(stages, conds, kit, si, mode)[0]) for m, si, mode in cold]
    hard = [r for r in rows if not avoidable(r[3])]
    margin, si, mode, cond = (hard or rows)[0]
    name = stages_name(stages, si)
    gap = -margin
    feels = cond.feels_like_c if cond else None
    if not hard:
        return {
            "stage_index": si, "stage": name, "mode": mode, "gap_clo": round(gap, 2),
            "feels_like_c": feels, "missing": [], "avoidable": True,
            "message": f"Only if you stay outside in the evening at {name}"
                       + (f" (feels like {feels:.0f} °C)" if feels is not None else "")
                       + f": {gap:.2f} clo short standing still. Head indoors, keep walking or "
                       "add a layer you already own; closing it fully would mean a much pricier "
                       "jacket for a few evenings.",
        }
    when = "at rest" if mode == "rest" else "on the move"
    missing = [SLOT_BY_KEY[k].name.lower() for k in ("insulation_top", "mid_top", "base_bottom",
                                                      "shell_bottom", "headwear", "gloves")
               if k not in kit]
    tips = []
    if missing:
        tips.append("add " + " and ".join(missing[:2]))
    if mode == "rest":
        tips.append("keep the down jacket for the stops, and sit out of the wind or indoors"
                    if "insulation_top" in kit else "bring an insulated jacket for the stops")
    if tier != "premium":
        tips.append("the premium tier has warmer pieces")
    feels_txt = f", feels like {feels:.0f} °C" if feels is not None else ""
    return {
        "stage_index": si, "stage": name, "mode": mode, "gap_clo": round(gap, 2),
        "feels_like_c": feels, "missing": missing, "avoidable": False,
        "message": f"Still {gap:.2f} clo short at {name} {when}{feels_txt}: the catalog has no "
                   f"warmer swap that fits this tier. To close it: " + "; ".join(tips) + ".",
    }


def requirement_json(r: SlotRequirement) -> dict:
    return {
        "slot": r.slot, "code": r.code, "name": r.name, "needed": r.needed, "level": r.level,
        "ref_clo": r.ref_clo, "waterproof": r.waterproof,
        "waterproof_grade_mm": r.waterproof_grade_mm, "windproof": r.windproof,
        "footwear_type": r.footwear_type, "ankle_support": r.ankle_support,
        "insulated": r.insulated, "breathable_high": r.breathable_high, "packable": r.packable,
        "reasons": r.reasons, "stages": r.stages, "days_needed": r.days_needed,
        "trip_days": r.trip_days,
    }


def stages_name(stages, idx: int) -> str:
    return next((s.name for s in stages if s.index == idx), f"stage {idx + 1}")


def _money(v: float) -> str:
    return f"€{abs(v):,.0f}"


def group_by_slot(items: list[CatalogItem]) -> dict[str, list[CatalogItem]]:
    out: dict[str, list[CatalogItem]] = {}
    for it in items:
        out.setdefault(it.slot, []).append(it)
    return out


def trip_days(stages: list[StageInput]) -> set[date]:
    return {d.date for s in stages for d in s.days}
