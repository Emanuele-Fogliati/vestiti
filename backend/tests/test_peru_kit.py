"""Peru, in the app (round 5 on the PC): one upgrade line per piece with the net cost,
a warmth gap is closed or explained, and a men's kit has no women's cuts."""

STOPS = [("Cusco", -13.53, -71.97, 3400, "2026-11-25", "2026-11-26", [{"type": "city"}]),
         ("Puno", -15.84, -70.02, 3827, "2026-11-30", "2026-11-30",
          [{"type": "hiking", "difficulty": "hard", "max_altitude_m": 5200}]),
         ("Taquile", -15.77, -69.68, 4072, "2026-12-01", "2026-12-01", [{"type": "boat"}]),
         ("Lima", -12.04, -77.03, 150, "2026-12-06", "2026-12-06", [{"type": "city"}])]


def _plans(client):
    t = client.post("/api/trips", json={"name": "Peru", "stops": [
        {"name": n, "latitude": la, "longitude": lo, "elevation_m": el, "start_date": a,
         "end_date": b, "activities": acts} for n, la, lo, el, a, b, acts in STOPS]}).json()
    return client.get(f"/api/trips/{t['id']}/plans").json()


def test_upgrades_are_one_line_per_piece_and_cold_is_explained(client):
    client.post("/api/auth/guest")
    plans = _plans(client)
    for tier, tp in plans["tiers"].items():
        slots = [u["slot"] for u in tp["auto_upgrades"]]
        assert len(slots) == len(set(slots)), tier
        for u in tp["auto_upgrades"]:
            line = next(i for i in tp["items"] if i["slot"] == u["slot"])
            assert u["to"]["id"] == line["item"]["id"]  # the line names the item you get
            before = u["from"]["price"] if u["from"] else 0
            assert round(u["to"]["price"] - before, 2) == u["extra_cost"]
        if tp["warmth"]["status"] == "cold":
            assert tp["shortfall"] and "To close it" in tp["shortfall"]["message"]
        else:
            assert tp["shortfall"] is None
    assert plans["tiers"]["medium"]["warmth"]["status"] != "cold"


def test_mens_kit_has_no_womens_cuts(client):
    client.post("/api/auth/guest")
    assert client.patch("/api/me", json={"gender_pref": "men"}).status_code == 200
    plans = _plans(client)
    for tp in plans["tiers"].values():
        assert all(i["item"]["gender"] != "women" for i in tp["items"] if i["item"])
