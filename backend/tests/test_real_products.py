"""Real shop pages: reading a product page, the daily price check, and the seed catalog."""
import json
from datetime import datetime, timedelta, timezone

import httpx

from app.catalog import pagereader
from app.catalog.ingest import SEED_DIR, ingest_rows, seed_products
from app.catalog.feeds import read_feed
from app.catalog.refresh import readable, refresh_prices
from app.models import Product


def _page(price_a="199.95", stock_a="InStock", price_b="149.95", stock_b="OutOfStock",
          rating=True) -> str:
    group = {
        "@context": "https://schema.org/", "@type": "ProductGroup",
        "name": "Patagonia - Nano Puff Jacket - Giacca sintetica",
        "brand": {"@type": "Brand", "name": "Patagonia"},
        "audience": {"@type": "PeopleAudience", "suggestedGender": "https://schema.org/Male"},
        "hasVariant": [
            {"@type": "Product", "sku": "1", "gtin": "0198077142959",
             "image": "https://img.example/nano-black.jpg",
             "offers": {"@type": "Offer", "priceCurrency": "EUR", "price": price_a,
                        "availability": f"https://schema.org/{stock_a}"}},
            {"@type": "Product", "sku": "2",
             "offers": {"@type": "Offer", "priceCurrency": "EUR", "price": price_b,
                        "availability": f"https://schema.org/{stock_b}"}},
        ]}
    single = {"@context": "https://schema.org/", "@type": "Product", "name": group["name"],
              "image": "https://img.example/nano-black.jpg"}
    if rating:
        single["review"] = [{"@type": "Review", "reviewRating": {"ratingValue": v}}
                            for v in (5, 4, 5, 4)]
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": []}
    return "".join(f'<script type="application/ld+json">{json.dumps(b)}</script>'
                   for b in (group, crumbs, single))


def test_page_reader_takes_cheapest_variant_in_stock():
    r = pagereader.parse(_page(), "https://www.bergfreunde.it/x/")
    assert r.ok and r.price == 199.95 and r.currency == "EUR" and r.in_stock
    assert r.brand == "Patagonia" and r.gender == "men"
    assert r.image_url == "https://img.example/nano-black.jpg"
    assert r.rating == 4.5 and r.review_count == 4
    r = pagereader.parse(_page(stock_b="InStock"), "u")
    assert r.price == 149.95


def test_page_reader_out_of_stock_and_no_data():
    r = pagereader.parse(_page(stock_a="OutOfStock"), "u")
    assert not r.ok and r.price is None and not r.in_stock and r.error is None
    r = pagereader.parse("<html>nothing here</html>", "u")
    assert not r.ok and r.error == "no product data on the page"


def test_readable_shops_only():
    assert readable("https://www.bergfreunde.it/patagonia-nano-puff-jacket-giacca-sintetica/")
    assert not readable("https://www.decathlon.it/search?Ntt=MH100")
    assert not readable(None)


def _client(pages: dict[str, tuple[int, str]]) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        code, body = pages.get(str(req.url), (404, ""))
        return httpx.Response(code, text=body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _product(db, ext, url, price=100.0, active=True):
    p = Product(network="awin", external_id=ext, merchant="Bergfreunde", brand="Patagonia",
                name=ext, category="insulation_top", price=price, url=url, source="manual",
                active=active, specs={})
    db.add(p)
    db.commit()
    return p


def test_refresh_updates_price_switches_off_and_back_on(db):
    base = "https://www.bergfreunde.it/test-"
    up = _product(db, "t-up", base + "up/")
    gone = _product(db, "t-gone", base + "gone/")
    sold_out = _product(db, "t-sold", base + "sold/")
    back = _product(db, "t-back", base + "back/", active=False)
    broken = _product(db, "t-broken", base + "broken/")
    client = _client({base + "up/": (200, _page(price_a="179.00")),
                      base + "sold/": (200, _page(stock_a="OutOfStock")),
                      base + "back/": (200, _page()),
                      base + "broken/": (503, "")})
    # only our five products: the seed catalog's real pages are not touched by this test
    ids = {p.id for p in (up, gone, sold_out, back, broken)}
    others = db.query(Product).filter(Product.id.notin_(ids)).all()
    keep = {p.id: p.url for p in others}
    for p in others:
        p.url = "https://elsewhere.example/" + p.id
    db.commit()
    try:
        out = refresh_prices(db, pause=0, client=client)
        for p in (up, gone, sold_out, back, broken):
            db.refresh(p)
        assert up.price == 179.0 and up.active
        assert up.image_url == "https://img.example/nano-black.jpg" and up.checked_at is not None
        assert gone.active is False and sold_out.active is False
        assert back.active is True and back.price == 199.95
        assert broken.active is True and broken.checked_at is None  # a failed read changes nothing
        assert out["off"] == 2 and out["back_on"] == 1 and out["failed"] == 1
        # recently checked products are skipped
        again = refresh_prices(db, older_than=timedelta(hours=20), pause=0, client=client)
        assert again["checked"] == 1  # only the one whose read failed
    finally:
        for p in others:
            p.url = keep[p.id]
        db.commit()
    for p in (up, gone, sold_out, back, broken):
        db.delete(p)
    db.commit()


def test_seed_keeps_fresher_prices_and_rows_when_shop_changes(db):
    url = "https://www.bergfreunde.it/seed-test/"
    row = {"external_id": "seed-test-1", "network": "direct", "merchant": "Old shop",
           "brand": "Rab", "name": "Test Jacket", "category": "shell_top", "price": 100,
           "url": "https://old.example/", "specs": {"clo": 0.1}}
    data = json.dumps({"products": [row]}).encode()
    ingest_rows(db, read_feed(data, "json"), "seed", "t", deactivate_missing=False,
                source="seed")
    p = db.query(Product).filter_by(external_id="seed-test-1").one()
    first_id = p.id
    # the file moves it to a real shop page, checked yesterday
    moved = {**row, "network": "awin", "program_id": "125902", "merchant": "Bergfreunde",
             "url": url, "price": 120, "checked_at": "2026-11-12"}
    ingest_rows(db, read_feed(json.dumps({"products": [moved]}).encode(), "json"), "seed", "t",
                deactivate_missing=False, source="seed")
    db.refresh(p)
    assert p.id == first_id and p.network == "awin" and p.price == 120 and p.url == url
    # the app re-read the page today: a later seed run with the older file keeps today's price
    p.price, p.checked_at = 111, datetime.now(timezone.utc)
    db.commit()
    ingest_rows(db, read_feed(json.dumps({"products": [moved]}).encode(), "json"), "seed", "t",
                deactivate_missing=False, source="seed")
    db.refresh(p)
    assert p.price == 111
    db.delete(p)
    db.commit()


def test_seed_catalog_links_to_real_shops(db):
    data = json.loads((SEED_DIR / "products.json").read_text(encoding="utf-8"))["products"]
    active = [p for p in data if p.get("active", True)]
    checked = [p for p in active if p.get("checked_at")]
    assert len(checked) >= 60
    for p in active:
        assert not p["url"].startswith(("https://www.google.", "https://www.amazon.")), p["name"]
    for p in checked:  # a checked product has a real page, a picture and an affiliate program
        assert readable(p["url"]) and p["image_url"].startswith("https://")
        assert p["network"] == "awin" and p["program_id"]
    for p in data:
        if not p.get("active", True):
            assert p.get("inactive_reason")
    # switched-off products don't reach the kit
    seed_products(db)
    off = {p["external_id"] for p in data if not p.get("active", True)}
    live = {p.external_id for p in db.query(Product).filter_by(source="seed", active=True)}
    assert off and not (off & live)
