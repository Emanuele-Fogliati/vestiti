"""Accounts: guest, register, sign in (password or emailed link), password reset,
sign out (this device or everywhere), profile, GDPR export and deletion.

Sessions are a signed cookie (HttpOnly, SameSite=Lax) carrying the user's session_version:
bumping it (sign out everywhere, new password) ends every other session at once.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app import mailer
from app.config import get_settings
from app.db import get_db
from app.deps import current_user, optional_user, rate_limit
from app.models import AffiliateClick, AuthToken, Trip, User, WardrobeItem
from app.schemas import LoginIn, ProfileIn, RegisterIn, TripOut, UserOut, WardrobeOut
from app.security import (
    COOKIE_NAME,
    hash_password,
    limiter,
    link_token_hash,
    make_token,
    new_link_token,
    verify_password,
)

router = APIRouter(prefix="/api", tags=["auth"])
auth_limit = Depends(rate_limit("auth", "auth_rate_limit_per_minute"))

# same answer whether or not the email has an account (no account discovery)
LINK_SENT = "If this email can sign in, a link is on its way. It works once."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _set_cookie(resp: Response, user: User):
    s = get_settings()
    resp.set_cookie(COOKIE_NAME, make_token(user.id, user.session_version or 0),
                    max_age=s.session_days * 86400, httponly=True, secure=s.cookie_secure,
                    samesite="lax", path="/")


def _limit_email(bucket: str, email: str, per_minute: int = 5) -> None:
    """Per-address limit on top of the per-IP one: slows password guessing spread over
    many IPs and stops anyone flooding a stranger's inbox."""
    if not limiter.allow(f"{bucket}:{email}", per_minute):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts for this email, wait a minute")


def merge_guest(db: Session, guest: User | None, into: User) -> int:
    """Signing in from a guest session: the guest's trips and wardrobe move into the
    account (nothing planned before signing in is lost), then the guest is deleted."""
    if guest is None or not guest.is_guest or guest.id == into.id:
        return 0
    moved = 0
    for t in db.scalars(select(Trip).where(Trip.user_id == guest.id)).all():
        t.user_id = into.id
        moved += 1
    for w in db.scalars(select(WardrobeItem).where(WardrobeItem.user_id == guest.id)).all():
        w.user_id = into.id
    db.execute(update(AffiliateClick).where(AffiliateClick.user_id == guest.id).values(user_id=into.id))
    if into.profile_done_at is None and guest.profile_done_at is not None:
        # the quiz answered as a guest is the traveller's own: keep it
        for k in ("thermal_offset", "pace", "evenings", "gender_pref", "profile_done_at"):
            setattr(into, k, getattr(guest, k))
    db.flush()
    db.expire(guest, ["trips", "wardrobe"])
    db.delete(guest)
    return moved


def _signed_in(db: Session, resp: Response, user: User, guest: User | None) -> User:
    merge_guest(db, guest, user)
    user.last_login_at = _now()
    db.commit()
    db.refresh(user)
    _set_cookie(resp, user)
    return user


# ---------------------------------------------------------------- session

@router.get("/session")
def session(user: User | None = Depends(optional_user)):
    """Who is signed in, or null. Unlike GET /me it answers 200 when nobody is."""
    return {"user": UserOut.model_validate(user).model_dump(mode="json") if user else None}


@router.post("/auth/guest", response_model=UserOut, dependencies=[auth_limit])
def guest(resp: Response, db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    """Start without an account. The guest can later register and keep their trips."""
    if user:
        return user
    user = User(is_guest=True)
    db.add(user)
    db.commit()
    _set_cookie(resp, user)
    return user


@router.post("/auth/register", response_model=UserOut, dependencies=[auth_limit])
def register(body: RegisterIn, resp: Response, db: Session = Depends(get_db),
             user: User | None = Depends(optional_user)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists. Sign in instead.")
    if user and user.is_guest:
        user.email = email  # upgrade the guest in place: trips and wardrobe are kept
        user.password_hash = hash_password(body.password)
        user.display_name = body.display_name
        user.is_guest = False
    else:
        user = User(email=email, password_hash=hash_password(body.password),
                    display_name=body.display_name)
        db.add(user)
    # admin rights come only from the CLI (create-admin), never from an unverified email
    user.last_login_at = _now()
    db.commit()
    _set_cookie(resp, user)
    return user


@router.post("/auth/login", response_model=UserOut, dependencies=[auth_limit])
def login(body: LoginIn, resp: Response, db: Session = Depends(get_db),
          current: User | None = Depends(optional_user)):
    email = body.email.lower()
    _limit_email("login", email, max(5, get_settings().auth_rate_limit_per_minute))
    user = db.scalar(select(User).where(User.email == email))
    if not verify_password(body.password, user.password_hash if user else None) or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    return _signed_in(db, resp, user, current)


@router.post("/auth/logout", status_code=204)
def logout():
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@router.post("/auth/logout-everywhere", status_code=204)
def logout_everywhere(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """End every session of this account, on every device (lost phone, shared computer)."""
    user.session_version = (user.session_version or 0) + 1
    db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


# ---------------------------------------------------------------- email links

class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ResetIn(TokenIn):
    password: str = Field(min_length=8, max_length=200)


def _issue(db: Session, purpose: str, email: str, user: User | None, minutes: int) -> str:
    # a new link replaces the older unused ones of the same kind
    for old in db.scalars(select(AuthToken).where(AuthToken.email == email, AuthToken.purpose == purpose,
                                                  AuthToken.used_at.is_(None))).all():
        old.used_at = _now()
    raw, digest = new_link_token()
    db.add(AuthToken(token_hash=digest, purpose=purpose, email=email,
                     user_id=user.id if user else None, expires_at=_now() + timedelta(minutes=minutes)))
    db.commit()
    return raw


def _consume(db: Session, raw: str, purpose: str) -> AuthToken:
    row = db.scalar(select(AuthToken).where(AuthToken.token_hash == link_token_hash(raw),
                                            AuthToken.purpose == purpose))
    if row is None or row.used_at is not None or _aware(row.expires_at) < _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "This link has expired or was already used. Ask for a new one.")
    row.used_at = _now()
    return row


def _link_reply(path: str, raw: str | None) -> dict:
    s = get_settings()
    out = {"detail": LINK_SENT, "email_enabled": s.email_enabled}
    if raw and s.show_dev_links:
        out["dev_link"] = f"{path}?token={raw}"  # local machine without a mail server only
    return out


@router.post("/auth/password/forgot", status_code=202, dependencies=[auth_limit])
def forgot_password(body: EmailIn, db: Session = Depends(get_db)):
    s = get_settings()
    email = body.email.lower()
    _limit_email("mail", email, 3)
    user = db.scalar(select(User).where(User.email == email))
    raw = None
    if user and not user.is_guest:
        raw = _issue(db, "reset", email, user, s.reset_link_minutes)
        link = f"{s.public_base_url.rstrip('/')}/reset-password?token={raw}"
        mailer.send(email, f"Reset your {s.brand_name} password",
                    f"Someone (hopefully you) asked to reset the password of your {s.brand_name} account.\n\n"
                    f"Choose a new password here (the link works once, for {s.reset_link_minutes} minutes):\n"
                    f"{link}\n\nDidn't ask? Ignore this email: your password stays the same.\n")
    return _link_reply("/reset-password", raw)


@router.post("/auth/password/reset", response_model=UserOut, dependencies=[auth_limit])
def reset_password(body: ResetIn, resp: Response, db: Session = Depends(get_db),
                   current: User | None = Depends(optional_user)):
    row = _consume(db, body.token, "reset")
    user = db.get(User, row.user_id) if row.user_id else None
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This link has expired or was already used. Ask for a new one.")
    user.password_hash = hash_password(body.password)
    user.session_version = (user.session_version or 0) + 1  # every old session ends
    return _signed_in(db, resp, user, current)


@router.post("/auth/email-link", status_code=202, dependencies=[auth_limit])
def email_link(body: EmailIn, db: Session = Depends(get_db)):
    """Sign in without a password: we email a one-use link. A new email gets an account
    when the link is opened (so the address is proven before the account exists)."""
    s = get_settings()
    email = body.email.lower()
    _limit_email("mail", email, 3)
    user = db.scalar(select(User).where(User.email == email))
    raw = _issue(db, "login", email, user, s.login_link_minutes)
    link = f"{s.public_base_url.rstrip('/')}/sign-in-link?token={raw}"
    mailer.send(email, f"Your {s.brand_name} sign-in link",
                f"Open this link to sign in to {s.brand_name} (it works once, for {s.login_link_minutes} minutes):\n"
                f"{link}\n\nDidn't ask? Ignore this email: nobody can sign in without the link.\n")
    return _link_reply("/sign-in-link", raw)


@router.post("/auth/email-link/verify", response_model=UserOut, dependencies=[auth_limit])
def email_link_verify(body: TokenIn, resp: Response, db: Session = Depends(get_db),
                      current: User | None = Depends(optional_user)):
    row = _consume(db, body.token, "login")
    user = db.scalar(select(User).where(User.email == row.email))
    if user is None:
        if current and current.is_guest:
            user, current = current, None  # the guest becomes the account: nothing to move
            user.email, user.is_guest = row.email, False
        else:
            user = User(email=row.email)
            db.add(user)
            db.flush()
    return _signed_in(db, resp, user, current)


# ---------------------------------------------------------------- the signed-in user

class PasswordIn(BaseModel):
    current_password: str | None = Field(default=None, max_length=200)  # none yet: link-only account
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/me/password", response_model=UserOut, dependencies=[auth_limit])
def change_password(body: PasswordIn, resp: Response, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    if user.is_guest:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Create an account first")
    if user.password_hash and not verify_password(body.current_password or "", user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is not right")
    user.password_hash = hash_password(body.new_password)
    user.session_version = (user.session_version or 0) + 1  # other devices are signed out
    db.commit()
    _set_cookie(resp, user)  # this device stays signed in
    return user


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
    if user.email:
        db.execute(delete(AuthToken).where(AuthToken.email == user.email))
    db.delete(user)
    db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp

