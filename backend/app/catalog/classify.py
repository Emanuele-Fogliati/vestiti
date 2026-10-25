"""Map raw affiliate-feed products to our slots and estimate technical specs.

Feeds rarely carry clo values or clean waterproof ratings. We read what the title,
description and category give us, and mark every guessed value with
specs["estimated"] = [field names], so the UI can say "estimated".
"""
from __future__ import annotations

import re

# Most specific first. Each entry: (slot, any-of keywords)
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("shell_bottom", ("rain pant", "rain trouser", "waterproof trouser", "waterproof pant",
                      "overtrouser", "over trouser", "shell pant", "hardshell pant", "gore-tex pant",
                      "rain pants")),
    ("base_bottom", ("base layer bottom", "baselayer bottom", "thermal bottom", "long john",
                     "leggings", "tights", "base layer pant", "base layer legging")),
    ("insulation_top", ("down jacket", "down hoody", "down hoodie", "puffer", "puffy",
                        "insulated jacket", "synthetic jacket", "primaloft", "down parka",
                        "down sweater", "thermoball", "nano puff", "atom hoody", "down coat",
                        "insulated hoody", "belay parka")),
    ("shell_top", ("rain jacket", "waterproof jacket", "shell jacket", "hardshell", "hard shell",
                   "gore-tex jacket", "rain shell", "storm jacket", "anorak", "rain coat",
                   "raincoat", "waterproof shell")),
    ("mid_top", ("fleece", "midlayer", "mid-layer", "mid layer", "grid hoody", "polartec")),
    ("base_top", ("base layer", "baselayer", "thermal top", "merino crew", "merino top",
                  "long sleeve", "long-sleeve", "t-shirt", " tee ", "heattech")),
    ("gloves", ("glove", "mitten", "mitt ")),
    ("socks", ("sock",)),
    ("sun_hat", ("sun hat", "bucket hat", "booney", "brim hat", "sun cap", "running cap",
                 "baseball cap", "sun runner")),
    ("headwear", ("beanie", "toque", "knit hat", "watch cap", "balaclava")),
    ("footwear", ("boot", "shoe", "trail runner", "sandal", "sneaker", "trainer", "approach")),
    ("trousers", ("hiking pant", "trekking pant", "trekking trouser", "hiking trouser",
                  "trousers", "pants", "shorts", "convertible", "jogger")),
]
EXCLUDE = ("kid", "child", "junior", "toddler", "baby", "dog ", "backpack", "tent",
           "sleeping bag", "gift card", "replacement", "laces", "insole")


def classify(text: str) -> str | None:
    t = f" {text.lower()} "
    if any(x in t for x in EXCLUDE):
        return None
    for slot, words in RULES:
        if any(w in t for w in words):
            return slot
    # Second pass: a generic "jacket" named after its membrane or fill.
    if re.search(r"\b(jacket|hoody|hoodie|parka)\b", t):
        if any(w in t for w in WATERPROOF_TECH):
            return "shell_top"
        if any(w in t for w in (" down ", "insulated", "synthetic fill", "800 fill", "850 fill")):
            return "insulation_top"
    return None


# Membrane and fabric names that make a jacket a waterproof shell.
WATERPROOF_TECH = ("gore-tex", "goretex", "gore tex", "h2no", "futurelight", "dryvent",
                   "pertex shield", "ascentshell", "omni-tech", "outdry", "event ", "waterproof",
                   "2.5l", "3l", "2l ")


def gender_of(text: str, column: str | None = None) -> str:
    v = (column or "").lower()
    t = f" {text.lower()} "
    for src in (v, t):
        if any(w in src for w in ("women", "womens", "women's", "female", "ladies", " w ")):
            return "women"
        if any(w in src for w in (" men", "mens", "men's", "male", " m ")) or src.strip() in (
                "men", "male"):
            return "men"
    return "unisex"


def _num(s: str) -> int:
    return int(re.sub(r"[^\d]", "", s))


def extract_specs(slot: str, text: str) -> dict:
    t = text.lower()
    specs: dict = {}
    est: list[str] = []

    # insulation material
    if "merino" in t or "wool" in t:
        specs["insulation"] = "merino"
    elif "down" in t and slot == "insulation_top":
        specs["insulation"] = "down"
    elif "fleece" in t or "polartec" in t:
        specs["insulation"] = "fleece"
    elif "cotton" in t and "poly" not in t:
        specs["insulation"] = "cotton"
    elif slot in ("base_top", "base_bottom"):
        specs["insulation"] = "synthetic_base"
    elif slot == "insulation_top":
        specs["insulation"] = "synthetic"

    m = re.search(r"(\d{3})\s?(?:fp|fill|cuin|-fill)", t)
    if m:
        specs["fill_power"] = int(m.group(1))

    # waterproofing
    m = re.search(r"(\d{1,2}[,.]?\d{3})\s?mm", t) or re.search(r"(\d{1,2})\s?k\s?(?:mm|/)", t)
    if m:
        val = m.group(1)
        specs["waterproof_mm"] = _num(val) * (1000 if len(re.sub(r"[^\d]", "", val)) <= 2 else 1)
    elif "gore-tex pro" in t:
        specs["waterproof_mm"] = 28000
        est.append("waterproof_mm")
    elif "gore-tex" in t or "goretex" in t or " gtx" in t or "futurelight" in t or "event" in t:
        specs["waterproof_mm"] = 28000 if slot in ("shell_top", "shell_bottom") else 0
        specs["waterproof"] = True
        if slot in ("shell_top", "shell_bottom"):
            est.append("waterproof_mm")
    elif "waterproof" in t and "water-resistant" not in t:
        specs["waterproof"] = True
        if slot in ("shell_top", "shell_bottom"):
            specs["waterproof_mm"] = 10000
            est.append("waterproof_mm")
    m = re.search(r"(\d{1,2}[,.]?\d{3})\s?g/m", t)
    if m:
        specs["breathability_g"] = _num(m.group(1))
    elif "gore-tex" in t or " gtx" in t:
        specs["breathability_g"] = 20000
        est.append("breathability_g")
    if any(w in t for w in ("windproof", "windstopper", "wind-resistant", "infinium")) or \
            specs.get("waterproof") or specs.get("waterproof_mm", 0) >= 5000:
        specs["windproof"] = True
    m = re.search(r"(?<![\d/])(\d{2,4})\s?g(?:rams)?\b(?!/)", t)
    if m and 30 <= int(m.group(1)) <= 2500:
        specs["weight_g"] = int(m.group(1))
    if any(w in t for w in ("packable", "packs into", "stuff sack", "ultralight", "ultra light")):
        specs["packable"] = True

    if slot == "footwear":
        if "sandal" in t:
            ft = "sandal"
        elif any(w in t for w in ("mountaineering", "crampon", "alpine boot", "nepal")):
            ft = "mountaineering_boot"
        elif "boot" in t or " mid" in t:
            ft = "hiking_boot"
        elif any(w in t for w in ("trail", "hiking shoe", "approach")):
            ft = "trail_runner"
        else:
            ft = "sneaker"
        specs["footwear_type"] = ft
        specs["ankle_support"] = ft in ("hiking_boot", "mountaineering_boot")
        specs["insulated"] = any(w in t for w in ("insulated", "winter", "thinsulate", "snow boot"))
        if any(w in t for w in ("waterproof", "gore-tex", "gtx", " wp")):
            specs["waterproof"] = True

    specs["clo"] = estimate_clo(slot, t, specs)
    est.append("clo")
    specs["estimated"] = est
    return specs


def estimate_clo(slot: str, t: str, specs: dict) -> float:
    if slot == "insulation_top":
        c = 0.55
        fp = specs.get("fill_power") or 0
        if fp >= 800:
            c += 0.12
        elif fp >= 700:
            c += 0.07
        if any(w in t for w in ("expedition", "belay", "parka", "heavyweight")):
            c += 0.3
        if any(w in t for w in ("ultra light", "ultralight", "light down")):
            c -= 0.07
        if "hood" in t:
            c += 0.03
        if "vest" in t or "gilet" in t:
            c -= 0.2
        return round(max(c, 0.3), 2)
    if slot == "mid_top":
        if any(w in t for w in ("100", "micro", "light")):
            return 0.26
        if any(w in t for w in ("300", "heavy", "sherpa", "pile")):
            return 0.45
        return 0.34
    if slot == "base_top":
        if any(w in t for w in ("t-shirt", " tee", "short sleeve", "short-sleeve")):
            return 0.08
        if any(w in t for w in ("heavyweight", "260", "250", "expedition")):
            return 0.28
        if any(w in t for w in ("midweight", "200", "mid weight")):
            return 0.2
        return 0.15
    if slot == "base_bottom":
        if any(w in t for w in ("heavyweight", "260", "250")):
            return 0.18
        if any(w in t for w in ("midweight", "200")):
            return 0.14
        return 0.11
    if slot == "trousers":
        if "short" in t:
            return 0.06
        if any(w in t for w in ("softshell", "winter", "lined", "insulated")):
            return 0.28
        return 0.2
    if slot == "shell_top":
        return 0.12
    if slot == "shell_bottom":
        return 0.08
    if slot == "gloves":
        if any(w in t for w in ("mitt", "insulated", "expedition", "guide")):
            return 0.09
        if "liner" in t:
            return 0.03
        return 0.05
    if slot == "headwear":
        return 0.05 if "balaclava" not in t else 0.06
    if slot == "socks":
        return 0.04 if "merino" in t or "wool" in t else 0.03
    if slot == "footwear":
        return 0.07 if specs.get("insulated") else 0.04
    return 0.01
