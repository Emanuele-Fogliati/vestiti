"""End-to-end API flow on SQLite. Weather uses the offline estimate (no network)."""
from fastapi.testclient import TestClient

from app.main import app

TRIP = {"name": "Alps + Rome", "stops": [
    {"name": "Chamonix", "country_code": "FR", "latitude": 45.92, "longitude": 6.87, "elevation_m": 1035,
     "start_date": "2027-07-10", "end_date": "2027-07-13",
     "activities": [{"type": "hiking", "difficulty": "hard", "max_altitude_m": 2600}, {"type": "city"}]},
    {"name": "Rome", "country_code": "IT", "latitude": 41.9, "longitude": 12.5, "elevation_m": 20,
     "start_date": "2027-07-14", "end_date": "2027-07-16"},
]}


def guest_with_trip(client):
    assert client.post("/api/auth/guest").status_code == 200
    r = client.post("/api/trips", json=TRIP)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_and_config(client):
    assert client.get("/api/health").json()["ok"] is True
    cfg = client.get("/api/config").json()
    assert cfg["brand"]["name"] == "Thruwear" and cfg["brand"]["tagline"] == "Wear it thru." and cfg["disclosure"] and len(cfg["slots"]) == 12


def test_csrf_header_required():
    with TestClient(app) as raw:
        assert raw.post("/api/auth/guest").status_code == 403


def test_full_trip_flow(client):
    trip = guest_with_trip(client)
    tid = trip["id"]
    assert [s["name"] for s in trip["stops"]] == ["Chamonix", "Rome"]

    w = client.get(f"/api/trips/{tid}/weather").json()
    assert w["stops"][0]["days"] and w["stops"][0]["days"][0]["source"] == "estimate"

    plans = client.get(f"/api/trips/{tid}/plans").json()
    tiers = plans["tiers"]
    assert tiers["cheap"]["totals"]["total"] < tiers["medium"]["totals"]["total"] < tiers["premium"]["totals"]["total"]
    for t in tiers.values():
        assert t["warmth"]["status"] in ("covered", "marginal")

    st = client.get(f"/api/trips/{tid}/strategy?tier=medium").json()
    assert len(st["stages"]) == 2 and st["model_note"]

    prods = client.get(f"/api/trips/{tid}/slots/shell_top/products?sort=price_asc").json()
    items = prods["items"] if isinstance(prods, dict) else prods
    prices = [p["price"] for p in items]
    assert prices == sorted(prices) and len(prices) > 3

    # swap the medium shell for the cheapest one, then reset
    pick = items[0]["id"]
    assert client.put(f"/api/trips/{tid}/selections", json={"tier": "medium", "slot": "shell_top",
                                                             "choice": "product", "product_id": pick}).status_code == 200
    again = client.get(f"/api/trips/{tid}/plans").json()["tiers"]["medium"]
    shell = next(i for i in again["items"] if i["slot"] == "shell_top")
    assert shell["item"]["id"] == pick
    assert client.delete(f"/api/trips/{tid}/selections").status_code in (200, 204)

    # outbound click: redirect to the shop URL stored in the DB, and the click is logged
    r = client.get(f"/api/go/product/{pick}?trip_id={tid}&tier=medium&slot=shell_top", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://")


def test_owned_items_are_reused(client):
    tid = guest_with_trip(client)["id"]
    before = client.get(f"/api/trips/{tid}/plans").json()["tiers"]["cheap"]["totals"]["total"]
    r = client.post("/api/wardrobe", json={"category": "shell_top", "name": "Old rain jacket", "warmth": "medium",
                                           "waterproof": True, "windproof": True})
    assert r.status_code in (200, 201), r.text
    after = client.get(f"/api/trips/{tid}/plans").json()["tiers"]
    assert after["cheap"]["totals"]["items_owned"] >= 1
    assert after["cheap"]["totals"]["total"] < before


def test_stops_edit_add_remove(client):
    trip = guest_with_trip(client)
    tid, first = trip["id"], trip["stops"][0]["id"]
    r = client.post(f"/api/trips/{tid}/stops", json={"name": "Florence", "latitude": 43.77, "longitude": 11.25,
                                                      "start_date": "2027-07-17", "end_date": "2027-07-18"})
    assert r.status_code == 201
    assert client.patch(f"/api/trips/{tid}/stops/{first}", json={"elevation_m": 1200}).status_code == 200
    assert client.delete(f"/api/trips/{tid}/stops/{first}").status_code == 204
    names = [s["name"] for s in client.get(f"/api/trips/{tid}").json()["stops"]]
    assert names == ["Rome", "Florence"]


def test_trips_are_private(client):
    tid = guest_with_trip(client)["id"]
    with TestClient(app) as other:
        other.headers.update({"X-Requested-With": "app"})
        other.post("/api/auth/guest")
        assert other.get(f"/api/trips/{tid}").status_code == 404
        assert other.get(f"/api/trips/{tid}/plans").status_code == 404


def test_guest_upgrade_login_export_delete(client):
    tid = guest_with_trip(client)["id"]
    r = client.post("/api/auth/register", json={"email": "ana@example.com", "password": "correct horse 1"})
    assert r.status_code == 200 and r.json()["is_guest"] is False
    assert client.get(f"/api/trips/{tid}").status_code == 200  # guest trips moved over
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "ana@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ana@example.com", "password": "correct horse 1"}).status_code == 200
    data = client.get("/api/me/export").json()
    assert data["trips"]
    assert client.delete("/api/me").status_code == 204
    assert client.post("/api/auth/login", json={"email": "ana@example.com", "password": "correct horse 1"}).status_code == 401


def test_admin_only(client, db):
    client.post("/api/auth/guest")
    assert client.get("/api/admin/stats").status_code == 403
    # registering with an admin-looking email gives no rights: only the CLI flag does
    u = client.post("/api/auth/register", json={"email": "admin@example.com", "password": "admin-pass-123"}).json()
    assert u["is_admin"] is False and client.get("/api/admin/stats").status_code == 403
    from app.models import User
    db.get(User, u["id"]).is_admin = True
    db.commit()
    s = client.get("/api/admin/stats")
    assert s.status_code == 200 and s.json()["products_active"] > 100


def test_parse_itinerary_endpoint(client):
    client.post("/api/auth/guest")
    r = client.post("/api/ai/parse-itinerary", json={"text": "From 3 May 2027: 2 days in Rome, then 3 days hiking in Chamonix"})
    assert r.status_code == 200
    d = r.json()
    assert [s["name"] for s in d["stops"]] == ["Rome", "Chamonix"]


def test_parse_itinerary_accepts_long_text_up_to_50k(client):
    client.post("/api/auth/guest")
    long = "From 3 May 2027: 2 days in Rome. " + "Free afternoon walking around the old town. " * 1000
    assert 40_000 < len(long) <= 50_000
    assert client.post("/api/ai/parse-itinerary", json={"text": long}).status_code == 200
    r = client.post("/api/ai/parse-itinerary", json={"text": "x" * 50_001})
    assert r.status_code == 422
