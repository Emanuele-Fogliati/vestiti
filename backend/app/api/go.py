"""Tracked outbound links. Destinations come only from the database (no open redirect)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.affiliates.networks import network_for
from app.config import get_settings
from app.db import get_db
from app.deps import optional_user
from app.engine.garments import SLOT_KEYS
from app.models import AffiliateClick, Product, RentalPartner, Trip, User
from app.security import ua_hash

router = APIRouter(prefix="/api/go", tags=["outbound"])


def _trip_id(db: Session, trip_id: str | None, user: User | None) -> str | None:
    if not trip_id or not user:
        return None
    t = db.get(Trip, trip_id)
    return t.id if t and t.user_id == user.id else None


@router.get("/product/{product_id}")
def go_product(product_id: str, request: Request, trip_id: str | None = None,
               tier: str | None = None, slot: str | None = None,
               user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if p is None or not p.active:
        raise HTTPException(404, "Product not available")
    click = AffiliateClick(user_id=user.id if user else None, trip_id=_trip_id(db, trip_id, user),
                           product_id=p.id, kind="buy", network=p.network,
                           tier=tier if tier in ("cheap", "medium", "premium") else None,
                           slot=slot if slot in SLOT_KEYS else None, price=p.price,
                           destination_url="", referrer=request.headers.get("referer"),
                           user_agent_hash=ua_hash(request.headers.get("user-agent")))
    db.add(click)
    db.flush()
    out = network_for(p.network, get_settings()).build(p.url, click.id, p.program_id)
    click.destination_url = out.url
    click.tracked = out.tracked
    db.commit()
    return RedirectResponse(out.url, status_code=302,
                            headers={"Referrer-Policy": "no-referrer-when-downgrade",
                                     "X-Robots-Tag": "noindex, nofollow"})


@router.get("/rental/{partner_id}")
def go_rental(partner_id: str, request: Request, slot: str, start: date, end: date,
              country: str | None = None, trip_id: str | None = None,
              user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    r = db.get(RentalPartner, partner_id)
    if r is None or not r.active or slot not in (r.categories or []):
        raise HTTPException(404, "Rental not available")
    if end < start or (end - start).days > 120:
        raise HTTPException(422, "Bad dates")
    url = r.url_template.format(category=slot, start=start.isoformat(), end=end.isoformat(),
                                country=(country or "")[:2])
    click = AffiliateClick(user_id=user.id if user else None, trip_id=_trip_id(db, trip_id, user),
                           rental_partner_id=r.id, kind="rent", network=r.network, slot=slot,
                           destination_url="", referrer=request.headers.get("referer"),
                           user_agent_hash=ua_hash(request.headers.get("user-agent")))
    db.add(click)
    db.flush()
    out = network_for(r.network, get_settings()).build(url, click.id)
    click.destination_url = out.url
    click.tracked = out.tracked
    db.commit()
    return RedirectResponse(out.url, status_code=302)
