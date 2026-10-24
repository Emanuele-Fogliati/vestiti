import gzip

from app.catalog.classify import classify, extract_specs, gender_of
from app.catalog.feeds import read_feed
from app.catalog.ingest import ingest_bytes
from app.models import Product


def test_classify():
    assert classify("Arc'teryx Beta AR Gore-Tex Pro Jacket") == "shell_top"
    assert classify("Rab Microlight Alpine Down Jacket") == "insulation_top"
    assert classify("Smartwool Merino 250 Base Layer Crew") == "base_top"
    assert classify("Salomon X Ultra 4 GTX hiking shoe") == "footwear"
    assert classify("Osprey backpack 30L") is None
    assert classify("Kids rain jacket") is None


def test_specs_and_gender():
    s = extract_specs("shell_top", "20,000mm waterproof 15000 g/m2 breathable 395 g")
    assert s["waterproof_mm"] == 20000 and s["breathability_g"] == 15000 and s["weight_g"] == 395
    assert "clo" in s["estimated"]
    assert gender_of("Women's Nano Puff") == "women"
    assert gender_of("Nano Puff", "Mens") == "men"


AWIN = (
    "aw_product_id,product_name,brand_name,merchant_name,merchant_id,search_price,currency,merchant_deep_link,"
    "merchant_category,description\n"
    "A1,Beta AR Gore-Tex Pro Jacket Men's,Arc'teryx,Shop X,123,650,EUR,https://shop.example/beta,Jackets,3L 28000mm\n"
    "A2,Trail Sock Merino,Darn Tough,Shop X,123,25,EUR,https://shop.example/sock,Socks,merino\n"
    "A3,Camping Tent 2P,MSR,Shop X,123,400,EUR,https://shop.example/tent,Tents,\n"
)


def test_awin_feed_import_upserts_and_deactivates(db):
    rows = list(read_feed(AWIN.encode(), "awin"))
    assert rows[0]["external_id"] == "A1" and rows[0]["price"] == 650

    job = ingest_bytes(db, gzip.compress(AWIN.encode()), "awin", "feed.csv.gz")
    assert job.created == 2 and job.skipped == 1
    p = db.query(Product).filter_by(network="awin", external_id="A1").one()
    assert p.category == "shell_top" and p.gender == "men" and p.program_id == "123"

    cheaper = AWIN.replace(",650,", ",599,").replace("A2,Trail Sock", "A9,Trail Sock")
    job2 = ingest_bytes(db, cheaper.encode(), "awin", "feed2.csv")
    assert job2.updated == 1 and job2.created == 1 and job2.deactivated == 1
    db.refresh(p)
    assert p.price == 599
    assert db.query(Product).filter_by(network="awin", external_id="A2").one().active is False
