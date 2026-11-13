"""One bag for the whole trip (Manu, 13 Nov 2026): the same jackets, fleece and boots at
every stop; only clearly hot places add a few light pieces (shorts, T-shirt, sandals), and
two mountains never get two outfits."""

MOUNTAINS = [("Cortina", 46.54, 12.14, 1224, "2027-07-10", "2027-07-13",
              [{"type": "hiking", "difficulty": "moderate", "max_altitude_m": 2700}]),
             ("Val Gardena", 46.57, 11.67, 1236, "2027-07-14", "2027-07-16",
              [{"type": "hiking", "difficulty": "moderate", "max_altitude_m": 2500}])]
SEA = [("Cagliari", 39.22, 9.11, 10, "2027-07-19", "2027-07-23", [{"type": "beach"}]),
       ("Villasimius", 39.14, 9.52, 5, "2027-07-24", "2027-07-26", [{"type": "beach"}])]


def _trip(client, stops, market="us"):
    client.post("/api/auth/guest")
    client.patch("/api/me", json={"market": market, "gender_pref": "men"})
    t = client.post("/api/trips", json={"name": "Mix", "stops": [
        {"name": n, "latitude": la, "longitude": lo, "elevation_m": el, "start_date": a,
         "end_date": b, "activities": acts} for n, la, lo, el, a, b, acts in stops]}).json()
    return t["id"]


def test_two_mountains_share_one_bag(client):
    tid = _trip(client, MOUNTAINS)
    plans = client.get(f"/api/trips/{tid}/plans").json()
    assert plans["zones"] == []
    for tp in plans["tiers"].values():
        slots = [i["slot"] for i in tp["items"]]
        assert len(slots) == len(set(slots)) and not any("@" in s for s in slots)


def test_sea_after_mountains_adds_light_pieces_only(client):
    tid = _trip(client, MOUNTAINS + SEA)
    plans = client.get(f"/api/trips/{tid}/plans").json()
    (zone,) = plans["zones"]
    assert zone["names"] == ["Cagliari", "Villasimius"]
    medium = plans["tiers"]["medium"]
    extra = [i for i in medium["items"] if "@" in i["slot"]]
    assert {i["base_slot"] for i in extra} <= {"base_top", "trousers", "footwear"}
    assert {"trousers@warm", "base_top@warm"} <= {i["slot"] for i in extra}
    main = {i["slot"]: i for i in medium["items"] if "@" not in i["slot"]}
    for i in extra:  # really lighter than the piece it stands in for, and in the total
        spec = i["item"]["specs"]
        if i["base_slot"] == "footwear":
            assert spec["footwear_type"] in ("sandal", "sneaker")
        else:
            assert spec["clo"] < main[i["base_slot"]]["item"]["specs"]["clo"]
        assert i["item"]["gender"] in ("men", "unisex")
    buy = sum(i["cost"] for i in medium["items"] if i["kind"] == "product")
    assert abs(medium["totals"]["buy"] - buy) < 0.01
    # one shell, one insulated jacket, one fleece: never a second set for the sea
    for s in ("shell_top", "insulation_top", "mid_top"):
        assert sum(1 for i in medium["items"] if i["slot"].split("@")[0] == s) <= 1


def test_layers_wear_the_light_pieces_at_the_sea(client):
    tid = _trip(client, MOUNTAINS + SEA)
    st = client.get(f"/api/trips/{tid}/strategy?tier=medium").json()
    keys = [s["key"] for s in st["slots"]]
    assert "trousers@warm" in keys and "trousers@warm" in st["kit"]
    by = {s["name"]: s for s in st["stages"]}
    assert by["Cagliari"]["slots"]["trousers@warm"]["status"] == "worn"
    assert by["Cortina"]["slots"]["trousers"]["status"] == "worn"
    assert "trousers@warm" not in by["Cortina"]["slots"]


def test_hot_day_piece_can_be_owned_or_swapped(client):
    tid = _trip(client, MOUNTAINS + SEA)
    r = client.get(f"/api/trips/{tid}/slots/trousers@warm/products").json()
    assert r["items"] and all(i["specs"]["clo"] <= 0.09 for i in r["items"])
    pick = r["items"][-1]
    assert client.put(f"/api/trips/{tid}/selections", json={
        "tier": "medium", "slot": "trousers@warm", "choice": "product",
        "product_id": pick["id"]}).status_code == 200
    plans = client.get(f"/api/trips/{tid}/plans").json()
    line = next(i for i in plans["tiers"]["medium"]["items"] if i["slot"] == "trousers@warm")
    assert line["item"]["id"] == pick["id"] and line["locked"]
    client.put(f"/api/trips/{tid}/selections", json={"tier": "medium", "slot": "trousers@warm",
                                                     "choice": "have"})
    plans = client.get(f"/api/trips/{tid}/plans").json()
    for tp in plans["tiers"].values():
        line = next(i for i in tp["items"] if i["slot"] == "trousers@warm")
        assert line["kind"] == "have" and line["cost"] == 0
    assert client.put(f"/api/trips/{tid}/selections", json={
        "tier": "medium", "slot": "shell_top@warm", "choice": "have"}).status_code == 422
