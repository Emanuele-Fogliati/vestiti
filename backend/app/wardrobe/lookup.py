"""Find the clothing model a traveller owns, from its name or from what a photo shows.

Two sources, both local and free:
- known_models.json: well-known model lines, including older and discontinued ones
  (a model line keeps its warmth and waterproofing across versions);
- the shop catalog (products table): what is on sale now.

There is no free public database of clothing with technical data, and none at all for
discontinued models, so what is not in these two lists gets an estimate from the name
(local language model, or keyword rules when it is off). The traveller always confirms.
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.classify import classify, extract_specs
from app.engine.garments import FOOTWEAR_TYPES, REF_CLO, SLOT_KEYS, level_for_clo
from app.models import Product

LIB_PATH = Path(__file__).with_name("known_models.json")
MATERIALS = ("merino", "synthetic", "fleece", "down", "cotton", "other")
WARMTH = ("light", "medium", "warm", "very_warm")

# what people type -> how the brand is written in the lists
BRAND_ALIASES = {
    "tnf": "the north face", "north face": "the north face", "northface": "the north face",
    "arcteryx": "arc'teryx", "arc teryx": "arc'teryx", "arcterix": "arc'teryx",
    "quechua": "decathlon", "forclaz": "decathlon", "wedze": "decathlon", "simond": "decathlon",
    "kalenji": "decathlon", "kiprun": "decathlon", "patagucci": "patagonia",
    "fjallraven": "fjällräven", "fjall raven": "fjällräven", "hh": "helly hansen",
    "levis": "levi's", "levi": "levi's", "dr martens": "dr. martens", "doc martens": "dr. martens",
    "ua": "under armour", "under armor": "under armour", "rei": "rei co-op",
    "mountain hardware": "mountain hardwear", "mont bell": "montbell",
}
# words that carry no meaning for the match
STOP = {"the", "a", "an", "my", "of", "and", "for", "with", "men", "mens", "women", "womens",
        "man", "woman", "uomo", "donna", "il", "la", "lo", "di", "da", "e", "jacket", "giacca"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9.]+", " ", s).replace(" . ", " ").strip()


def _brand_key(s: str) -> str:
    return norm(s).replace(".", "")


_ALIASES_N = {_brand_key(k): _brand_key(v) for k, v in BRAND_ALIASES.items()}


def tokens(s: str) -> list[str]:
    return [t.strip(".") for t in norm(s).split() if t.strip(".") and t.strip(".") not in STOP]


@lru_cache
def library() -> list[dict]:
    data = json.loads(LIB_PATH.read_text(encoding="utf-8"))
    out = []
    for m in data["models"]:
        out.append({**m, "ref": f"lib:{m['id']}", "source": "known"})
    return out


def product_to_model(p: Product) -> dict:
    """A shop product described with the same coarse fields as a wardrobe item."""
    specs = p.specs or {}
    clo = specs.get("clo")
    ins = specs.get("insulation")
    material = {"synthetic_base": "synthetic"}.get(ins, ins)
    if material not in MATERIALS:
        material = None
    wp = bool(specs.get("waterproof") or (specs.get("waterproof_mm") or 0) >= 5000)
    m = {
        "ref": f"product:{p.id}", "id": p.id, "source": "shop", "brand": p.brand,
        "name": re.sub(r"\s*\((Men|Women)\)$", "", p.name), "category": p.category,
        "warmth": level_for_clo(p.category, clo) if clo else "medium",
        "clo": clo, "waterproof": wp, "windproof": bool(specs.get("windproof") or wp),
        "material": material,
    }
    if p.category == "footwear":
        m["footwear_type"] = specs.get("footwear_type") or "sneaker"
        m["ankle_support"] = bool(specs.get("ankle_support"))
    if specs.get("fill_power"):
        m["fill_power"] = specs["fill_power"]
    if specs.get("waterproof_mm"):
        m["waterproof_mm"] = specs["waterproof_mm"]
    return m


def shop_models(db: Session) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for p in db.scalars(select(Product).where(Product.active.is_(True))):
        m = product_to_model(p)
        key = (_brand_key(m["brand"]), norm(m["name"]))
        seen.setdefault(key, m)  # men's and women's cut: one entry
    return list(seen.values())


def _haystack(m: dict) -> tuple[str, list[str], list[str]]:
    brand = _brand_key(m.get("brand") or "")
    name_toks = tokens(m["name"])
    for a in m.get("aka") or []:
        name_toks += tokens(a)
    return brand, name_toks, tokens(m.get("brand") or "")


def _tok_match(q: str, cands: list[str]) -> float:
    if q in cands:
        return 1.0
    if len(q) >= 3 and any(c.startswith(q) for c in cands):
        return 0.9
    # model codes: "mh500" vs "mh 500", typos: "torentshell"
    if len(q) >= 4:
        best = max((difflib.SequenceMatcher(None, q, c).ratio() for c in cands), default=0)
        if best >= 0.8:
            return best * 0.9
    return 0.0


def _split_codes(toks: list[str]) -> list[str]:
    """'mh500' -> 'mh', '500' too, so either spelling matches."""
    out = list(toks)
    for t in toks:
        m = re.fullmatch(r"([a-z]+)(\d+)", t)
        if m:
            out += [m.group(1), m.group(2)]
    return out


def score(query: str, m: dict) -> float:
    q = tokens(query)
    if not q:
        return 0.0
    qn = " ".join(q)
    brand, name_toks, brand_toks = _haystack(m)
    # a brand written another way ("tnf", "quechua") counts as the brand
    for alias, real in _ALIASES_N.items():
        if re.search(rf"\b{re.escape(alias)}\b", qn) and real == brand:
            qn = re.sub(rf"\b{re.escape(alias)}\b", " ".join(brand_toks), qn)
    q = qn.split()
    brand_hit = bool(brand_toks) and all(t in q for t in brand_toks)
    rest = [t for t in q if t not in brand_toks] if brand_hit else q
    hay = _split_codes(name_toks)
    if not rest:
        return 0.5 if brand_hit else 0.0  # brand only: list its models
    hits = [_tok_match(t, hay + ([] if brand_hit else brand_toks)) for t in _split_codes(rest)]
    got = sum(hits) / len(hits)
    if got == 0:
        return 0.0
    # how much of the model name the query covers (prefer "beta ar" over "beta" for "beta ar")
    name_main = set(_split_codes(tokens(m["name"])))
    cover = len([t for t in name_main if any(_tok_match(t, [x]) for x in _split_codes(rest))]) / max(len(name_main), 1)
    s = 0.6 * got + 0.15 * cover + (0.25 if brand_hit else 0.0)
    if not brand_hit and m.get("brand") and _brand_mentioned_other(q, brand):
        s *= 0.4  # the query names another brand
    return round(s, 3)


def _brand_mentioned_other(q: list[str], brand: str) -> bool:
    qn = " ".join(q)
    for b in _all_brands():
        if b and b != brand and re.search(rf"\b{re.escape(b)}\b", qn):
            return True
    return False


@lru_cache
def _all_brands() -> tuple[str, ...]:
    return tuple(sorted({_brand_key(m["brand"]) for m in library() if m["brand"]}
                        | set(_ALIASES_N.values())))


def search(db: Session, query: str, category: str | None = None, limit: int = 8) -> list[dict]:
    query = (query or "")[:120]
    pool = shop_models(db) + library()
    if category in SLOT_KEYS:
        pool = [m for m in pool if m["category"] == category]
    scored = [(score(query, m), m) for m in pool]
    scored = [(s, m) for s, m in scored if s >= 0.45]
    # near-equal matches: what is on sale now first, then current models, then older ones
    scored.sort(key=lambda x: (-round(x[0] * 10), x[1]["source"] != "shop", -x[0], x[1]["source"] != "shop", bool(x[1].get("older")),
                               x[1]["brand"] == "", x[1]["name"]))
    out, seen = [], set()
    for s, m in scored:
        key = (_brand_key(m["brand"]), norm(m["name"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(public(m, s))
        if len(out) >= limit:
            break
    return out


def public(m: dict, s: float | None = None) -> dict:
    """What the app shows and what becomes a wardrobe item when confirmed."""
    cat = m["category"]
    item = {
        "ref": m["ref"], "source": m["source"], "brand": m.get("brand") or None, "name": m["name"],
        "category": cat, "warmth": m.get("warmth") or "medium",
        "waterproof": bool(m.get("waterproof")), "windproof": bool(m.get("windproof")),
        "material": m.get("material"), "footwear_type": m.get("footwear_type") if cat == "footwear" else None,
        "ankle_support": bool(m.get("ankle_support")) if cat == "footwear" else False,
        "older": bool(m.get("older")), "note": m.get("note"),
        "clo": m.get("clo"),
    }
    specs = {k: m[k] for k in ("fill_power", "waterproof_mm") if m.get(k)}
    item["specs"] = specs or None
    if s is not None:
        item["score"] = s
    return item


def by_ref(db: Session, ref: str) -> dict | None:
    if ref.startswith("lib:"):
        return next((public(m) for m in library() if m["ref"] == ref), None)
    if ref.startswith("product:"):
        p = db.get(Product, ref.split(":", 1)[1])
        return public(product_to_model(p)) if p else None
    return None


# ------------------------------------------------------------------ estimate from a name

def clean_guess(d: dict, fallback_name: str) -> dict | None:
    """Keep only valid values from a model's (or the rules') answer."""
    cat = d.get("category")
    if cat not in SLOT_KEYS:
        return None
    warmth = d.get("warmth") if d.get("warmth") in WARMTH else "medium"
    mat = d.get("material") if d.get("material") in MATERIALS else None
    ft = d.get("footwear_type") if d.get("footwear_type") in FOOTWEAR_TYPES else None
    item = {
        "ref": None, "source": "estimate", "brand": (str(d.get("brand") or "").strip()[:120] or None),
        "name": (str(d.get("name") or "").strip() or fallback_name)[:200], "category": cat,
        "warmth": warmth, "waterproof": d.get("waterproof") is True,
        "windproof": d.get("windproof") is True or d.get("waterproof") is True, "material": mat,
        "footwear_type": (ft or "sneaker") if cat == "footwear" else None,
        "ankle_support": d.get("ankle_support") is True if cat == "footwear" else False,
        "older": False, "note": None, "clo": None, "specs": None,
    }
    return item


def guess_by_rules(name: str) -> dict | None:
    slot = classify(name)
    if slot is None:
        return None
    specs = extract_specs(slot, name)
    ins = {"synthetic_base": "synthetic"}.get(specs.get("insulation"), specs.get("insulation"))
    return clean_guess({
        "category": slot, "name": name, "warmth": level_for_clo(slot, specs.get("clo") or REF_CLO[slot]["medium"]),
        "waterproof": bool(specs.get("waterproof") or specs.get("waterproof_mm")),
        "windproof": bool(specs.get("windproof")), "material": ins,
        "footwear_type": specs.get("footwear_type"), "ankle_support": specs.get("ankle_support"),
    }, name)


GUESS_SYSTEM = """You help a traveller describe a piece of clothing they own, from its name.
Answer with one JSON object and nothing else:
{"brand": string or null, "name": short product name, "category": one of
 shell_top (rain or wind jacket), insulation_top (down or padded jacket, coat), mid_top (fleece,
 jumper, hoodie, softshell), base_top (T-shirt, thermal top, shirt), base_bottom (thermal leggings),
 trousers (trousers, jeans, shorts), shell_bottom (rain or ski trousers), headwear (beanie),
 gloves, sun_hat (cap, sun hat), socks, footwear (any shoe or boot),
 "warmth": light|medium|warm|very_warm (compared with others of the same category),
 "waterproof": true|false, "windproof": true|false,
 "material": merino|synthetic|fleece|down|cotton|other|null,
 "footwear_type": sandal|sneaker|trail_runner|hiking_boot|mountaineering_boot|null,
 "ankle_support": true|false, "known": true if you know this exact product, else false}
If you do not know the product, judge only from the words in the name. Never invent a model."""


def guess_from_name(name: str, llm=None) -> dict | None:
    """Estimate from the name: language model first, keyword rules if it is off."""
    from app.llm.client import LLMClient, LLMUnavailable
    name = name.strip()[:200]
    try:
        d = (llm or LLMClient()).chat_json(GUESS_SYSTEM, f"Name: {name}", max_tokens=300, timeout=45)
        item = clean_guess(d, name)
        if item:
            item["by"] = "ai"
            return item
    except (LLMUnavailable, ValueError, json.JSONDecodeError):
        pass
    item = guess_by_rules(name)
    if item:
        item["by"] = "rules"
    return item
