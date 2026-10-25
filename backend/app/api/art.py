from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import art
from app.art import generate
from app.db import get_db
from app.deps import current_user, rate_limit
from app.models import PlaceArt, User

router = APIRouter(prefix="/api/art", tags=["art"])
art_limit = rate_limit("art", "art_rate_limit_per_minute")


@router.get("/landmarks")
def list_landmarks():
    return [{"id": lm.id, "label": lm.label, "country": lm.country} for lm in art.landmarks()]


@router.get("/landmarks/{landmark_id}.svg")
def landmark_svg(landmark_id: str):
    """The scene as an SVG fragment (no <svg> wrapper): the page inlines it so the --il-* tokens apply."""
    body = art.svg(landmark_id)
    if body is None:
        raise HTTPException(404, "Unknown landmark")
    return Response(body, media_type="text/plain; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=86400"})


class PlaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    country_code: str | None = Field(default=None, max_length=2)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


def _place_out(row: PlaceArt | None) -> dict:
    if row is None:
        return {"status": "none"}
    out = {"status": row.status, "key": row.key, "label": row.subject}
    if row.status == "ready":
        out["url"] = f"/api/art/places/{row.key}.webp?v={int(row.updated_at.timestamp())}"
    return out


@router.post("/places", dependencies=[Depends(art_limit)])
def place_art(body: PlaceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The model-made illustration for a place outside the landmark library.

    ready: url to show. pending: being drawn, ask again in a few seconds. failed / none: keep the
    generic scene. Only signed-in users (guests included) can queue new images."""
    return _place_out(generate.request(db, body.name, body.country_code, body.latitude, body.longitude))


@router.get("/places/{key}.webp")
def place_image(key: str, theme: str = Query("yellow-black", max_length=30), db: Session = Depends(get_db)):
    row = db.get(PlaceArt, key)
    if row is None or row.status != "ready" or not row.image:
        raise HTTPException(404, "No image for this place")
    return Response(generate.toned_image(row, theme), media_type="image/webp",
                    headers={"Cache-Control": "public, max-age=604800"})
