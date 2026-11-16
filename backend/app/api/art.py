import hashlib
import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

from app import art

router = APIRouter(prefix="/api/art", tags=["art"])


@router.get("/landmarks")
def list_landmarks():
    return [{"id": lm.id, "label": lm.label, "country": lm.country} for lm in art.landmarks()]


@lru_cache
def _about() -> dict:
    """What each drawn place is, one or two sentences from Wikipedia (tools/art/about.py)."""
    f = Path(art.__file__).with_name("about.json")
    return json.loads(f.read_text()) if f.exists() else {}


@router.get("/landmarks/{landmark_id}/about")
def landmark_about(landmark_id: str):
    """The small card a drawing on any map opens (Manu 2026-11-16: "cliccando su ognuna delle
    immagini ... una piccola descrizione ... cos'è quel posto"): what the place is, from Wikipedia
    and credited, and what the drawing shows. A place Wikipedia has no page for: the drawing only."""
    lm = next((x for x in art.landmarks() if x.id == landmark_id), None)
    if lm is None:
        raise HTTPException(404, "Unknown landmark")
    got = _about().get(landmark_id)
    return {"id": lm.id, "country": lm.country, "shows": lm.label,
            "text": got[0] if got else None,
            "source": {"title": got[1], "url": "https://en.wikipedia.org/wiki/" + got[1].replace(" ", "_")} if got else None}


@router.get("/landmarks/{landmark_id}.svg")
def landmark_svg(landmark_id: str, request: Request, flat: bool = False):
    """The scene as an SVG fragment (no <svg> wrapper) that the page inlines: by default with the
    official look (the place's palette, outline and shadow); ?flat=1 gives the drawing as stored."""
    body = art.svg(landmark_id) if flat else art.rendered(landmark_id)
    if body is None:
        raise HTTPException(404, "Unknown landmark")
    # The browser must ask again each time (a redrawn scene shows at once); the ETag keeps it a
    # cheap 304 when nothing changed.
    tag = '"' + hashlib.sha1(body.encode()).hexdigest()[:16] + '"'
    headers = {"Cache-Control": "no-cache", "ETag": tag}
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="text/plain; charset=utf-8", headers=headers)
