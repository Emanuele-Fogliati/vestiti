"""Accounts: sessions end for real, password reset and sign-in links, guest trips survive
signing in, and nothing tells a stranger which emails have an account."""
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app import mailer
from app.config import get_settings
from app.main import app
from tests.conftest import H
from tests.test_api import guest_with_trip


import pytest


def _new_client(base_url: str = "http://localhost") -> TestClient:
    c = TestClient(app, base_url=base_url)
    c.headers.update(H)
    return c


@pytest.fixture()
def client():
    # requests addressed to localhost, like a local Docker run (dev links need it)
    with _new_client() as c:
        yield c


def _register(client, email, pw="correct horse 1"):
    r = client.post("/api/auth/register", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def _token(reply: dict) -> str:
    return parse_qs(urlparse(reply["dev_link"]).query)["token"][0]


def test_session_endpoint_answers_200_when_signed_out(client):
    assert client.get("/api/session").json() == {"user": None}
    client.post("/api/auth/guest")
    assert client.get("/api/session").json()["user"]["is_guest"] is True


def test_logout_everywhere_kills_other_devices(client):
    _register(client, "everywhere@example.com")
    other = _new_client()
    assert other.post("/api/auth/login", json={"email": "everywhere@example.com", "password": "correct horse 1"}).status_code == 200
    assert other.get("/api/me").status_code == 200
    assert client.post("/api/auth/logout-everywhere").status_code == 204
    assert other.get("/api/me").status_code == 401  # the stolen/old cookie no longer works
    assert client.get("/api/me").status_code == 401


def test_old_cookie_is_dead_after_logout_everywhere(client):
    _register(client, "cookie@example.com")
    stolen = client.cookies.get("session")
    client.post("/api/auth/logout-everywhere")
    thief = _new_client()
    thief.cookies.set("session", stolen)
    assert thief.get("/api/me").status_code == 401


def test_login_from_guest_keeps_the_guest_trips(client):
    _register(client, "keeper@example.com")
    client.post("/api/auth/logout")
    trip_id = guest_with_trip(client)["id"]  # planned as a guest, then signs in
    r = client.post("/api/auth/login", json={"email": "keeper@example.com", "password": "correct horse 1"})
    assert r.status_code == 200 and r.json()["is_guest"] is False
    ids = [t["id"] for t in client.get("/api/trips").json()]
    assert trip_id in ids


def test_guest_quiz_answers_follow_into_the_account(client):
    _register(client, "quiz@example.com")
    client.post("/api/auth/logout")
    client.post("/api/auth/guest")
    assert client.post("/api/me/quiz", json={"cold": "very_cold", "pace": "brisk", "evenings": "late"}).status_code == 200
    me = client.post("/api/auth/login", json={"email": "quiz@example.com", "password": "correct horse 1"}).json()
    assert me["pace"] == "brisk" and me["evenings"] == "late" and me["profile_done_at"]


def test_wrong_email_and_wrong_password_look_the_same(client):
    _register(client, "same@example.com")
    client.post("/api/auth/logout")
    a = client.post("/api/auth/login", json={"email": "same@example.com", "password": "nope-nope"})
    b = client.post("/api/auth/login", json={"email": "nobody-here@example.com", "password": "nope-nope"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_huge_password_is_refused_before_hashing(client):
    r = client.post("/api/auth/login", json={"email": "x@example.com", "password": "a" * 10_000})
    assert r.status_code == 422


def test_password_reset_flow(client):
    _register(client, "reset@example.com", "old password 1")
    other = _new_client()
    other.post("/api/auth/login", json={"email": "reset@example.com", "password": "old password 1"})
    client.post("/api/auth/logout")
    r = client.post("/api/auth/password/forgot", json={"email": "reset@example.com"})
    assert r.status_code == 202 and "dev_link" in r.json()
    assert "reset-password?token=" in mailer.OUTBOX[-1].get_content()
    tok = _token(r.json())
    assert client.post("/api/auth/password/reset", json={"token": tok, "password": "short"}).status_code == 422
    r = client.post("/api/auth/password/reset", json={"token": tok, "password": "new password 2"})
    assert r.status_code == 200 and r.json()["email"] == "reset@example.com"
    assert client.get("/api/me").status_code == 200  # signed in by the reset
    assert other.get("/api/me").status_code == 401  # every older session ended
    # the link works once
    assert client.post("/api/auth/password/reset", json={"token": tok, "password": "another one 3"}).status_code == 400
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "reset@example.com", "password": "old password 1"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "reset@example.com", "password": "new password 2"}).status_code == 200


def test_forgot_password_does_not_reveal_accounts(client):
    a = client.post("/api/auth/password/forgot", json={"email": "ghost@example.com"})
    assert a.status_code == 202 and a.json()["detail"]
    assert "dev_link" not in a.json()  # nothing to reset, and the reply text is the same
    _register(client, "real@example.com")
    b = client.post("/api/auth/password/forgot", json={"email": "real@example.com"})
    assert a.json()["detail"] == b.json()["detail"]


def test_new_reset_link_replaces_the_old_one(client):
    _register(client, "twice@example.com")
    first = _token(client.post("/api/auth/password/forgot", json={"email": "twice@example.com"}).json())
    second = _token(client.post("/api/auth/password/forgot", json={"email": "twice@example.com"}).json())
    assert client.post("/api/auth/password/reset", json={"token": first, "password": "first try 11"}).status_code == 400
    assert client.post("/api/auth/password/reset", json={"token": second, "password": "second try 22"}).status_code == 200


def test_expired_link_is_refused(client, db):
    from datetime import datetime, timedelta, timezone

    from app.models import AuthToken
    from app.security import link_token_hash
    _register(client, "late@example.com")
    tok = _token(client.post("/api/auth/password/forgot", json={"email": "late@example.com"}).json())
    row = db.query(AuthToken).filter_by(token_hash=link_token_hash(tok)).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.post("/api/auth/password/reset", json={"token": tok, "password": "too late 123"}).status_code == 400


def test_email_link_signs_in_and_creates_account(client):
    trip_id = guest_with_trip(client)["id"]
    r = client.post("/api/auth/email-link", json={"email": "Linky@Example.com"})
    assert r.status_code == 202
    me = client.post("/api/auth/email-link/verify", json={"token": _token(r.json())}).json()
    assert me["email"] == "linky@example.com" and me["is_guest"] is False
    assert trip_id in [t["id"] for t in client.get("/api/trips").json()]  # the guest became the account
    # a link-only account can set a password without knowing an old one
    assert client.post("/api/me/password", json={"new_password": "now with pw 1"}).status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "linky@example.com", "password": "now with pw 1"}).status_code == 200


def test_email_link_for_existing_account(client):
    _register(client, "existing@example.com")
    client.post("/api/auth/logout")
    r = client.post("/api/auth/email-link", json={"email": "existing@example.com"})
    tok = _token(r.json())
    assert client.post("/api/auth/email-link/verify", json={"token": tok}).json()["email"] == "existing@example.com"
    assert client.post("/api/auth/email-link/verify", json={"token": tok}).status_code == 400  # once
    assert client.post("/api/auth/password/reset", json={"token": tok, "password": "wrong kind 1"}).status_code == 400


def test_change_password(client):
    _register(client, "change@example.com", "first pass 1")
    other = _new_client()
    other.post("/api/auth/login", json={"email": "change@example.com", "password": "first pass 1"})
    bad = client.post("/api/me/password", json={"current_password": "wrong", "new_password": "second pass 2"})
    assert bad.status_code == 400
    ok = client.post("/api/me/password", json={"current_password": "first pass 1", "new_password": "second pass 2"})
    assert ok.status_code == 200
    assert client.get("/api/me").status_code == 200  # this device stays in
    assert other.get("/api/me").status_code == 401  # the others are out


def test_guest_cannot_set_password(client):
    client.post("/api/auth/guest")
    assert client.post("/api/me/password", json={"new_password": "whatever 123"}).status_code == 400


def test_no_dev_links_on_a_public_address(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "dev_email_links", False)
    assert s.show_dev_links is False  # off unless asked for
    monkeypatch.setattr(s, "dev_email_links", True)
    monkeypatch.setattr(s, "public_base_url", "https://thruwear.com")
    assert s.show_dev_links is False
    monkeypatch.setattr(s, "public_base_url", "http://localhost:8000")
    monkeypatch.setattr(s, "environment", "production")
    assert s.show_dev_links is False
    monkeypatch.setattr(s, "environment", "development")
    monkeypatch.setattr(s, "smtp_host", "smtp.example.com")
    assert s.show_dev_links is False  # real email: never on screen


def test_delete_account_removes_links(client, db):
    from app.models import AuthToken
    _register(client, "gone@example.com")
    client.post("/api/auth/password/forgot", json={"email": "gone@example.com"})
    assert client.delete("/api/me").status_code == 204
    assert db.query(AuthToken).filter_by(email="gone@example.com").count() == 0


def test_prune_guests(db):
    from datetime import datetime, timedelta, timezone

    from app.models import Trip, User
    from app.services.accounts import prune_guests
    old = datetime.now(timezone.utc) - timedelta(days=60)
    idle = User(is_guest=True, created_at=old)
    planner = User(is_guest=True, created_at=old)
    db.add_all([idle, planner])
    db.flush()
    db.add(Trip(user_id=planner.id, name="kept"))
    db.commit()
    prune_guests(db, 30)
    assert db.get(User, idle.id) is None and db.get(User, planner.id) is not None


def test_trip_from_recommended_remembers_it_and_gets_guides(client):
    client.post("/api/auth/guest")
    slug = client.get("/api/inspire").json()[0]["slug"]
    t = client.post(f"/api/inspire/{slug}/trip", json={}).json()
    assert t["source_itinerary"] == slug
    assert all(s["guide"] and s["guide"]["fun_fact"] for s in t["stops"])
    assert client.get("/api/trips").json()[0]["source_itinerary"] == slug
    dup = client.post(f"/api/trips/{t['id']}/duplicate").json()
    assert dup["source_itinerary"] == slug


def test_own_trip_stop_gets_a_guide_when_we_know_the_place(client):
    client.post("/api/auth/guest")
    t = client.post("/api/trips", json={"name": "Peru", "stops": [
        {"name": "Cusco", "country_code": "PE", "latitude": -13.53, "longitude": -71.97, "elevation_m": 3400,
         "start_date": "2027-06-01", "end_date": "2027-06-03", "activities": [{"type": "city"}]},
        {"name": "Somewhere Unknown", "country_code": "PE", "latitude": -12, "longitude": -75, "elevation_m": 100,
         "start_date": "2027-06-04", "end_date": "2027-06-05", "activities": [{"type": "city"}]}]}).json()
    assert t["source_itinerary"] is None
    assert "Inca" in t["stops"][0]["guide"]["blurb"] and t["stops"][1]["guide"] is None


def test_no_dev_link_through_a_lan_ip_or_tunnel(client):
    _register(client, "tunnel@example.com")
    for base in ("http://192.168.1.20:8000", "https://abc123.ngrok-free.app"):
        r = _new_client(base).post("/api/auth/password/forgot", json={"email": "tunnel@example.com"})
        assert r.status_code == 202 and "dev_link" not in r.json(), base
        r = _new_client(base).post("/api/auth/email-link", json={"email": "tunnel@example.com"})
        assert "dev_link" not in r.json(), base


def test_no_dev_link_for_an_admin(client, db):
    from app.models import User
    u = _register(client, "boss@example.com")
    db.get(User, u["id"]).is_admin = True
    db.commit()
    assert "dev_link" not in client.post("/api/auth/password/forgot", json={"email": "boss@example.com"}).json()
    assert "dev_link" not in client.post("/api/auth/email-link", json={"email": "boss@example.com"}).json()


def test_pre_registered_account_is_taken_back_by_the_email_owner(client):
    # an attacker registers the victim's email with their own password
    attacker = _new_client()
    _register(attacker, "victim@example.com", "attacker pass 1")
    # the real owner signs in with a link sent to their inbox
    r = client.post("/api/auth/email-link", json={"email": "victim@example.com"})
    assert client.post("/api/auth/email-link/verify", json={"token": _token(r.json())}).status_code == 200
    assert attacker.get("/api/me").status_code == 401  # the attacker's session ended
    fresh = _new_client()
    assert fresh.post("/api/auth/login", json={"email": "victim@example.com", "password": "attacker pass 1"}).status_code == 401
    # once proven, a later link does not wipe the owner's own password
    assert client.post("/api/me/password", json={"new_password": "owner pass 22"}).status_code == 200
    r = client.post("/api/auth/email-link", json={"email": "victim@example.com"})
    client.post("/api/auth/email-link/verify", json={"token": _token(r.json())})
    assert fresh.post("/api/auth/login", json={"email": "victim@example.com", "password": "owner pass 22"}).status_code == 200
