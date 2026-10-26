"""Saved wardrobe: find what you own by name (also older models) or from photos."""
import json

import httpx
import pytest

from app.api import wardrobe as wardrobe_api
from app.config import Settings
from app.llm.client import LLMUnavailable
from app.llm.vision import read_garment
from app.wardrobe import lookup

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200


def guest(client):
    assert client.post("/api/auth/guest").status_code == 200


def names(results):
    return [(r["brand"], r["name"]) for r in results]


# ------------------------------------------------------------------ the known-models list

def test_known_models_are_valid():
    from app.engine.garments import FOOTWEAR_TYPES, SLOT_KEYS
    lib = lookup.library()
    assert len(lib) >= 150
    assert len({m["id"] for m in lib}) == len(lib)
    for m in lib:
        assert m["category"] in SLOT_KEYS, m
        assert m["warmth"] in lookup.WARMTH, m
        assert m["material"] in lookup.MATERIALS + (None,), m
        if m["category"] == "footwear":
            assert m["footwear_type"] in FOOTWEAR_TYPES, m
        if m["waterproof"]:
            assert m["windproof"], m


@pytest.mark.parametrize("query, expected", [
    ("torrentshell", ("Patagonia", "Torrentshell")),
    ("patagonia torentshell", ("Patagonia", "Torrentshell")),  # typo
    ("tnf nuptse", ("The North Face", "1996 Retro Nuptse Jacket")),  # brand nickname
    ("arcteryx beta ar", ("Arc'teryx", "Beta AR Jacket")),
    ("quechua mh 500", ("Decathlon", "Quechua MH500")),  # sub-brand + code written apart
    ("atom lt", ("Arc'teryx", "Atom LT Hoody")),  # renamed in 2022
    ("salomon x ultra 3", ("Salomon", "X Ultra 3 Mid GTX")),  # replaced in 2021
    ("levis 501", ("Levi's", "501 Original Jeans")),
    ("piumino", (None, "")),  # Italian word for an everyday piece
])
def test_search_by_name_finds_current_and_older_models(db, query, expected):
    res = lookup.search(db, query)
    assert res, query
    brand, name = expected
    assert res[0]["brand"] == brand and res[0]["name"].startswith(name), names(res)


def test_older_models_are_marked_and_shop_products_come_first(db):
    res = lookup.search(db, "salomon x ultra")
    shop = [r for r in res if r["source"] == "shop"]
    older = [r for r in res if r["older"]]
    assert shop and older
    assert res.index(shop[0]) < res.index(older[0])
    assert any(r["note"] and "2021" in r["note"] for r in older)


def test_search_does_not_mix_brands(db):
    res = lookup.search(db, "patagonia nano puff")
    assert res[0]["brand"] == "Patagonia"
    assert all(r["brand"] in ("Patagonia",) or r["score"] < res[0]["score"] for r in res)
    assert lookup.search(db, "zara blazer") == []


def test_category_filter(db):
    res = lookup.search(db, "torrentshell", category="shell_bottom")
    assert res and all(r["category"] == "shell_bottom" for r in res)


def test_guess_from_name_without_ai_uses_keyword_rules():
    g = lookup.guess_from_name("Black puffer jacket from Zara")
    assert g["category"] == "insulation_top" and g["source"] == "estimate" and g["by"] == "rules"
    boots = lookup.guess_from_name("cheap waterproof hiking boots")
    assert boots["footwear_type"] == "hiking_boot" and boots["waterproof"] and boots["ankle_support"]
    assert lookup.guess_from_name("my lucky blazer") is None


def test_guess_from_name_drops_invalid_values_from_the_model():
    class FakeLLM:
        def chat_json(self, *a, **k):
            return {"category": "spaceship", "warmth": "hot"}
    assert lookup.guess_from_name("Rain jacket", llm=FakeLLM())["by"] == "rules"

    class Good:
        def chat_json(self, *a, **k):
            return {"brand": "Zara", "name": "Puffer", "category": "insulation_top", "warmth": "boiling",
                    "material": "unobtainium", "waterproof": "yes"}
    g = lookup.guess_from_name("Zara puffer", llm=Good())
    assert g["by"] == "ai" and g["warmth"] == "medium" and g["material"] is None and g["waterproof"] is False


# ------------------------------------------------------------------ API

def test_lookup_api_and_add_confirmed_model(client):
    guest(client)
    res = client.get("/api/wardrobe/lookup", params={"q": "torrentshell 3l"}).json()["results"]
    pick = next(r for r in res if r["category"] == "shell_top")
    body = {k: pick[k] for k in ("category", "name", "brand", "warmth", "waterproof", "windproof",
                                 "material", "footwear_type", "ankle_support")}
    body.update(model_ref=pick["ref"], added_via="search")
    r = client.post("/api/wardrobe", json=body)
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["model_ref"] == pick["ref"] and item["added_via"] == "search"
    # the server copies the model's own data, not the client's
    assert item["specs"] and item["specs"].get("waterproof_mm")
    assert item["clo_override"] is not None


def test_unknown_model_ref_is_dropped(client):
    guest(client)
    r = client.post("/api/wardrobe", json={"category": "mid_top", "name": "Fleece",
                                           "model_ref": "lib:does-not-exist", "added_via": "search"})
    assert r.status_code == 201 and r.json()["model_ref"] is None and r.json()["specs"] is None
    assert client.post("/api/wardrobe", json={"category": "mid_top", "name": "Fleece",
                                              "added_via": "telepathy"}).status_code == 422


def test_known_model_data_reaches_the_plan():
    from app.models import WardrobeItem
    from app.services.planner import owned_item
    w = WardrobeItem(id="x", category="shell_top", name="Beta AR", warmth="medium", waterproof=True,
                     windproof=True, specs={"waterproof_mm": 28000})
    assert owned_item(w).specs["waterproof_mm"] == 28000
    w.specs = None
    assert owned_item(w).specs["waterproof_mm"] == 10000


def test_lookup_needs_a_session(client):
    assert client.get("/api/wardrobe/lookup", params={"q": "beta"}).status_code == 401


def test_guess_api(client):
    guest(client)
    r = client.post("/api/wardrobe/guess", json={"name": "Old waterproof rain jacket"})
    assert r.status_code == 200 and r.json()["result"]["category"] == "shell_top"


# ------------------------------------------------------------------ photos

def test_photo_status_off_when_ai_is_off(client):
    guest(client)
    st = client.get("/api/wardrobe/photo-status").json()
    assert st["enabled"] is False and st["available"] is False


def _send(client, n=3, kind="top", data=JPEG):
    files = [("photos", (f"p{i}.jpg", data, "image/jpeg")) for i in range(n)]
    return client.post("/api/wardrobe/recognize", files=files, data={"kind": kind})


def test_recognize_reads_the_label_and_proposes_the_model(client, monkeypatch):
    guest(client)
    seen_args = {}

    def fake(images, hint):
        seen_args["n"], seen_args["hint"] = len(images), hint
        return {"text_seen": ["PATAGONIA", "TORRENTSHELL 3L", "STY85240"], "brand": "Patagonia",
                "model": "Torrentshell 3L", "style_code": "STY85240", "category": "shell_top",
                "colour": "blue", "features": ["hood", "taped seams"], "waterproof": True,
                "label_readable": True, "confidence": "high"}
    monkeypatch.setattr(wardrobe_api, "read_garment", fake)
    r = _send(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert seen_args == {"n": 3, "hint": "a jacket or top"}
    assert body["seen"]["brand"] == "Patagonia" and body["seen"]["style_code"] == "STY85240"
    assert body["results"][0]["name"].startswith("Torrentshell") and body["results"][0]["category"] == "shell_top"
    assert body["described"]["category"] == "shell_top" and body["described"]["waterproof"] is True


def test_recognize_finds_the_model_among_label_words(client, monkeypatch):
    guest(client)
    monkeypatch.setattr(wardrobe_api, "read_garment", lambda i, h: {
        "text_seen": ["MERRELL", "MOAB 2", "GORE-TEX", "J06059"], "brand": "Merrell", "model": None,
        "category": "footwear", "footwear_type": "hiking_boot"})
    body = _send(client, kind="shoes").json()
    assert body["results"] and body["results"][0]["name"].startswith("Moab 2")


def test_recognize_without_a_readable_label_describes_the_item(client, monkeypatch):
    guest(client)
    monkeypatch.setattr(wardrobe_api, "read_garment", lambda i, h: {
        "text_seen": [], "brand": None, "model": None, "category": "insulation_top", "colour": "black",
        "features": ["quilted baffles", "hood"], "warmth": "warm", "material": "down",
        "label_readable": False, "confidence": "low"})
    body = _send(client).json()
    assert body["results"] == []
    d = body["described"]
    assert d["category"] == "insulation_top" and d["material"] == "down" and d["name"] == "Black insulated jacket"


def test_recognize_trusts_the_kind_the_traveller_chose(client, monkeypatch):
    guest(client)
    monkeypatch.setattr(wardrobe_api, "read_garment", lambda i, h: {"category": "shell_top", "brand": None})
    d = _send(client, kind="shoes").json()["described"]
    assert d["category"] == "footwear"


def test_recognize_brand_only_lists_that_brands_models(client, monkeypatch):
    guest(client)
    monkeypatch.setattr(wardrobe_api, "read_garment", lambda i, h: {
        "text_seen": ["THE NORTH FACE", "100% POLYESTER"], "brand": "The North Face", "model": None,
        "category": "mid_top"})
    res = _send(client).json()["results"]
    assert res and all(r["brand"] == "The North Face" and r["category"] == "mid_top" for r in res)


def test_recognize_checks_the_photos(client, monkeypatch):
    guest(client)
    monkeypatch.setattr(wardrobe_api, "read_garment", lambda i, h: {})
    assert _send(client, n=5).status_code == 422
    assert _send(client, data=b"<?php echo 1; ?>").status_code == 422
    assert _send(client, data=JPEG + b"\x00" * wardrobe_api.MAX_PHOTO_BYTES).status_code == 413


def test_recognize_says_when_the_model_is_off(client):
    guest(client)
    r = _send(client)  # LLM_ENABLED=false in tests
    assert r.status_code == 503 and "Search by name" in r.json()["detail"]


def test_recognize_needs_a_session(client):
    assert _send(client).status_code == 401


def test_vision_request_is_openai_compatible_with_inline_images():
    seen = []

    def handler(req: httpx.Request):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content":
                              '```json\n{"brand": "Rab", "category": "insulation_top"}\n```'}}]})
    s = Settings(llm_enabled=True, vision_enabled=True, llm_base_url="http://llm.test/v1",
                 vision_model="qwen3-vl:8b-instruct")
    out = read_garment([(JPEG, "image/jpeg"), (JPEG, "image/jpeg")], "a jacket or top", settings=s,
                       transport=httpx.MockTransport(handler))
    assert out == {"brand": "Rab", "category": "insulation_top"}
    body = seen[0]
    assert body["model"] == "qwen3-vl:8b-instruct"
    parts = body["messages"][1]["content"]
    assert [p["type"] for p in parts] == ["text", "image_url", "image_url"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_vision_off_or_failing_raises():
    with pytest.raises(LLMUnavailable):
        read_garment([(JPEG, "image/jpeg")], None, settings=Settings(llm_enabled=True, vision_enabled=False))
    s = Settings(llm_enabled=True, llm_base_url="http://llm.test/v1")
    with pytest.raises(LLMUnavailable):
        read_garment([(JPEG, "image/jpeg")], None, settings=s,
                     transport=httpx.MockTransport(lambda r: httpx.Response(500)))
