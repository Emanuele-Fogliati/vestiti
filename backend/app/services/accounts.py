"""Account housekeeping."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import AuthToken, Trip, User


def prune_guests(db: Session, days: int = 30) -> int:
    """Delete guest users with no trips whose last activity is older than `days`.
    Guests with a trip are kept: someone planned something and may come back to it."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = select(User).where(User.is_guest.is_(True), User.created_at < cutoff,
                           ~exists().where(Trip.user_id == User.id))
    n = 0
    for u in db.scalars(q).all():
        db.delete(u)
        n += 1
    # spent or expired email links are of no use to anyone
    for t in db.scalars(select(AuthToken).where(AuthToken.expires_at < cutoff)).all():
        db.delete(t)
    db.commit()
    return n
