"""Traveller profile: the quiz, the chat updates and the "what changed in the plan" diff.

The plan stays deterministic. What the traveller tells us (quiz taps or chat sentences)
becomes a few structured settings the engine already understands:

- cold      -> User.thermal_offset (clo added to every requirement)
- pace      -> User.pace (heat made on the move)
- evenings  -> User.evenings (how much to spend on cold town evenings)
- owned     -> WardrobeItem rows (rated against the spec like any owned piece)

No model ever picks a product here. The chat's model only fills the same fields the quiz
does, and a rule-based reader does the same when the model is offline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.garments import FOOTWEAR_TYPES, LEVELS, SLOT_BY_KEY, SLOT_KEYS
from app.models import User, WardrobeItem

COLD_OFFSET = {"very_cold": 0.3, "bit_cold": 0.15, "average": 0.0, "warm": -0.3}
COLD_LABEL = {"very_cold": "always cold", "bit_cold": "a bit cold", "average": "average",
              "warm": "rarely cold"}
PACE_LABEL = {"relaxed": "relaxed, many stops", "average": "average", "brisk": "brisk"}
EVENING_LABEL = {"early": "back inside early", "sometimes": "out some evenings",
                 "late": "out late most evenings"}

QUIZ_NOTE = "Added from the quiz"
CHAT_NOTE = "Added from the chat"

# The quiz's "what do you already have?" chips. Each becomes a plain, average garment:
# the engine rates it honestly and says so when it is not warm enough for the trip.
BASICS: dict[str, dict] = {
    "fleece": {"label": "Fleece", "category": "mid_top", "name": "Fleece",
               "warmth": "medium", "material": "fleece"},
    "rain_jacket": {"label": "Rain jacket", "category": "shell_top", "name": "Rain jacket",
                    "warmth": "medium", "waterproof": True, "windproof": True},
    "puffy": {"label": "Puffy jacket", "category": "insulation_top", "name": "Puffy jacket",
              "warmth": "medium", "material": "synthetic"},
    "thermal_top": {"label": "Thermal top", "category": "base_top", "name": "Thermal top",
                    "warmth": "medium", "material": "synthetic"},
    "hiking_trousers": {"label": "Hiking trousers", "category": "trousers",
                        "name": "Hiking trousers", "warmth": "medium", "material": "synthetic"},
    "hiking_boots": {"label": "Hiking boots", "category": "footwear", "name": "Hiking boots",
                     "warmth": "medium", "waterproof": True, "footwear_type": "hiking_boot",
                     "ankle_support": True},
}
BASIC_BY_CATEGORY = {b["category"]: k for k, b in BASICS.items()}


def cold_key(offset: float | None) -> str:
    v = offset or 0.0
    return min(COLD_OFFSET, key=lambda k: abs(COLD_OFFSET[k] - v))


def profile_json(db: Session, user: User) -> dict:
    cats = {w.category for w in user_wardrobe(db, user)}
    return {
        "cold": cold_key(user.thermal_offset), "thermal_offset": user.thermal_offset or 0.0,
        "pace": user.pace or "average", "evenings": user.evenings or "sometimes",
        "owned": [k for k, b in BASICS.items() if b["category"] in cats],
        "done": user.profile_done_at is not None,
        "basics": [{"key": k, "label": b["label"]} for k, b in BASICS.items()],
    }


def user_wardrobe(db: Session, user: User) -> list[WardrobeItem]:
    return list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id == user.id)).all())


# ---------------------------------------------------------------- updates

@dataclass
class OwnedPiece:
    category: str
    name: str
    brand: str | None = None
    warmth: str = "medium"
    waterproof: bool = False
    windproof: bool = False
    material: str | None = None
    footwear_type: str | None = None
    ankle_support: bool = False

    def clean(self) -> "OwnedPiece | None":
        if self.category not in SLOT_KEYS:
            return None
        self.name = (self.name or SLOT_BY_KEY[self.category].name).strip()[:120] or \
            SLOT_BY_KEY[self.category].name
        self.brand = (self.brand or "").strip()[:120] or None
        if self.warmth not in LEVELS:
            self.warmth = "medium"
        if self.material not in (None, "merino", "synthetic", "fleece", "down", "cotton", "other"):
            self.material = None
        if self.category == "footwear":
            if self.footwear_type not in FOOTWEAR_TYPES:
                self.footwear_type = "sneaker"
            if self.footwear_type in ("hiking_boot", "mountaineering_boot"):
                self.ankle_support = True
        else:
            self.footwear_type = None
            self.ankle_support = False
        if self.category in ("shell_top", "shell_bottom") and self.waterproof:
            self.windproof = True
        return self


@dataclass
class Updates:
    cold: str | None = None
    pace: str | None = None
    evenings: str | None = None
    owned: list[OwnedPiece] = field(default_factory=list)
    question: bool = False

    def empty(self) -> bool:
        return not (self.cold or self.pace or self.evenings or self.owned)

    def merge(self, other: "Updates") -> "Updates":
        """self wins on every field it sets; other fills the gaps."""
        cats = {o.category for o in self.owned}
        return Updates(cold=self.cold or other.cold, pace=self.pace or other.pace,
                       evenings=self.evenings or other.evenings,
                       owned=self.owned + [o for o in other.owned if o.category not in cats],
                       question=self.question or other.question)


def _snapshot_profile(user: User) -> dict:
    return {"thermal_offset": user.thermal_offset or 0.0, "pace": user.pace or "average",
            "evenings": user.evenings or "sometimes"}


def apply_updates(db: Session, user: User, up: Updates, note: str = CHAT_NOTE) -> tuple[list[str], dict]:
    """Write the updates. Returns (what changed, in plain sentences; undo data)."""
    undo = {"profile": _snapshot_profile(user), "wardrobe_ids": []}
    changes: list[str] = []
    if up.cold and abs(COLD_OFFSET[up.cold] - (user.thermal_offset or 0.0)) > 1e-6:
        before = cold_key(user.thermal_offset)
        user.thermal_offset = COLD_OFFSET[up.cold]
        sign = "+" if user.thermal_offset > 0 else ""
        changes.append(f"Feel the cold: {COLD_LABEL[before]} → {COLD_LABEL[up.cold]} "
                       f"({sign}{user.thermal_offset:.2f} clo on every warmth target)")
    if up.pace and up.pace != (user.pace or "average"):
        changes.append(f"Pace: {PACE_LABEL[user.pace or 'average']} → {PACE_LABEL[up.pace]}")
        user.pace = up.pace
    if up.evenings and up.evenings != (user.evenings or "sometimes"):
        changes.append(f"Evenings: {EVENING_LABEL[user.evenings or 'sometimes']} → "
                       f"{EVENING_LABEL[up.evenings]}")
        user.evenings = up.evenings
    existing = user_wardrobe(db, user)
    for piece in up.owned:
        p = piece.clean()
        if p is None:
            continue
        same = next((w for w in existing if w.category == p.category
                     and w.name.lower() == p.name.lower()), None)
        if same:
            continue
        w = WardrobeItem(user_id=user.id, category=p.category, name=p.name, brand=p.brand,
                         warmth=p.warmth, waterproof=p.waterproof, windproof=p.windproof,
                         material=p.material, footwear_type=p.footwear_type,
                         ankle_support=p.ankle_support, notes=note)
        db.add(w)
        db.flush()
        existing.append(w)
        undo["wardrobe_ids"].append(w.id)
        changes.append(f"Added to your wardrobe: {p.name} ({SLOT_BY_KEY[p.category].name.lower()})")
    return changes, undo


def apply_quiz(db: Session, user: User, cold: str | None, pace: str | None,
               evenings: str | None, owned: list[str] | None) -> tuple[list[str], dict]:
    up = Updates(cold=cold, pace=pace, evenings=evenings)
    removed: list[str] = []
    if owned is not None:
        keys = [k for k in owned if k in BASICS]
        have = {w.category for w in user_wardrobe(db, user)}
        for k in keys:
            b = BASICS[k]
            if b["category"] in have:
                continue  # they already told us about a piece of this kind: keep theirs
            up.owned.append(OwnedPiece(**{f: v for f, v in b.items() if f != "label"}))
        # unticked chips remove only the generic pieces an earlier quiz added
        for w in user_wardrobe(db, user):
            k = BASIC_BY_CATEGORY.get(w.category)
            if k and k not in keys and w.notes == QUIZ_NOTE:
                removed.append(f"Removed from your wardrobe: {w.name}")
                db.delete(w)
    changes, undo = apply_updates(db, user, up, note=QUIZ_NOTE)
    user.profile_done_at = datetime.now(timezone.utc)
    return changes + removed, undo


# ---------------------------------------------------------------- rule-based reader

_WARM = re.compile(
    r"non (patisco|soffro|sento|soffro) (tanto |molto |troppo |particolarmente |mai )?(il )?freddo"
    r"|non sono (un |una )?freddol(?:os|on)|runs? (hot|warm)|rarely (get |feel )?cold|never (get |feel )?cold"
    r"|(don'?t|do not) (really )?(feel|get|mind) (the )?cold|caloros|ho sempre caldo"
    r"|(i'?m|i am) always (hot|warm)|sento poco il freddo|resisto bene al freddo", re.I)
_BIT_COLD = re.compile(
    r"(a bit|a little|slightly|somewhat|un po'?|un pochino|abbastanza) (of a )?(cold|chilly|freddol(?:os|on))"
    r"|patisco un po'?|soffro un po'?", re.I)
_VERY_COLD = re.compile(
    r"freddol(?:os|on)|always (cold|freezing)|runs? cold|feel the cold|get cold (easily|fast|quickly)"
    r"|patisco (molto |tanto |parecchio )?(il )?freddo|soffro (molto |tanto |parecchio )?(il )?freddo"
    r"|ho sempre freddo|sempre freddo|cold person|hate the cold|odio il freddo", re.I)
_BRISK = re.compile(
    r"cammino (veloce|svelto|forte|tanto)|walk (fast|quickly|briskly)|fast (walker|hiker|pace)|brisk"
    r"|passo (veloce|svelto)|(molto )?allenat|very fit|in good shape|in forma", re.I)
_RELAXED = re.compile(
    r"cammino (piano|lent)|walk slow|slow (walker|hiker|pace)|take it easy|lots of (photo )?stops"
    r"|tante (soste|pause|foto)|passo (lento|tranquillo)|non sono (molto )?allenat|not (very )?fit"
    r"|fuori forma|out of shape", re.I)
_LATE = re.compile(
    r"esco (la sera|di sera|spesso)|stay out late|night ?life|aperitiv|evenings? out|out at night"
    r"|stargaz|guardare le stelle|fuori la sera|vita notturna|cena fuori|dinner outside|fino a tardi"
    r"|la sera (sono|sto) fuori|out in the evening", re.I)
_EARLY = re.compile(
    r"(rientro|torno) (presto|in hotel|in albergo)|in (hotel|albergo) (la sera|presto)|early to bed"
    r"|go to bed early|back (at|to) the hotel|stay in at night|la sera (sto|resto) (in hotel|dentro|in albergo)"
    r"|a letto presto|non esco (mai )?la sera|don'?t go out (at night|in the evening)", re.I)
_NEG_OWN = re.compile(r"\b(don'?t|do not|doesn'?t) (have|own)|haven'?t got|\bnon (ho|possiedo|ce l'ho)"
                      r"|\bno (fleece|jacket|boots)|\bniente\b|\bnessun", re.I)
_OWN = re.compile(r"\b(i have|i'?ve got|i own|i already have|i'?ll bring|bring my|i got|got an?|my|mine"
                  r"|ho|ho già|già ho|possiedo|ce l'ho|ho un|ho una|mi porto|porto (il|la|i|le|lo) mi"
                  r"|il mio|la mia|i miei|le mie)\b", re.I)
_QUESTION = re.compile(r"\?|^\s*(should|do|does|did|is|are|what|why|how|can|could|will|which|when"
                       r"|devo|serve|servono|perch[eé]|come|quale|quali|cosa|posso|conviene|meglio)\b", re.I)

# keyword -> (category, english name, defaults)
_ITEMS: list[tuple[re.Pattern, str, str, dict]] = [
    (re.compile(r"\b(piumino|piumin[oi]|down jacket|nuptse|down parka)\b", re.I), "insulation_top",
     "down jacket", {"material": "down", "warmth": "warm"}),
    (re.compile(r"\b(puffy|puffer|thermoball|giacca imbottita|insulated jacket|parka)\b", re.I),
     "insulation_top", "puffy jacket", {"material": "synthetic"}),
    (re.compile(r"\b(k-?way|rain ?jacket|raincoat|giacca (anti ?pioggia|impermeabile)|guscio|hard ?shell"
                r"|shell jacket|waterproof jacket|gore-?tex jacket|giacca in gore-?tex|giubbotto impermeabile)\b", re.I),
     "shell_top", "rain jacket", {"waterproof": True, "windproof": True}),
    (re.compile(r"\b(windbreaker|wind ?jacket|antivento|softshell|soft shell)\b", re.I), "shell_top",
     "windproof jacket", {"windproof": True, "warmth": "light"}),
    (re.compile(r"\b(pile|fleece|felpa in pile|micropile)\b", re.I), "mid_top", "fleece",
     {"material": "fleece"}),
    (re.compile(r"\b(pantaloni (impermeabili|antipioggia)|rain ?(pants|trousers)|over ?(pants|trousers)"
                r"|sovrapantaloni|waterproof (pants|trousers))\b", re.I), "shell_bottom", "rain trousers",
     {"waterproof": True, "windproof": True}),
    (re.compile(r"\b(pantaloni da (trekking|montagna|escursionismo)|hiking (pants|trousers)"
                r"|trekking (pants|trousers)|zip-?off)\b", re.I), "trousers", "hiking trousers",
     {"material": "synthetic"}),
    (re.compile(r"\b(leggings? termic\w*|calzamaglia|thermal (leggings|tights|bottoms)|long johns"
                r"|pantaloni termici)\b", re.I), "base_bottom", "thermal leggings", {"material": "synthetic"}),
    (re.compile(r"\b(maglia termica|maglietta termica|thermal (top|shirt)|base ?layer|merino (top|t-?shirt|shirt)"
                r"|intimo termico|sottomaglia|maglia in merino|termica)\b", re.I), "base_top", "thermal top",
     {"material": "synthetic"}),
    (re.compile(r"\b(scarponi\w*|hiking boots?|trekking boots?|mountain boots?|boots|stivali)\b", re.I),
     "footwear", "hiking boots", {"footwear_type": "hiking_boot", "ankle_support": True,
                                  "waterproof": True}),
    (re.compile(r"\b(scarpe da (trekking|trail|montagna)|trail ?runn\w*|trail shoes|hiking shoes"
                r"|approach shoes|scarpe da escursionismo)\b", re.I), "footwear", "hiking shoes",
     {"footwear_type": "trail_runner"}),
    (re.compile(r"\b(sneakers?|scarpe da ginnastica|running shoes|scarpe da corsa)\b", re.I), "footwear",
     "sneakers", {"footwear_type": "sneaker"}),
    (re.compile(r"\b(guanti|gloves|mittens|muffole)\b", re.I), "gloves", "gloves", {}),
    (re.compile(r"\b(berretto|cuffia|beanie|cappello di lana|wool hat|woolly hat)\b", re.I), "headwear",
     "beanie", {}),
    (re.compile(r"\b(cappello da sole|cappello con (la )?tesa|sun ?hat|bucket hat)\b", re.I), "sun_hat",
     "sun hat", {}),
]
_BRANDS = ["Decathlon", "Quechua", "Forclaz", "Simond", "Wedze", "Kalenji", "The North Face",
           "North Face", "Patagonia", "Columbia", "Arc'teryx", "Arcteryx", "Salomon", "Uniqlo", "Mammut",
           "Salewa", "La Sportiva", "Scarpa", "Merrell", "Montura", "Napapijri", "Jack Wolfskin",
           "Mountain Warehouse", "Rab", "Helly Hansen", "Icebreaker", "Smartwool", "Zara", "H&M",
           "Moncler", "Colmar", "CMP", "Karpos", "Millet", "Lowa", "Meindl", "Asolo", "Timberland",
           "Nike", "Adidas", "Ferrino", "Dolomite", "Garmont", "Vaude", "Fjallraven", "Fjällräven",
           "Haglofs", "Ortovox", "Dynafit", "Kathmandu", "Regatta", "Trespass", "Craghoppers"]
_BRAND_RE = re.compile(r"\b(" + "|".join(re.escape(b) for b in sorted(_BRANDS, key=len, reverse=True))
                       + r")\b", re.I)
_LIGHT = re.compile(r"\b(legger\w*|light(weight)?|thin|sottile|fin[eo])\b", re.I)
_HEAVY = re.compile(r"\b(pesant\w*|heavy|thick|spess\w*|cald[oa]|warm)\b", re.I)
_OLD = re.compile(r"\b(old|vecchi\w*|usat\w*|worn)\b", re.I)


def _canon_brand(b: str) -> str:
    return next((x for x in _BRANDS if x.lower() == b.lower()), b)


def read_rules(text: str) -> Updates:
    up = Updates()
    t = " " + text.strip() + " "
    if _WARM.search(t):
        up.cold = "warm"
    elif _BIT_COLD.search(t):
        up.cold = "bit_cold"
    elif _VERY_COLD.search(t):
        up.cold = "very_cold"
    if _RELAXED.search(t):
        up.pace = "relaxed"
    elif _BRISK.search(t):
        up.pace = "brisk"
    if _EARLY.search(t):
        up.evenings = "early"
    elif _LATE.search(t):
        up.evenings = "late"
    seen: set[str] = set()
    for clause in re.split(r"[.;!\n]|,\s*(?=(?:ma|but|e non|and no)\b)", text):
        if not clause.strip() or _NEG_OWN.search(clause) or not _OWN.search(clause):
            continue
        if "?" in clause and not re.search(r"\b(i have|ho)\b", clause, re.I):
            continue  # "should I bring my fleece?" is a question, not news
        for rx, cat, label, defaults in _ITEMS:
            m = rx.search(clause)
            if not m or cat in seen:
                continue
            seen.add(cat)
            lo, hi = max(m.start() - 30, 0), min(m.end() + 30, len(clause))
            near = clause[lo:hi]
            bm = _BRAND_RE.search(near)
            brand = _canon_brand(bm.group(1)) if bm else None
            warmth = defaults.get("warmth", "medium")
            if _LIGHT.search(near):
                warmth = "light"
            elif _HEAVY.search(near) and warmth == "medium":
                warmth = "warm"
            name = label
            if brand:
                name = f"{brand} {name}"
            if _OLD.search(near):
                name = f"old {name}"
            piece = OwnedPiece(category=cat, name=name[:1].upper() + name[1:], brand=brand,
                               warmth=warmth, **{k: v for k, v in defaults.items() if k != "warmth"})
            up.owned.append(piece)
    up.question = bool(_QUESTION.search(text))
    return up


# ---------------------------------------------------------------- plan diff

def plan_snapshot(plans: dict) -> dict | None:
    if not plans or plans.get("empty"):
        return None
    out = {}
    for tier, t in plans["tiers"].items():
        items = {}
        for it in t["items"]:
            item = it.get("item") or {}
            items[it["slot"]] = {"kind": it["kind"], "slot_name": it["slot_name"],
                                 "id": item.get("id"), "note": it.get("note"),
                                 "name": " ".join(x for x in (item.get("brand"), item.get("name")) if x)
                                 or None, "cost": it["cost"]}
        status = t["warmth"]["status"]
        if status == "cold" and (t.get("shortfall") or {}).get("avoidable"):
            status = "evenings"  # only an evening outside in town is left cold
        out[tier] = {"total": t["totals"]["total"], "status": status, "items": items,
                     "owned_notes": {n["item"]["id"]: n for n in t.get("owned_notes", [])}}
    return out


def _piece(p: dict | None) -> str:
    if not p:
        return "nothing"
    if p["kind"] == "owned":
        return f"yours ({p['name']})" if p["name"] else "yours"
    if p["kind"] == "have":
        return "yours"
    if p["kind"] == "rent":
        return f"rent (€{p['cost']:,.0f})"
    if p["kind"] == "none":
        return "nothing"
    return f"{p['name']} (€{p['cost']:,.0f})"


STATUS_LABEL = {"covered": "warm enough everywhere", "marginal": "borderline somewhere",
                "evenings": "warm enough, except evenings you choose to stay outside",
                "cold": "too cold somewhere"}


def _owned_use(after: dict, wardrobe: list[WardrobeItem], tier: str) -> list[str]:
    """For each piece the traveller just told us about: is it in this tier's kit, and if
    not, why. Silence here would look like the app ignored them."""
    a = after[tier]
    out = []
    name = tier.capitalize()
    for w in wardrobe:
        line = a["items"].get(w.category)
        if line and line["kind"] == "owned" and line["id"] == w.id:
            verb = "are" if w.name.lower().endswith("s") else "is"
            out.append(f"Your {w.name} {verb} in the {name} kit, so you don't buy one.")
            continue
        note = a["owned_notes"].get(w.id)
        if note and note.get("verdict") == "not_suitable":
            out.append(note["message"])
        elif line and line["kind"] == "owned":
            out.append(f"Your {line['name']} fits better than your {w.name}, so the kit uses that.")
        elif line and line["kind"] == "product" and line.get("note") in ("auto-upgraded for warmth", "added for warmth"):
            out.append(f"Your {w.name} works, but the {name} kit swaps it for a warmer one "
                       f"({line['name']}, €{line['cost']:,.0f}) to cover the coldest stop. "
                       "Keep yours if you'd rather not spend that.")
        elif line and line["kind"] == "product":
            out.append(f"Your {w.name} isn't used in the {name} kit: you chose to buy this piece.")
        elif w.category not in a["items"]:
            out.append(f"This trip doesn't need a {SLOT_BY_KEY[w.category].name.lower()}, so your "
                       f"{w.name} can stay home.")
    return out


def plan_diff(before: dict | None, after: dict | None, tier: str,
              new_owned: list[WardrobeItem] | None = None) -> dict:
    if not before or not after:
        return {"tier": tier, "pieces": [], "totals": [], "status": None, "owned": []}
    b, a = before[tier], after[tier]
    pieces = []
    for slot in [s for s in SLOT_KEYS if s in b["items"] or s in a["items"]]:
        pb, pa = b["items"].get(slot), a["items"].get(slot)
        if (pb or {}).get("kind") == (pa or {}).get("kind") and (pb or {}).get("name") == (pa or {}).get("name") \
                and abs((pb or {}).get("cost", 0) - (pa or {}).get("cost", 0)) < 0.01:
            continue
        name = (pa or pb)["slot_name"]
        pieces.append({"slot": slot, "slot_name": name, "before": _piece(pb), "after": _piece(pa),
                       "cost_delta": round((pa or {}).get("cost", 0) - (pb or {}).get("cost", 0), 2)})
    totals = [{"tier": t, "before": before[t]["total"], "after": after[t]["total"]}
              for t in before if t in after]
    status = None
    if b["status"] != a["status"]:
        status = {"before": STATUS_LABEL[b["status"]], "after": STATUS_LABEL[a["status"]]}
    return {"tier": tier, "pieces": pieces, "totals": totals, "status": status,
            "owned": _owned_use(after, new_owned or [], tier)}


def summary(diff: dict, changed: bool) -> str:
    """The first line of the chat reply."""
    if not changed:
        return "That matches what I already had for you, so the plan stays the same."
    name = diff["tier"].capitalize()
    others = [t for t in diff["totals"] if t["tier"] != diff["tier"] and abs(t["after"] - t["before"]) >= 0.5]
    if diff["pieces"] or diff["status"]:
        return f"Got it. Here's what changed in your {name} kit."
    if others:
        return (f"Got it. Your {name} kit stays the same; the other budgets changed "
                "(switch budget to see them).")
    return f"Got it. Your {name} kit was already right for that, so nothing changed."
