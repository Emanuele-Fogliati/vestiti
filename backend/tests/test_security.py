"""Security audit 2026-10: abuse limits and input checks that keep one visitor from
freezing the server or reaching things they should not."""
import threading
import time

import pytest

from app.catalog.ingest import ingest_rows
from app.config import get_settings
from app.llm import client as llm_client
from app.llm.client import LLMClient, LLMUnavailable
from app.models import Product
from app.security import limiter

from .test_api import guest_with_trip


def test_stop_cannot_be_stretched_over_centuries(client):
    # Before the fix this PATCH was accepted and the next /strategy took 3.5 minutes (8 MB)
    t = guest_with_trip(client)
    sid = t["stops"][0]["id"]
    url = f"/api/trips/{t['id']}/stops/{sid}"
    assert client.patch(url, json={"end_date": "2127-07-01"}).status_code == 422
    assert client.patch(url, json={"end_date": "2028-07-01"}).status_code == 422  # > 120 days
    assert client.patch(url, json={"start_date": "0001-01-01"}).status_code == 422
    assert client.patch(url, json={"end_date": "2027-07-20"}).status_code == 200


def test_new_stops_and_trips_have_bounded_dates(client):
    client.post("/api/auth/guest")
    stop = {"name": "X", "latitude": 0, "longitude": 0, "start_date": "9999-12-25", "end_date": "9999-12-31"}
    assert client.post("/api/trips", json={"name": "far", "stops": [stop]}).status_code == 422
    stop.update(start_date="2027-01-01", end_date="2027-01-02",
                visits=[{"name": "Y", "date": "0001-01-01"}])
    assert client.post("/api/trips", json={"name": "visit", "stops": [stop]}).status_code == 422
    assert client.get("/api/inspire/peru?start=9999-12-31").status_code in (404, 422)


def test_stop_patch_bad_values_are_422_not_500(client):
    t = guest_with_trip(client)
    url = f"/api/trips/{t['id']}/stops/{t['stops'][0]['id']}"
    assert client.patch(url, json={"country_code": "PERU"}).status_code == 422
    assert client.patch(url, json={"country_code": "1<"}).status_code == 422
    assert client.patch(url, json={"name": None}).status_code == 200  # ignored, not a crash
    assert client.patch(url, json={"notes": "x" * 5000}).status_code == 422
    r = client.patch(url, json={"country_code": "it"})
    assert r.status_code == 200 and r.json()["country_code"] == "IT"


def test_reorder_rejects_duplicates(client):
    t = guest_with_trip(client)
    a, b = (s["id"] for s in t["stops"])
    r = client.post(f"/api/trips/{t['id']}/stops/reorder", json={"stop_ids": [a, a, b]})
    assert r.status_code == 422


def test_catalog_paging_is_validated(client):
    assert client.get("/api/catalog/products?limit=-1").status_code == 422
    assert client.get("/api/catalog/products?offset=-5").status_code == 422
    assert client.get("/api/catalog/products?limit=5").status_code == 200


def test_big_bodies_are_refused(client):
    client.post("/api/auth/guest")
    big = '{"name": "' + "x" * 1_100_000 + '"}'
    r = client.post("/api/trips", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413

    def chunks():  # no Content-Length: counted while reading
        for _ in range(12):
            yield b"x" * 100_000
    r = client.post("/api/trips", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_public_config_hides_the_model_server(client):
    for body in (client.get("/api/config").json()["ai"], client.get("/api/ai/status").json()):
        assert "base_url" not in body and "detail" not in body


def test_geocode_is_rate_limited(client):
    s = get_settings()
    old = s.geo_rate_limit_per_minute
    s.geo_rate_limit_per_minute = 3
    limiter._hits.pop("geo:testclient", None)
    try:
        codes = [client.get("/api/geocode?q=Cusco").status_code for _ in range(4)]
    finally:
        s.geo_rate_limit_per_minute = old
        limiter._hits.pop("geo:testclient", None)
    assert codes == [200, 200, 200, 429]


def test_rental_country_cannot_inject_url_parts(client, db):
    from app.models import RentalPartner
    r = db.query(RentalPartner).filter(RentalPartner.url_template.contains("{country}")).first()
    if r is None:
        pytest.skip("no rental partner uses {country}")
    slot = r.categories[0]
    base = f"/api/go/rental/{r.id}?slot={slot}&start=2027-01-01&end=2027-01-05"
    assert client.get(base + "&country=%26x", follow_redirects=False).status_code == 422
    ok = client.get(base + "&country=PE", follow_redirects=False)
    assert ok.status_code == 302 and "country=PE" in ok.headers["location"]


def test_feed_links_must_be_web_urls(db):
    rows = [{"external_id": "js-1", "name": "Evil fleece jacket", "price": 10, "brand": "X",
             "url": "javascript:alert(1)", "_category": "mid_top"},
            {"external_id": "ok-1", "name": "Good fleece jacket", "price": 10, "brand": "X",
             "url": "https://shop.example/fleece", "image_url": "data:text/html,hi",
             "_category": "mid_top"}]
    job = ingest_rows(db, rows, "sec-test", deactivate_missing=False)
    assert job.created == 1 and job.skipped == 1
    p = db.query(Product).filter(Product.network == "sec-test").one()
    assert p.url.startswith("https://") and p.image_url is None


def test_llm_calls_are_capped(monkeypatch):
    """Over the cap a call waits briefly, then fails over to the rule-based fallback."""
    s = get_settings().model_copy(update={"llm_enabled": True, "llm_max_concurrent": 1,
                                          "llm_queue_wait_s": 0.05})
    monkeypatch.setattr(llm_client, "_slots", threading.BoundedSemaphore(1))
    llm_client._slots.acquire()  # someone else is using the model
    try:
        t0 = time.monotonic()
        with pytest.raises(LLMUnavailable, match="busy"):
            LLMClient(s).chat("sys", "hi")
        assert time.monotonic() - t0 < 2
    finally:
        llm_client._slots.release()
