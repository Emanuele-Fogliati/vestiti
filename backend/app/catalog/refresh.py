"""Re-read price, stock and picture of every product whose shop page we are allowed to read.

Only shops in READABLE_HOSTS: they serve their product data to plain requests and are
partners we link to. A product that went out of stock is switched off (the kit picks
something else) and switched back on when it is back. Products that come from an affiliate
feed are left alone: the next feed import is their truth.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import pagereader
from app.models import Product

log = logging.getLogger(__name__)
READABLE_HOSTS = {"www.bergfreunde.it"}


def readable(url: str | None) -> bool:
    return bool(url) and urlparse(url).hostname in READABLE_HOSTS


def refresh_prices(db: Session, older_than: timedelta | None = None, pause: float = 0.7,
                   client: httpx.Client | None = None, limit: int | None = None) -> dict:
    now = datetime.now(timezone.utc)
    rows = [p for p in db.scalars(select(Product).where(Product.source != "feed"))
            if readable(p.url)]
    if older_than is not None:
        cutoff = now - older_than
        rows = [p for p in rows if p.checked_at is None
                or (p.checked_at if p.checked_at.tzinfo else
                    p.checked_at.replace(tzinfo=timezone.utc)) < cutoff]
    if limit:
        rows = rows[:limit]
    out = {"checked": 0, "updated": 0, "off": 0, "back_on": 0, "failed": 0}
    own = client is None
    client = client or httpx.Client(
        headers={"User-Agent": pagereader.UA, "Accept-Language": "it,en;q=0.8"},
        follow_redirects=True, timeout=20)
    try:
        for i, p in enumerate(rows):
            if i and pause:
                time.sleep(pause)  # one page at a time
            r = pagereader.read(p.url, client)
            out["checked"] += 1
            if r.error and r.status not in (404, 410):
                out["failed"] += 1  # network trouble or a changed page: keep what we had
                log.warning("price check failed for %s: %s", p.url, r.error)
                continue
            p.checked_at = now
            if not r.ok:  # gone (404) or nothing in stock
                if p.active:
                    p.active = False
                    out["off"] += 1
                continue
            if not p.active:
                p.active = True
                out["back_on"] += 1
            if abs((p.price or 0) - r.price) >= 0.01 or (r.image_url and p.image_url != r.image_url):
                out["updated"] += 1
            p.price = round(r.price, 2)
            p.currency = r.currency or p.currency
            p.image_url = r.image_url or p.image_url
            if r.rating is not None and r.review_count >= 3:
                p.rating, p.review_count = r.rating, r.review_count
            db.commit()
    finally:
        if own:
            client.close()
    db.commit()
    log.info("price check: %s", out)
    return out
