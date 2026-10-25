from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import User, WardrobeItem
from app.schemas import WardrobeIn, WardrobeOut

router = APIRouter(prefix="/api/wardrobe", tags=["wardrobe"])
MAX_ITEMS = 300


@router.get("", response_model=list[WardrobeOut])
def list_items(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(WardrobeItem).where(WardrobeItem.user_id == user.id)
                      .order_by(WardrobeItem.category, WardrobeItem.created_at)).all()


@router.post("", response_model=WardrobeOut, status_code=201)
def add_item(body: WardrobeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if len(user.wardrobe) >= MAX_ITEMS:
        raise HTTPException(422, f"At most {MAX_ITEMS} wardrobe items")
    item = WardrobeItem(user_id=user.id, **body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _own(item_id: str, user: User, db: Session) -> WardrobeItem:
    item = db.get(WardrobeItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "Item not found")
    return item


@router.put("/{item_id}", response_model=WardrobeOut)
def update_item(item_id: str, body: WardrobeIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    item = _own(item_id, user, db)
    for k, v in body.model_dump().items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own(item_id, user, db))
    db.commit()
