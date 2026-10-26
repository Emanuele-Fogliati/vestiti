"""Upsert affiliate feed rows into the products table."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.classify import classify, extract_specs, gender_of
from app.catalog.feeds import read_feed
from app.engine.garments import SLOT_KEYS
from app.models import FeedImport, Product, RentalPartner

log = logging.getLogger(__name__)
SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
OUT_OF_STOCK = {"0", "false", "no", "out of stock", "outofstock", "out_of_stock"}


def _web_url(u) -> bool:
    return isinstance(u, str) and u.lower().startswith(("https://", "http://")) and len(u) < 4000


def ingest_rows(db: Session, rows, network: str, filename: str = "upload",
                deactivate_missing: bool = True, source: str = "feed") -> FeedImport:
    job = FeedImport(network=network, filename=filename, errors=[])
    db.add(job)
    db.flush()
    seen: set[str] = set()
    merchants: set[str] = set()
    errors: list[str] = []
    for i, r in enumerate(rows):
        job.rows += 1
        try:
            ext = r.get("external_id")
            name = r.get("name")
            price = r.get("price")
            url = r.get("url")
            if not (ext and name and url) or price is None or price <= 0:
                job.skipped += 1
                continue
            if not _web_url(url):
                # the Buy button redirects here: only plain web links (no javascript:, data:...)
                job.skipped += 1
                continue
            ext = str(ext)[:200]
            if str(r.get("in_stock") or "1").strip().lower() in OUT_OF_STOCK:
                job.skipped += 1
                continue
            text = " ".join(filter(None, [name, r.get("category_text"), r.get("description")]))
            slot = r.get("_category") or classify(f"{name} {r.get('category_text') or ''}")
            if slot not in SLOT_KEYS:
                job.skipped += 1
                continue
            specs = r.get("_specs") or extract_specs(slot, text)
            row_network = r.get("_network") or network
            seen.add(ext)
            merchants.add(r.get("merchant") or "")
            p = db.scalar(select(Product).where(Product.network == row_network,
                                                Product.external_id == ext))
            fields = dict(
                name=name[:300], brand=(r.get("brand") or "Unknown")[:120],
                merchant=(r.get("merchant") or row_network)[:120], program_id=(str(r["program_id"])[:80] if r.get("program_id") else None),
                category=slot, gender=r.get("gender") if r.get("gender") in ("men", "women", "unisex")
                else gender_of(name, r.get("gender")), price=float(price),
                currency=(r.get("currency") or "EUR")[:3].upper(), url=url,
                image_url=r.get("image_url") if _web_url(r.get("image_url")) else None, specs=specs, rating=r.get("rating"),
                review_count=int(r.get("review_count") or 0), active=True, source=source,
            )
            if p is None:
                db.add(Product(network=row_network, external_id=ext, **fields))
                job.created += 1
            else:
                for k, v in fields.items():
                    setattr(p, k, v)
                job.updated += 1
        except Exception as e:  # one bad row must not kill the import
            job.skipped += 1
            if len(errors) < 50:
                errors.append(f"row {i + 1}: {e}")
    if deactivate_missing and seen:
        stale = db.scalars(select(Product).where(
            Product.network == network, Product.source == source, Product.active.is_(True),
            Product.merchant.in_(merchants))).all()
        for p in stale:
            if p.external_id not in seen:
                p.active = False
                job.deactivated += 1
    job.errors = errors
    job.status = "done"
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    log.info("feed import %s: %s created, %s updated, %s skipped, %s deactivated",
             filename, job.created, job.updated, job.skipped, job.deactivated)
    return job


def ingest_bytes(db: Session, raw: bytes, network: str, filename: str,
                 deactivate_missing: bool = True) -> FeedImport:
    return ingest_rows(db, read_feed(raw, network), network, filename, deactivate_missing)


def seed_products(db: Session) -> FeedImport:
    raw = (SEED_DIR / "products.json").read_bytes()
    rows = list(read_feed(raw, "json"))
    job = ingest_rows(db, rows, "seed", "seed/products.json", deactivate_missing=False,
                      source="seed")
    # a product taken out of the seed file must not keep being picked from an old database
    keep = {r.get("external_id") for r in rows}
    stale = [p for p in db.scalars(select(Product).where(Product.source == "seed",
                                                         Product.active.is_(True)))
             if p.external_id not in keep]
    for p in stale:
        p.active = False
    if stale:
        job.deactivated += len(stale)
        db.commit()
        log.info("seed: %s products no longer in the seed file deactivated", len(stale))
    return job


def seed_rental_partners(db: Session) -> int:
    data = json.loads((SEED_DIR / "rental_partners.json").read_text(encoding="utf-8"))
    n = 0
    for p in data["partners"]:
        row = db.scalar(select(RentalPartner).where(RentalPartner.slug == p["slug"]))
        if row is None:
            row = RentalPartner(slug=p["slug"])
            db.add(row)
            n += 1
        row.name = p["name"]
        row.url_template = p["url_template"]
        row.network = p.get("network", "direct")
        row.countries = p["countries"]
        row.categories = p["categories"]
        row.daily_rates = p["daily_rates"]
        row.min_days = p.get("min_days", 1)
        row.currency = p.get("currency", "EUR")
        row.is_placeholder = True
        row.active = True
    db.commit()
    return n


def seed_all(db: Session) -> dict:
    job = seed_products(db)
    partners = seed_rental_partners(db)
    return {"products_created": job.created, "products_updated": job.updated,
            "rental_partners_created": partners}
