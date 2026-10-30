"""Read a few photos of a garment with a local vision model.

Any OpenAI-compatible server that accepts images works (Ollama, llama.cpp with an mmproj,
vLLM, LM Studio). Default: Ollama with Qwen3-VL 8B (`ollama pull qwen3-vl:8b-instruct`).

What this can and cannot do, honestly:
- it reads text well: the brand, the model name or the style code printed on the label;
- it tells the kind of garment, the colour, hood, quilting (down or padded), membrane logos;
- it cannot tell one plain black jacket from another without a readable label.
So the app asks for a label photo and always lets the traveller confirm or correct.
Photos are sent to the model and then dropped: nothing is stored.
"""
from __future__ import annotations

import base64
import logging

import httpx

from app.config import Settings, get_settings
from app.llm.client import LLMUnavailable, _llm_slots, parse_json_loose

log = logging.getLogger(__name__)

SYSTEM = """You look at photos of ONE piece of clothing or ONE pair of shoes that a traveller owns.
Read every piece of text you can see (logos, labels, tags, insoles, tongues): copy it exactly.
Then describe the item. Answer with one JSON object and nothing else:
{"text_seen": [every word or code you can read, exactly as printed],
 "brand": brand name if a logo or label shows it, else null,
 "model": model name if printed (e.g. "Torrentshell 3L", "Moab 3"), else null,
 "style_code": style or article number if printed (e.g. "STY85240", "8 552 123"), else null,
 "category": shell_top (thin rain or wind jacket, smooth fabric, no padding),
   insulation_top (down or padded jacket or coat: quilted, puffy, stitched baffles),
   mid_top (fleece, knitted jumper, hoodie, softshell), base_top (T-shirt, thermal top, any woven shirt),
   base_bottom (thermal leggings), trousers, shell_bottom (rain or ski trousers),
   headwear (beanie), gloves, sun_hat, socks, footwear,
 "colour": main colour,
 "features": short list, e.g. "hood", "quilted baffles", "taped seams", "GORE-TEX logo", "high ankle", "lugged sole",
 "warmth": light|medium|warm|very_warm (compared with others of the same category),
 "waterproof": true|false, "windproof": true|false,
 "material": merino|synthetic|fleece|down|cotton|other|null (use the label if it lists fibres),
 "footwear_type": sandal|sneaker|trail_runner|hiking_boot|mountaineering_boot|null,
 "ankle_support": true|false,
 "label_readable": true if you could read a brand or model on a label, else false,
 "confidence": low|medium|high}
Ignore text that is not on the item (signs, packaging, background). Only report text you can actually read. If unsure, use null. Never guess a model name."""


def vision_status(s: Settings | None = None) -> dict:
    s = s or get_settings()
    return {"enabled": s.vision_enabled and s.llm_enabled, "model": s.vision_model}


def read_garment(images: list[tuple[bytes, str]], kind_hint: str | None = None,
                 settings: Settings | None = None,
                 transport: httpx.BaseTransport | None = None) -> dict:
    """images: (bytes, mime type). Returns the model's JSON (not yet validated)."""
    s = settings or get_settings()
    if not (s.vision_enabled and s.llm_enabled):
        raise LLMUnavailable("photo recognition is switched off")
    parts: list[dict] = [{"type": "text", "text": (
        f"{len(images)} photos of the same item"
        + (f" (the traveller says it is: {kind_hint})" if kind_hint else "") + ".")}]
    for data, mime in images:
        b64 = base64.b64encode(data).decode()
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    body = {"model": s.vision_model, "temperature": 0.1, "max_tokens": 700, "stream": False,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": parts}],
            "response_format": {"type": "json_object"}}
    base = (s.vision_base_url or s.llm_base_url).rstrip("/")
    headers = {"Authorization": f"Bearer {s.llm_api_key}"} if s.llm_api_key else {}
    slots = _llm_slots(s.llm_max_concurrent)
    if not slots.acquire(timeout=s.llm_queue_wait_s):
        raise LLMUnavailable("model busy")
    try:
        with httpx.Client(base_url=base, timeout=s.vision_timeout_s, headers=headers,
                          transport=transport, trust_env=False) as c:
            r = c.post("/chat/completions", json=body)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"] or ""
    except Exception as e:
        log.info("vision call failed: %s", e)
        raise LLMUnavailable(str(e)) from e
    finally:
        slots.release()
    try:
        out = parse_json_loose(text)
    except ValueError as e:
        raise LLMUnavailable("the model did not answer in JSON") from e
    if not isinstance(out, dict):
        raise LLMUnavailable("the model did not answer in JSON")
    return out
