"""Preferred brands: the kit follows them only when that is honest."""
from app.engine import outfit as O
from app.engine.fit import FitResult
from app.services import brands as B
from app.services.profile import read_rules
from tests.test_profile import PERU


# ---------------------------------------------------------------- reading them

def test_rules_read_a_preference_not_an_owned_piece():
    assert read_rules("Preferisco vestiti Patagonia").brands == ["Patagonia"]
    assert read_rules("I only wear Arc'teryx").brands == ["Arc'teryx"]
    up = read_rules("ho un pile Decathlon ma preferisco Patagonia")
    assert up.brands == ["Patagonia"] and up.owned[0].brand == "Decathlon"
    assert read_rules("I have a Patagonia down jacket").brands is None
    assert read_rules("nessun brand preferito").brands == []
    also = read_rules("mi piace anche Rab")
    assert also.brands == ["Rab"] and also.brands_add


def test_brand_spelling_follows_the_catalog():
    cat = ["Arc'teryx", "Decathlon", "Patagonia", "The North Face"]
    assert B.canon(None, ["arcteryx", "PATAGONIA", "north face", "Quechua", "Acme"], cat) == \
        ["Arc'teryx", "Patagonia", "The North Face", "Decathlon", "Acme"]
    assert B.canon(None, ["patagonia", "Patagonia"], cat) == ["Patagonia"]
    assert B.unknown(["Patagonia", "Acme"], cat) == ["Acme"]


# ---------------------------------------------------------------- engine rule

def _item(id_, brand, price, stars=4.0, passes=True, score=0.8):
    it = O.CatalogItem(id=id_, slot="mid_top", name="Fleece", brand=brand, price=price, specs={})
    it.fit = FitResult(passes=passes, score=score, stars=stars)
    return it


def test_preferred_pick_stays_honest():
    cands = [_item("a", "Decathlon", 20), _item("b", "Decathlon", 60), _item("c", "Rab", 90),
             _item("d", "Patagonia", 70), _item("e", "Patagonia", 300),
             _item("f", "Patagonia", 40, passes=False)]
    pref = frozenset({"patagonia"})
    normal = O.pick_for_tier(cands, "cheap")
    pick, why = O.preferred_pick(cands, "cheap", pref, normal)
    # cheapest Patagonia that passes and is not above the Medium pick's price
    assert pick.id == "d" and why is None
    # premium: no cap, best Patagonia
    assert O.preferred_pick(cands, "premium", pref, O.pick_for_tier(cands, "premium"))[0].brand == "Patagonia"
    # only unfit or too expensive pieces: the normal pick stays, and the reason is known
    assert O.preferred_pick(cands[:3] + [cands[5]], "cheap", pref, normal) == (None, "unfit")
    assert O.preferred_pick(cands[:3] + [cands[4]], "cheap", pref, normal) == (None, "budget")
    assert O.preferred_pick(cands[:3], "cheap", pref, normal) == (None, "none")


# ---------------------------------------------------------------- API

def test_patagonia_preference_changes_the_kit_and_explains_the_rest(client):
    client.post("/api/auth/guest")
    trip = client.post("/api/trips", json=PERU).json()
    base = client.get(f"/api/trips/{trip['id']}/plans").json()["tiers"]
    assert base["premium"]["brands"] is None
    r = client.patch("/api/me", json={"preferred_brands": ["patagonia"]})
    assert r.status_code == 200 and r.json()["preferred_brands"] == ["Patagonia"]
    tiers = client.get(f"/api/trips/{trip['id']}/plans").json()["tiers"]
    prem = tiers["premium"]
    buy = [i for i in prem["items"] if i["kind"] == "product"]
    pata = [i for i in buy if i["preferred_brand"]]
    assert pata and all(i["item"]["brand"] == "Patagonia" for i in pata)
    assert prem["brands"]["used"] == len(pata) and prem["brands"]["to_buy"] == len(buy)
    # every non-Patagonia piece to buy says why, unless it was just never in question
    for i in buy:
        if not i["preferred_brand"]:
            assert i["brand_note"] is None or "Patagonia" in i["brand_note"] or "warmer" in i["brand_note"]
    # honesty: the warmth verdict is never worse than without the preference
    rank = {"cold": 0, "marginal": 1, "covered": 2}
    for brand in (["Patagonia"], ["Uniqlo"], ["Arc'teryx", "Rab"]):
        client.patch("/api/me", json={"preferred_brands": brand})
        got = client.get(f"/api/trips/{trip['id']}/plans").json()["tiers"]
        for t in ("cheap", "medium", "premium"):
            assert rank[got[t]["warmth"]["status"]] >= rank[base[t]["warmth"]["status"]], (brand, t)
    client.patch("/api/me", json={"preferred_brands": ["Patagonia"]})
    # the cheap kit doesn't turn into the premium one
    assert tiers["cheap"]["totals"]["total"] <= base["medium"]["totals"]["total"] * 1.5
    # the product picker marks them and lists them first among equals
    slot = pata[0]["slot"]
    pick = client.get(f"/api/trips/{trip['id']}/slots/{slot}/products").json()
    assert pick["preferred_brands"] == ["Patagonia"]
    assert any(i["preferred_brand"] for i in pick["items"])


def test_profile_lists_catalog_brands_and_unknown_ones(client):
    client.post("/api/auth/guest")
    client.patch("/api/me", json={"preferred_brands": ["Patagonia", "Acme Wear"]})
    prof = client.get("/api/me/profile").json()
    assert "Patagonia" in prof["catalog_brands"] and "Generic" not in prof["catalog_brands"]
    assert prof["preferred_brands"] == ["Patagonia", "Acme Wear"]
    assert prof["unknown_brands"] == ["Acme Wear"]


def test_chat_sets_brands_and_undo_restores(client):
    client.post("/api/auth/guest")
    trip = client.post("/api/trips", json=PERU).json()
    body = client.post(f"/api/trips/{trip['id']}/chat",
                       json={"message": "Preferisco vestiti Patagonia", "tier": "premium"}).json()
    assert body["kind"] == "update"
    assert any("Preferred brands: none → Patagonia" in c for c in body["changes"])
    assert body["undo"]["profile"]["preferred_brands"] == []
    assert client.get("/api/me/profile").json()["preferred_brands"] == ["Patagonia"]
    client.patch("/api/me", json=body["undo"]["profile"])
    assert client.get("/api/me/profile").json()["preferred_brands"] == []


def test_quiz_takes_brands(client):
    client.post("/api/auth/guest")
    r = client.post("/api/me/quiz", json={"brands": ["arcteryx", "rab"]}).json()
    assert r["profile"]["preferred_brands"] == ["Arc'teryx", "Rab"]
    # skipped = kept
    r = client.post("/api/me/quiz", json={}).json()
    assert r["profile"]["preferred_brands"] == ["Arc'teryx", "Rab"]
