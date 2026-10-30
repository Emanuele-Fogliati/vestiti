from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import rate_limit
from app.engine.activities import ACTIVITIES, ACTIVITY_TYPES, DIFFICULTIES
from app.engine.garments import FOOTWEAR_TYPES, LEVELS, SLOTS
from app.llm.client import LLMClient
from app.models import Product
from app.weather import geocode

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("select 1"))
    return {"ok": True}


@router.get("/config")
def config():
    s = get_settings()
    return {
        "brand": {"name": s.brand_name, "tagline": s.brand_tagline, "domain": s.brand_domain,
                  "support_email": s.support_email},
        "theme": s.theme,
        "currency": s.currency,
        "ai": LLMClient().public_status(),
        "slots": [{"key": x.key, "code": x.code, "name": x.name, "torso": x.torso} for x in SLOTS],
        "activity_types": ACTIVITY_TYPES,
        "difficulties": DIFFICULTIES,
        "warmth_levels": LEVELS,
        "footwear_types": FOOTWEAR_TYPES,
        "activities": {k: {"label": v.label, "met_moving": v.met_moving} for k, v in ACTIVITIES.items()},
        "disclosure": (f"{s.brand_name} is free. When you buy through our links we may earn a "
                       "commission from the shop, at no extra cost to you. It never changes "
                       "what we recommend: if what you own is fine, we say so."),
    }


# each search is a request to Open-Meteo from our server: without a limit anyone could burn
# our share of their free tier (and get weather blocked for every user)
@router.get("/geocode", dependencies=[Depends(rate_limit("geo", "geo_rate_limit_per_minute"))])
def geocode_search(q: str = Query(min_length=2, max_length=120),
                   countries: str | None = Query(default=None, max_length=200)):
    """countries: the trip's ISO codes ("PE,BO"); places there are listed first."""
    res = geocode.search(q)
    if countries:
        want = {c.strip().upper() for c in countries.split(",") if c.strip()}
        res.sort(key=lambda r: r.get("country_code") not in want)
    return {"results": res}


@router.get("/catalog/products")
def catalog(slot: str | None = Query(None, max_length=40), q: str | None = Query(None, max_length=120),
            brand: str | None = Query(None, max_length=120),
            sort: str = "price_asc", limit: int = Query(60, ge=1, le=200),
            offset: int = Query(0, ge=0, le=100_000),
            db: Session = Depends(get_db)):
    stmt = select(Product).where(Product.active.is_(True))
    if slot:
        stmt = stmt.where(Product.category == slot)
    if brand:
        stmt = stmt.where(Product.brand == brand)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where((Product.name.ilike(like)) | (Product.brand.ilike(like)))
    order = {"price_asc": Product.price.asc(), "price_desc": Product.price.desc(),
             "rating": Product.rating.desc(), "name": Product.name.asc()}.get(sort, Product.price.asc())
    rows = db.scalars(stmt.order_by(order).offset(offset).limit(limit)).all()
    return {"items": [{"id": p.id, "slot": p.category, "brand": p.brand, "name": p.name,
                       "price": p.price, "currency": p.currency, "specs": p.specs,
                       "rating": p.rating, "review_count": p.review_count, "gender": p.gender,
                       "image_url": p.image_url, "merchant": p.merchant} for p in rows]}


@router.get("/catalog/brands")
def brands(slot: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Product.brand).where(Product.active.is_(True)).distinct()
    if slot:
        stmt = stmt.where(Product.category == slot)
    return {"brands": sorted(db.scalars(stmt).all())}
