"""Chat sentence -> structured profile updates.

The model only fills the same fields the quiz has (how cold you run, pace, evenings, what
you already own). It never chooses products: the deterministic engine does that with the
updated profile. Every field is validated, and the rule-based reader fills what the model
missed or runs alone when the model is offline.
"""
from __future__ import annotations

import json
import logging

from app.engine.garments import FOOTWEAR_TYPES, LEVELS, SLOT_KEYS
from app.llm.client import LLMClient, LLMUnavailable
from app.schemas import COLD, EVENINGS, PACES
from app.services.profile import OwnedPiece, Updates, read_rules

log = logging.getLogger(__name__)

SYSTEM = f"""You read one message a traveller writes to a packing app, in any language, and
turn it into profile settings. Reply with JSON only:
{{"cold": one of {list(COLD)} or null,
  "pace": one of {list(PACES)} or null,
  "evenings": one of {list(EVENINGS)} or null,
  "owned": [{{"category": one of {SLOT_KEYS}, "name": "short English name, e.g. Old Decathlon fleece",
             "brand": string or null, "warmth": one of {LEVELS}, "waterproof": true/false,
             "material": "merino"|"synthetic"|"fleece"|"down"|"cotton"|"other"|null,
             "footwear_type": one of {FOOTWEAR_TYPES} or null}}],
  "question": true/false}}
Meaning:
- cold: how easily they feel cold. "I'm always cold", "sono freddoloso" = very_cold; "a bit chilly
  sometimes" = bit_cold; "normal" = average; "I never feel the cold", "non patisco il freddo" = warm.
- pace: relaxed = slow walker, many photo stops; brisk = fast, fit, rarely stops.
- evenings: early = back inside after dinner; late = stays outdoors after dark (night life,
  stargazing); sometimes = in between.
- owned: clothes they say they ALREADY HAVE or will bring. Never include things they ask about,
  want to buy, or say they do not have. Category guide: fleece/pile = mid_top; puffy/down
  jacket/piumino = insulation_top; rain jacket/k-way/hardshell = shell_top; rain trousers =
  shell_bottom; hiking trousers/jeans = trousers; thermal top/merino base layer = base_top;
  thermal leggings = base_bottom; boots/scarponi = footwear (hiking_boot); beanie = headwear.
- question: true when the message asks something.
Use null or [] for anything the message does not say. Do not guess."""


def _pieces(raw) -> list[OwnedPiece]:
    out = []
    for o in raw if isinstance(raw, list) else []:
        if not isinstance(o, dict) or o.get("category") not in SLOT_KEYS:
            continue
        p = OwnedPiece(category=o["category"], name=str(o.get("name") or ""),
                       brand=o.get("brand") if isinstance(o.get("brand"), str) else None,
                       warmth=o.get("warmth") if o.get("warmth") in LEVELS else "medium",
                       waterproof=o.get("waterproof") is True,
                       material=o.get("material") if isinstance(o.get("material"), str) else None,
                       footwear_type=o.get("footwear_type") if isinstance(o.get("footwear_type"), str) else None)
        if p.clean():
            out.append(p)
    return out


def read_message(text: str, client: LLMClient | None = None) -> tuple[Updates, str]:
    """Returns (updates, reader) where reader is 'llm' or 'rules'."""
    rules = read_rules(text)
    client = client or LLMClient()
    try:
        data = client.chat_json(SYSTEM, f"Message: {text}", temperature=0.0, max_tokens=600)
    except (LLMUnavailable, ValueError, json.JSONDecodeError) as e:
        log.info("profile chat: model unavailable or bad JSON (%s), using rules", e)
        return rules, "rules"
    if not isinstance(data, dict):
        return rules, "rules"
    up = Updates(cold=data.get("cold") if data.get("cold") in COLD else None,
                 pace=data.get("pace") if data.get("pace") in PACES else None,
                 evenings=data.get("evenings") if data.get("evenings") in EVENINGS else None,
                 owned=_pieces(data.get("owned")), question=data.get("question") is True)
    # "average" from the model usually means "not mentioned": only the rules may set it back
    if up.cold == "average" and not rules.cold:
        up.cold = None
    if up.pace == "average":
        up.pace = None
    if up.evenings == "sometimes" and not rules.evenings:
        up.evenings = None
    return up.merge(rules), "llm"
