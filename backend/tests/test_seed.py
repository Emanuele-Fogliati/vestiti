"""Re-seeding an existing database: rows removed from the seed file are switched off."""
from sqlalchemy import select

from app.catalog.ingest import seed_products
from app.models import Product


def test_products_removed_from_the_seed_are_deactivated(db):
    ghost = Product(network="direct", external_id="seed-old-ski-jacket", name="Old Ski Jacket (Men)",
                    brand="Decathlon", merchant="Decathlon (direct)", category="shell_top",
                    gender="men", price=80.0, currency="EUR", url="https://example.com",
                    specs={"clo": 0.5}, active=True, source="seed")
    db.add(ghost)
    db.commit()
    job = seed_products(db)
    db.refresh(ghost)
    assert ghost.active is False and job.deactivated >= 1
    assert db.scalar(select(Product).where(Product.external_id.like("seed-decathlon-wedze-bl-900%"),
                                           Product.active.is_(True))) is not None
