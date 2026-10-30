import time

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import current_user, rate_limit
from app.engine.garments import SLOT_KEYS
from app.llm.client import LLMUnavailable
from app.llm.vision import read_garment
from app.models import User, WardrobeItem
from app.schemas import WardrobeIn, WardrobeOut
from app.wardrobe import lookup

router = APIRouter(prefix="/api/wardrobe", tags=["wardrobe"])
MAX_ITEMS = 300
MAX_PHOTOS = 4
MAX_PHOTO_BYTES = 4_000_000  # the app shrinks photos to ~300 KB before sending
PHOTO_KINDS = {"top": "a jacket or top", "bottom": "trousers or shorts", "shoes": "shoes or boots",
               "small": "a hat, gloves or socks"}


@router.get("", response_model=list[WardrobeOut])
def list_items(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(WardrobeItem).where(WardrobeItem.user_id == user.id)
                      .order_by(WardrobeItem.category, WardrobeItem.created_at)).all()


def _apply(item: WardrobeItem, body: WardrobeIn, db: Session) -> None:
    data = body.model_dump()
    for k, v in data.items():
        setattr(item, k, v)
    # a confirmed model brings its own data; the server looks it up, never trusts the client
    model = lookup.by_ref(db, body.model_ref) if body.model_ref else None
    if body.model_ref and model is None:
        item.model_ref = None
    item.specs = (model or {}).get("specs")
    if model and model.get("clo") and body.clo_override is None \
            and model["category"] == body.category and model["warmth"] == body.warmth:
        item.clo_override = model["clo"]


@router.post("", response_model=WardrobeOut, status_code=201)
def add_item(body: WardrobeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if len(user.wardrobe) >= MAX_ITEMS:
        raise HTTPException(422, f"At most {MAX_ITEMS} wardrobe items")
    item = WardrobeItem(user_id=user.id)
    _apply(item, body, db)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


# ------------------------------------------------------------------ find what you own

@router.get("/lookup")
def find_model(q: str = Query(min_length=2, max_length=120), category: str | None = None,
               _: User = Depends(current_user), db: Session = Depends(get_db),
               __=Depends(rate_limit("geo", "geo_rate_limit_per_minute"))):
    """Models whose name matches what the traveller remembers (shop + older models)."""
    return {"results": lookup.search(db, q, category if category in SLOT_KEYS else None)}


class GuessIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)


@router.post("/guess")
def guess(body: GuessIn, _: User = Depends(current_user),
          __=Depends(rate_limit("ai", "ai_rate_limit_per_minute"))):
    """Not in our lists: estimate from the words of the name. The traveller checks it."""
    item = lookup.guess_from_name(body.name)
    return {"result": item}


_photo_status_cache: dict[str, tuple[float, dict]] = {}


@router.get("/photo-status")
def photo_status(_: User = Depends(current_user)):
    """Can this server read photos right now? (model server up and the vision model there)"""
    s = get_settings()
    out = {"enabled": s.vision_enabled and s.llm_enabled, "available": False, "model": s.vision_model}
    if not out["enabled"]:
        return out
    base = (s.vision_base_url or s.llm_base_url).rstrip("/")
    hit = _photo_status_cache.get(base + s.vision_model)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    try:
        with httpx.Client(base_url=base, timeout=3.0, trust_env=False) as c:
            r = c.get("/models")
            r.raise_for_status()
            ids = [m.get("id", "") for m in r.json().get("data", [])]
        # Ollama lists pulled models; llama.cpp and others serve one model whatever its name
        out["available"] = not ids or any(s.vision_model == i or s.vision_model in i for i in ids) \
            or len(ids) == 1
    except Exception:
        out["available"] = False
    _photo_status_cache[base + s.vision_model] = (time.time(), out)
    return out


def _image_type(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/recognize")
async def recognize(photos: list[UploadFile] = File(...), kind: str = Form("top"),
                    user: User = Depends(current_user), db: Session = Depends(get_db),
                    _=Depends(rate_limit("photo", "photo_rate_limit_per_minute"))):
    """2-4 photos of one item -> what we could read, and the models it may be.
    The photos are only passed to the model: nothing is saved."""
    if not 1 <= len(photos) <= MAX_PHOTOS:
        raise HTTPException(422, f"Send 1 to {MAX_PHOTOS} photos")
    images: list[tuple[bytes, str]] = []
    for f in photos:
        data = await f.read(MAX_PHOTO_BYTES + 1)
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(413, "A photo is too large")
        mime = _image_type(data)
        if mime is None:
            raise HTTPException(422, "Photos must be JPEG, PNG or WebP")
        images.append((data, mime))
    try:
        seen = await _run(images, PHOTO_KINDS.get(kind))
    except LLMUnavailable:
        raise HTTPException(503, "Photo recognition is not available right now. "
                                 "Search by name instead, or describe the item.") from None
    return lookup_from_photos(db, seen, kind)


async def _run(images, hint):
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(read_garment, images, hint)


def lookup_from_photos(db: Session, seen: dict, kind: str) -> dict:
    def s(v, n=80):
        return str(v).strip()[:n] if isinstance(v, (str, int, float)) and str(v).strip() else None

    brand, model, code = s(seen.get("brand")), s(seen.get("model")), s(seen.get("style_code"))
    text = [s(t, 60) for t in (seen.get("text_seen") or []) if s(t, 60)][:30] \
        if isinstance(seen.get("text_seen"), list) else []
    cat = seen.get("category") if seen.get("category") in SLOT_KEYS else None
    kind_cats = {"top": {"shell_top", "insulation_top", "mid_top", "base_top"},
                 "bottom": {"trousers", "shell_bottom", "base_bottom"}, "shoes": {"footwear"},
                 "small": {"headwear", "gloves", "sun_hat", "socks"}}.get(kind)
    if kind_cats and cat not in kind_cats:
        cat = None  # the traveller said what it is: trust them over the model
    results: list[dict] = []
    if model:
        results = lookup.search(db, " ".join(x for x in (brand, model) if x), None, limit=6) \
            or lookup.search(db, model, None, limit=6)
    if not results and text:
        # the model name may be among the words read on the label: try them one by one
        found: dict[str, dict] = {}
        for t in text[:12]:
            for r in lookup.search(db, f"{brand or ''} {t}".strip(), None, limit=3):
                if r["score"] >= 0.7 and r["ref"] not in found:
                    found[r["ref"]] = r
        results = sorted(found.values(), key=lambda r: -r["score"])[:6]
    if kind_cats:
        results = [r for r in results if r["category"] in kind_cats]
    if not results and brand:
        # brand read, model not: show that brand's models of this kind to pick from
        results = [r for r in lookup.search(db, brand, cat, limit=12)
                   if not kind_cats or r["category"] in kind_cats][:8]
    # a plain description of what the photos show, for when no model matches
    described = lookup.clean_guess({
        "brand": brand, "name": " ".join(x for x in (brand, model) if x)
        or _plain_name(cat, seen), "category": cat or _default_cat(kind),
        "warmth": seen.get("warmth"), "waterproof": seen.get("waterproof"),
        "windproof": seen.get("windproof"), "material": seen.get("material"),
        "footwear_type": seen.get("footwear_type"), "ankle_support": seen.get("ankle_support"),
    }, "My item")
    if described:
        described["source"] = "photo"
    conf = seen.get("confidence") if seen.get("confidence") in ("low", "medium", "high") else "low"
    return {
        "seen": {"brand": brand, "model": model, "style_code": code, "text": text,
                 "colour": s(seen.get("colour"), 30),
                 "features": [s(f, 40) for f in (seen.get("features") or []) if s(f, 40)][:8]
                 if isinstance(seen.get("features"), list) else [],
                 "label_readable": seen.get("label_readable") is True, "confidence": conf},
        "results": results, "described": described,
    }


def _default_cat(kind: str) -> str:
    return {"top": "mid_top", "bottom": "trousers", "shoes": "footwear", "small": "headwear"}.get(kind, "mid_top")


def _plain_name(cat: str | None, seen: dict) -> str:
    names = {"shell_top": "rain jacket", "insulation_top": "insulated jacket", "mid_top": "fleece / mid layer",
             "base_top": "top", "base_bottom": "base layer bottoms", "trousers": "trousers",
             "shell_bottom": "rain trousers", "headwear": "beanie", "gloves": "gloves",
             "sun_hat": "hat", "socks": "socks", "footwear": "shoes"}
    colour = seen.get("colour") if isinstance(seen.get("colour"), str) else ""
    return f"{colour.strip()[:20]} {names.get(cat or '', 'item')}".strip().capitalize()


# ------------------------------------------------------------------ edit / remove

def _own(item_id: str, user: User, db: Session) -> WardrobeItem:
    item = db.get(WardrobeItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "Item not found")
    return item


@router.put("/{item_id}", response_model=WardrobeOut)
def update_item(item_id: str, body: WardrobeIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    item = _own(item_id, user, db)
    _apply(item, body, db)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own(item_id, user, db))
    db.commit()
