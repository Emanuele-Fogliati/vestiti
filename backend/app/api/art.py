from fastapi import APIRouter, HTTPException, Response

from app import art

router = APIRouter(prefix="/api/art", tags=["art"])


@router.get("/landmarks")
def list_landmarks():
    return [{"id": lm.id, "label": lm.label, "country": lm.country} for lm in art.landmarks()]


@router.get("/landmarks/{landmark_id}.svg")
def landmark_svg(landmark_id: str, flat: bool = False):
    """The scene as an SVG fragment (no <svg> wrapper) that the page inlines: by default with the
    official look (the place's palette, outline and shadow); ?flat=1 gives the drawing as stored."""
    body = art.svg(landmark_id) if flat else art.rendered(landmark_id)
    if body is None:
        raise HTTPException(404, "Unknown landmark")
    return Response(body, media_type="text/plain; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=86400"})
