import hashlib

from fastapi import APIRouter, HTTPException, Request, Response

from app import art

router = APIRouter(prefix="/api/art", tags=["art"])


@router.get("/landmarks")
def list_landmarks():
    return [{"id": lm.id, "label": lm.label, "country": lm.country} for lm in art.landmarks()]


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
