"""Tracked outbound links. Destinations come only from the database (no open redirect)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import inspire
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


def _redirect(db: Session, request: Request, user: User | None, kind: str, network: str,
              url: str, program_id: str | None = None) -> RedirectResponse:
    click = AffiliateClick(user_id=user.id if user else None, kind=kind, network=network,
                           destination_url="", referrer=request.headers.get("referer"),
                           user_agent_hash=ua_hash(request.headers.get("user-agent")))
    db.add(click)
    db.flush()
    out = network_for(network, get_settings()).build(url, click.id, program_id)
    click.destination_url = out.url
    click.tracked = out.tracked
    db.commit()
    return RedirectResponse(out.url, status_code=302,
                            headers={"Referrer-Policy": "no-referrer-when-downgrade",
                                     "X-Robots-Tag": "noindex, nofollow"})


@router.get("/excursion/{slug}/{stop}/{n}")
def go_excursion(slug: str, stop: int, n: int, request: Request, provider: str = "getyourguide",
                 user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """A tour at one stop of a ready-made itinerary, searched on GetYourGuide or Viator.
    The search words come from the itinerary file, never from the request."""
    it = inspire.get(slug)
    if (it is None or provider not in inspire.EXCURSION_PROVIDERS or not 0 <= stop < len(it.stops)
            or not 0 <= n < len(it.stops[stop].excursions)):
        raise HTTPException(404, "Excursion not available")
    url = inspire.excursion_url(provider, it.stops[stop].excursions[n].query)
    return _redirect(db, request, user, "excursion", provider, url)


@router.get("/tour/{slug}/{n}")
def go_tour(slug: str, n: int, request: Request, user: User | None = Depends(optional_user),
            db: Session = Depends(get_db)):
    """A whole organised group trip similar to the itinerary (Intrepid, Exodus...)."""
    it = inspire.get(slug)
    if it is None or not 0 <= n < len(it.group_trips):
        raise HTTPException(404, "Trip not available")
    g = it.group_trips[n]
    return _redirect(db, request, user, "tour", g.network, str(g.url), g.program_id)
