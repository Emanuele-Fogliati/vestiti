"""Traveller profile: quiz, chat reader (rules, model offline) and the plan diff."""
from app.engine import outfit as O
from app.engine.strategy import conditions_for_stage
from app.services.profile import read_rules
from tests.helpers import stage
from tests.test_api import TRIP

PERU = {"name": "Peru", "stops": [
    {"name": "Cusco", "latitude": -13.53, "longitude": -71.97, "elevation_m": 3400,
     "start_date": "2026-11-25", "end_date": "2026-11-27", "activities": [{"type": "city"}]},
    {"name": "Puno", "latitude": -15.84, "longitude": -70.02, "elevation_m": 3827,
     "start_date": "2026-11-30", "end_date": "2026-11-30",
     "activities": [{"type": "hiking", "difficulty": "hard", "max_altitude_m": 5200}]}]}


# ---------------------------------------------------------------- rule reader

def test_rules_read_cold_in_both_languages():
    assert read_rules("I'm always cold").cold == "very_cold"
    assert read_rules("Sono un freddolone").cold == "very_cold"
    assert read_rules("io non patisco tanto il freddo").cold == "warm"
    assert read_rules("I don't really feel the cold").cold == "warm"
    assert read_rules("I'm a bit cold sometimes").cold == "bit_cold"
    assert read_rules("I have a fleece").cold is None


def test_rules_read_owned_pieces_with_brand_and_age():
    up = read_rules("I have an old Decathlon fleece and hiking boots")
    by = {p.category: p for p in up.owned}
    assert by["mid_top"].name == "Old Decathlon fleece" and by["mid_top"].brand == "Decathlon"
    assert by["footwear"].footwear_type == "hiking_boot"
    it = read_rules("ho un piumino The North Face, ma non ho il k-way")
    cats = {p.category for p in it.owned}
    assert cats == {"insulation_top"}  # "non ho il k-way" is not ownership


def test_rules_ignore_questions_about_pieces():
    up = read_rules("Do I need a fleece?")
    assert up.owned == [] and up.question


def test_rules_read_pace_and_evenings():
    up = read_rules("cammino piano e faccio tante foto, la sera esco a fare aperitivo")
    assert up.pace == "relaxed" and up.evenings == "late"
    assert read_rules("I go to bed early").evenings == "early"


# ---------------------------------------------------------------- engine

def test_slow_pace_needs_more_warmth_on_the_move():
    st = stage(activities=[{"type": "hiking", "difficulty": "moderate"}], tmax=8, tmin=0)
    req = lambda pace: max(c.required for c in conditions_for_stage(st, pace=pace)  # noqa: E731
                           if c.mode == "moving")
    assert req("relaxed") > req("average") > req("brisk")


def test_evenings_answer_decides_if_town_evenings_are_avoidable():
    cond = next(c for c in conditions_for_stage(stage(tmax=10, tmin=0)) if c.mode == "rest")
    assert O.avoidable(cond, "sometimes") and O.avoidable(cond, "early")
    assert not O.avoidable(cond, "late")


# ---------------------------------------------------------------- API

def test_quiz_saves_profile_adds_basics_and_shows_the_change(client):
    client.post("/api/auth/guest")
    trip = client.post("/api/trips", json=PERU).json()
    prof = client.get("/api/me/profile").json()
    assert prof["done"] is False and prof["cold"] == "average" and len(prof["basics"]) == 6
    r = client.post(f"/api/me/quiz?trip_id={trip['id']}&tier=medium",
                    json={"cold": "very_cold", "pace": "relaxed", "evenings": None,
                          "owned": ["fleece", "hiking_boots"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profile"]["done"] and body["profile"]["cold"] == "very_cold"
    assert set(body["profile"]["owned"]) == {"fleece", "hiking_boots"}
    assert any("Feel the cold" in c for c in body["changes"])
    assert body["plan"]["pieces"] or body["plan"]["status"]
    me = client.get("/api/me").json()
    assert me["thermal_offset"] == 0.3 and me["pace"] == "relaxed" and me["evenings"] == "sometimes"
    assert me["profile_done_at"]
    # un-ticking a chip removes only the generic piece the quiz added
    r = client.post("/api/me/quiz", json={"owned": ["fleece"]}).json()
    assert r["profile"]["owned"] == ["fleece"]
    assert any("Removed" in c for c in r["changes"])


def test_quiz_can_be_skipped_entirely(client):
    client.post("/api/auth/guest")
    r = client.post("/api/me/quiz", json={}).json()
    assert r["profile"]["done"] and r["changes"] == []


def test_chat_updates_profile_wardrobe_and_plan(client):
    client.post("/api/auth/guest")
    trip = client.post("/api/trips", json=PERU).json()
    r = client.post(f"/api/trips/{trip['id']}/chat",
                    json={"message": "Sono freddoloso e ho un vecchio pile Decathlon", "tier": "medium"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "update" and body["reader"] == "rules"  # model is off in tests
    assert any("Feel the cold" in c for c in body["changes"])
    assert any("Old Decathlon fleece" in c for c in body["changes"])
    assert body["undo"]["profile"]["thermal_offset"] == 0.0 and len(body["undo"]["wardrobe_ids"]) == 1
    # the reply says whether the new fleece is used in this kit, and if not, why
    assert len(body["plan"]["owned"]) == 1 and "Old Decathlon fleece" in body["plan"]["owned"][0]
    assert body["text"].startswith("Got it.")
    wardrobe = client.get("/api/wardrobe").json()
    assert wardrobe[0]["name"] == "Old Decathlon fleece" and wardrobe[0]["category"] == "mid_top"
    # same thing again: nothing new
    again = client.post(f"/api/trips/{trip['id']}/chat",
                        json={"message": "I'm always cold", "tier": "medium"}).json()
    assert again["changes"] == [] and "already" in again["text"]


def test_chat_question_is_answered_not_applied(client):
    client.post("/api/auth/guest")
    trip = client.post("/api/trips", json=TRIP).json()
    body = client.post(f"/api/trips/{trip['id']}/chat",
                       json={"message": "Do I need shell pants in Rome?"}).json()
    assert body["kind"] == "answer" and body["text"]
    assert client.get("/api/me").json()["thermal_offset"] == 0.0


def test_cold_traveller_gets_a_warmer_or_pricier_kit(client):
    client.post("/api/auth/guest")
    trip = client.post("/api/trips", json=PERU).json()
    base = client.get(f"/api/trips/{trip['id']}/plans").json()["tiers"]["medium"]
    client.patch("/api/me", json={"thermal_offset": 0.3})
    cold = client.get(f"/api/trips/{trip['id']}/plans").json()["tiers"]["medium"]
    assert cold["totals"]["total"] >= base["totals"]["total"]
    req_b = max(s["rest"]["required"] for s in base["warmth"]["stages"])
    req_c = max(s["rest"]["required"] for s in cold["warmth"]["stages"])
    assert round(req_c - req_b, 2) == 0.3


def test_model_reply_is_validated_and_merged_with_rules():
    import json

    from app.llm.client import LLMClient
    from app.llm.profile_chat import read_message
    from tests.test_llm import settings, transport

    reply = json.dumps({"cold": "very_cold", "pace": "average", "evenings": "nonsense",
                        "owned": [{"category": "mid_top", "name": "Old Decathlon fleece",
                                   "brand": "Decathlon", "warmth": "medium"},
                                  {"category": "spaceship", "name": "x"}],
                        "question": False})
    up, reader = read_message("I'm a cold person, I have an old Decathlon fleece and I walk fast",
                              LLMClient(settings(), transport(reply, [])))
    assert reader == "llm" and up.cold == "very_cold"
    assert up.evenings is None  # invalid value dropped
    assert up.pace == "brisk"  # model said "average" (= not mentioned), the rules caught it
    assert [p.category for p in up.owned] == ["mid_top"]  # unknown category dropped
