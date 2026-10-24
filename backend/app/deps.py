from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Trip, User
from app.security import COOKIE_NAME, limiter, read_token


def _token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return request.cookies.get(COOKIE_NAME)


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    tok = _token(request)
    if not tok:
        return None
    uid = read_token(tok)
    return db.get(User, uid) if uid else None


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not (user.is_admin or (user.email and user.email in get_settings().admin_emails)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return user


def own_trip(trip_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    return trip


def rate_limit(bucket: str, limit_attr: str):
    def dep(request: Request):
        ip = request.client.host if request.client else "?"
        limit = getattr(get_settings(), limit_attr)
        if not limiter.allow(f"{bucket}:{ip}", limit):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, slow down")
    return dep
