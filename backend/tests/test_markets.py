"""Two shop markets: US (USD, evo + Decathlon US) and Europe (EUR, Bergfreunde + Decathlon IT).
A user's kit only uses products of their market, and money reads in its currency."""
import json

from app.affiliates.networks import FlexOffers, program_id_for
from app.catalog.ingest import SEED_DIR
from app.catalog.refresh import readable
from app.config import Settings

from tests.test_peru_kit import _plans


def _kit_items(plans):
    return [i["item"] for tp in plans["tiers"].values() for i in tp["items"]
            if i["item"] and i["kind"] == "product"]


def test_us_user_gets_us_products_in_dollars(client, db):
    from app.models import Product
    client.post("/api/auth/guest")
    assert client.patch("/api/me", json={"market": "us"}).json()["market"] == "us"
    plans = _plans(client)
    items = _kit_items(plans)
    assert items
    us = {p.id for p in db.query(Product).filter_by(market="us")}
    assert all(i["id"] in us for i in items)
    assert all(i["currency"] == "USD" for i in items)
    reasons = [u["reason"] for tp in plans["tiers"].values() for u in tp["auto_upgrades"]]
    assert all("€" not in r for r in reasons)


def test_eu_user_keeps_eu_products(client, db):
    from app.models import Product
    client.post("/api/auth/guest")
    client.patch("/api/me", json={"market": "eu"})
    eu = {p.id for p in db.query(Product).filter_by(market="eu")}
    assert all(i["id"] in eu for i in _kit_items(_plans(client)))


def test_market_must_be_known(client):
    client.post("/api/auth/guest")
    assert client.patch("/api/me", json={"market": "xx"}).status_code == 422


def test_flexoffers_link_and_merchant_program_ids():
    s = Settings(flexoffers_link_template="https://track.flexlinks.com/a.ashx?foid=1&fot=9999"
                 "&foc=1&fobs={click}&url={url}",
                 merchant_program_ids="evo=12345; Decathlon US=678")
    out = FlexOffers(s).build("https://www.decathlon.com/products/x?a=1", "c1")
    assert out.tracked and "fobs=c1" in out.url
    assert "url=https%3A%2F%2Fwww.decathlon.com%2Fproducts%2Fx%3Fa%3D1" in out.url
    assert not FlexOffers(Settings()).build("https://x/", "c").tracked
    assert program_id_for("evo", None, s) == "12345"
    assert program_id_for("decathlon us", None, s) == "678"
    assert program_id_for("evo", "999", s) == "999"
    assert program_id_for("REI", None, s) is None


def test_us_seed_catalog_is_real_and_in_dollars():
    data = json.loads((SEED_DIR / "products_us.json").read_text(encoding="utf-8"))["products"]
    assert len(data) >= 80
    ids = [p["external_id"] for p in data]
    assert len(ids) == len(set(ids))
    brands = {p["brand"] for p in data if p.get("active", True)}
    assert {"The North Face", "Patagonia"} <= brands
    for p in data:
        assert p["market"] == "us" and p["currency"] == "USD", p["name"]
        assert readable(p["url"]) and p["checked_at"], p["name"]
        assert p["specs"], p["name"]  # warmth/waterproofing come from our own estimates
        if p.get("active", True):
            assert p["price"] > 0 and p["image_url"].startswith("https://"), p["name"]
        else:
            assert p["inactive_reason"], p["name"]
