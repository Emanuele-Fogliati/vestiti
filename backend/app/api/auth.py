from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import current_user, optional_user, rate_limit
from app.models import AffiliateClick, Trip, User
from app.schemas import LoginIn, ProfileIn, RegisterIn, TripOut, UserOut, WardrobeOut
from app.security import COOKIE_NAME, hash_password, make_token, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


def _set_cookie(resp: Response, user: User):
    s = get_settings()
    resp.set_cookie(COOKIE_NAME, make_token(user.id), max_age=s.session_days * 86400,
                    httponly=True, secure=s.cookie_secure, samesite="lax", path="/")


@router.post("/auth/guest", response_model=UserOut, dependencies=[Depends(rate_limit("auth", "auth_rate_limit_per_minute"))])
def guest(resp: Response, db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    """Start without an account. The guest can later register and keep their trips."""
    if user:
        return user
    user = User(is_guest=True)
    db.add(user)
    db.commit()
    _set_cookie(resp, user)
    return user


@router.post("/auth/register", response_model=UserOut, dependencies=[Depends(rate_limit("auth", "auth_rate_limit_per_minute"))])
def register(body: RegisterIn, resp: Response, db: Session = Depends(get_db),
             user: User | None = Depends(optional_user)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    if user and user.is_guest:
        user.email = email  # upgrade the guest in place: trips and wardrobe are kept
        user.password_hash = hash_password(body.password)
        user.display_name = body.display_name
        user.is_guest = False
    else:
        user = User(email=email, password_hash=hash_password(body.password),
                    display_name=body.display_name)
        db.add(user)
    if email in get_settings().admin_emails:
        user.is_admin = True
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    _set_cookie(resp, user)
    return user


@router.post("/auth/login", response_model=UserOut, dependencies=[Depends(rate_limit("auth", "auth_rate_limit_per_minute"))])
def login(body: LoginIn, resp: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    _set_cookie(resp, user)
    return user


@router.post("/auth/logout", status_code=204)
def logout():
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.commit()
    return user


@router.get("/me/export")
def export_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """GDPR data export: everything we store about the user."""
    trips = db.scalars(select(Trip).where(Trip.user_id == user.id)).all()
    clicks = db.scalars(select(AffiliateClick).where(AffiliateClick.user_id == user.id)).all()
    return {
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "trips": [TripOut.model_validate(t).model_dump(mode="json") for t in trips],
        "wardrobe": [WardrobeOut.model_validate(w).model_dump(mode="json") for w in user.wardrobe],
        "clicks": [{"at": c.created_at.isoformat(), "kind": c.kind, "network": c.network,
                    "product_id": c.product_id, "trip_id": c.trip_id} for c in clicks],
    }


@router.delete("/me", status_code=204)
def delete_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """GDPR erasure: deletes the account, trips and wardrobe. Click rows are kept for
    affiliate reconciliation but lose the link to the user (ON DELETE SET NULL)."""
    db.delete(user)
    db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp
