from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, own_trip
from app.engine.garments import SLOT_KEYS
from app.models import Product, Trip, TripSelection, User, WardrobeItem
from app.schemas import SelectionIn
from app.services.planner import Planner

router = APIRouter(prefix="/api/trips/{trip_id}", tags=["plans"])


def _tier(tier: str) -> str:
    if tier not in ("cheap", "medium", "premium"):
        raise HTTPException(422, "tier must be cheap, medium or premium")
    return tier


@router.get("/weather")
def weather(trip: Trip = Depends(own_trip), user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    p = Planner(db, user, trip)
    out = []
    for st in p.stage_inputs():
        out.append({"stop_id": st.stop_id, "name": st.name, "elevation_m": st.base_elevation_m,
                    "days": [{"date": d.date.isoformat(), "tmax": d.tmax, "tmin": d.tmin,
                              "precip_mm": d.precip_mm, "precip_prob": d.precip_prob,
                              "wind_kmh": d.wind_kmh, "uv": d.uv, "source": d.source,
                              "tmin_p10": d.tmin_p10} for d in st.days]})
    return {"stops": out}


@router.get("/strategy")
def strategy(tier: str = "medium", trip: Trip = Depends(own_trip),
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    return Planner(db, user, trip).strategy(_tier(tier))


@router.get("/plans")
def plans(trip: Trip = Depends(own_trip), user: User = Depends(current_user),
          db: Session = Depends(get_db)):
    return Planner(db, user, trip).plans()


@router.get("/slots/{slot}/products")
def slot_products(slot: str, q: str | None = None, brand: str | None = None,
                  sort: str = Query("fit", pattern="^(fit|price_asc|price_desc|warmth|weight|rating|waterproof)$"),
                  max_price: float | None = None, only_passing: bool = False,
                  trip: Trip = Depends(own_trip), user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    if slot not in SLOT_KEYS:
        raise HTTPException(404, "Unknown slot")
    return Planner(db, user, trip).slot_products(slot, q, brand, sort, max_price, only_passing)


@router.put("/selections")
def set_selection(body: SelectionIn, trip: Trip = Depends(own_trip),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Lock a slot of a tier to a product, an owned item, rental or skip. choice=auto
    removes the lock and lets the optimizer pick again."""
    row = db.scalar(select(TripSelection).where(TripSelection.trip_id == trip.id,
                                                TripSelection.tier == body.tier,
                                                TripSelection.slot == body.slot))
    if body.choice in ("have", "buy") or (body.choice == "auto" and row and row.choice in ("have", "buy")):
        # owning something does not depend on the budget: same answer in every tier
        rows = db.scalars(select(TripSelection).where(TripSelection.trip_id == trip.id,
                                                      TripSelection.slot == body.slot)).all()
        by_tier = {r.tier: r for r in rows}
        for t in ("cheap", "medium", "premium"):
            r = by_tier.get(t)
            if body.choice == "auto":
                if r and r.choice in ("have", "buy"):
                    db.delete(r)
                continue
            if r is None:
                r = TripSelection(trip_id=trip.id, tier=t, slot=body.slot)
                db.add(r)
            r.choice, r.product_id, r.wardrobe_item_id = body.choice, None, None
        db.commit()
        return {"ok": True, "choice": body.choice}
    if body.choice == "auto":
        if row:
            db.delete(row)
            db.commit()
        return {"ok": True, "choice": "auto"}
    if body.choice == "product":
        p = db.get(Product, body.product_id) if body.product_id else None
        if p is None or p.category != body.slot:
            raise HTTPException(422, "product not found for this slot")
    if body.choice == "owned":
        w = db.get(WardrobeItem, body.wardrobe_item_id) if body.wardrobe_item_id else None
        if w is None or w.user_id != user.id or w.category != body.slot:
            raise HTTPException(422, "wardrobe item not found for this slot")
    if row is None:
        row = TripSelection(trip_id=trip.id, tier=body.tier, slot=body.slot)
        db.add(row)
    row.choice = body.choice
    row.product_id = body.product_id if body.choice == "product" else None
    row.wardrobe_item_id = body.wardrobe_item_id if body.choice == "owned" else None
    db.commit()
    return {"ok": True, "choice": row.choice}


@router.delete("/selections")
def reset_selections(tier: str | None = None, trip: Trip = Depends(own_trip),
                     db: Session = Depends(get_db)):
    q = select(TripSelection).where(TripSelection.trip_id == trip.id)
    if tier:
        q = q.where(TripSelection.tier == _tier(tier))
    for r in db.scalars(q).all():
        db.delete(r)
    db.commit()
    return {"ok": True}
