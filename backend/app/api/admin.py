from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.affiliates.networks import status as affiliate_status
from app.catalog.feeds import MAPPINGS
from app.catalog.ingest import ingest_bytes, seed_all
from app.config import get_settings
from app.db import get_db
from app.deps import admin_user
from app.llm.client import LLMClient
from app.models import AffiliateClick, FeedImport, Product, Trip, User

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_user)])
MAX_FEED_BYTES = 200 * 1024 * 1024


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=30)
    clicks = db.execute(select(AffiliateClick.network, AffiliateClick.kind, AffiliateClick.tracked,
                               func.count()).group_by(AffiliateClick.network, AffiliateClick.kind,
                                                      AffiliateClick.tracked)).all()
    top = db.execute(select(Product.brand, Product.name, func.count(AffiliateClick.id))
                     .join(AffiliateClick, AffiliateClick.product_id == Product.id)
                     .where(AffiliateClick.created_at >= since)
                     .group_by(Product.id, Product.brand, Product.name)
                     .order_by(func.count(AffiliateClick.id).desc()).limit(10)).all()
    return {
        "users": db.scalar(select(func.count()).select_from(User).where(User.is_guest.is_(False))),
        "guests": db.scalar(select(func.count()).select_from(User).where(User.is_guest.is_(True))),
        "trips": db.scalar(select(func.count()).select_from(Trip)),
        "products_active": db.scalar(select(func.count()).select_from(Product).where(Product.active.is_(True))),
        "clicks_30d": db.scalar(select(func.count()).select_from(AffiliateClick).where(AffiliateClick.created_at >= since)),
        "clicks_by_network": [{"network": n, "kind": k, "tracked": t, "count": c} for n, k, t, c in clicks],
        "top_products_30d": [{"brand": b, "name": n, "clicks": c} for b, n, c in top],
        "affiliates": affiliate_status(get_settings()),
        "ai": LLMClient().status(),  # server address and model list: admins only
    }


@router.get("/feeds")
def feeds(db: Session = Depends(get_db)):
    rows = db.scalars(select(FeedImport).order_by(FeedImport.started_at.desc()).limit(50)).all()
    return {"networks": sorted(MAPPINGS) + ["json"],
            "imports": [{"id": r.id, "network": r.network, "filename": r.filename,
                         "started_at": r.started_at, "status": r.status, "rows": r.rows,
                         "created": r.created, "updated": r.updated, "skipped": r.skipped,
                         "deactivated": r.deactivated, "errors": r.errors[:10]} for r in rows]}


@router.post("/feeds/import")
async def import_feed(network: str = Form(...), file: UploadFile = File(...),
                      deactivate_missing: bool = Form(True), db: Session = Depends(get_db)):
    if network not in MAPPINGS and network != "json":
        raise HTTPException(422, f"network must be one of {sorted(MAPPINGS)} or json")
    raw = await file.read(MAX_FEED_BYTES + 1)
    if len(raw) > MAX_FEED_BYTES:
        raise HTTPException(413, "Feed too large (200 MB max); use the CLI for bigger files")
    job = ingest_bytes(db, raw, network, file.filename or "upload", deactivate_missing)
    return {"id": job.id, "rows": job.rows, "created": job.created, "updated": job.updated,
            "skipped": job.skipped, "deactivated": job.deactivated, "errors": job.errors[:20]}


@router.post("/seed")
def reseed(db: Session = Depends(get_db)):
    return seed_all(db)
