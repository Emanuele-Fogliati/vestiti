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
            assert "+" not in u["reason"] and ("€" in u["reason"] or "Same price" in u["reason"])
            if u["extra_cost"] < 0 and u["from"]:
                assert "warmer and cheaper" in u["reason"] and "Saves €" in u["reason"]
        if tp["warmth"]["status"] == "cold":
            assert tp["shortfall"] and tp["shortfall"]["message"]
        else:
            assert tp["shortfall"] is None
        # a sun hat at 3,400-5,200 m, even on days too cool for "strong sun"
        assert any(i["slot"] == "sun_hat" for i in tp["items"]), tier
    medium = plans["tiers"]["medium"]
    # what is left cold is the Taquile evening outdoors, which the app explains instead of
    # buying a €400 jacket for it
    assert medium["warmth"]["status"] != "cold" or medium["shortfall"]["avoidable"]
    totals = [plans["tiers"][t]["totals"]["total"] for t in ("cheap", "medium", "premium")]
    assert totals == sorted(totals) and totals[1] < 0.75 * totals[2]


def test_mens_kit_has_no_womens_cuts(client):
    client.post("/api/auth/guest")
    assert client.patch("/api/me", json={"gender_pref": "men"}).status_code == 200
    plans = _plans(client)
    for tp in plans["tiers"].values():
        assert all(i["item"]["gender"] != "women" for i in tp["items"] if i["item"])


def test_tier_close_to_the_next_one_suggests_it():
    from app.services.planner import tier_advice

    def t(total, status):
        return {"totals": {"total": total}, "warmth": {"status": status}}
    tiers = {"cheap": t(500, "cold"), "medium": t(2254, "cold"), "premium": t(2322, "marginal")}
    tier_advice(tiers)
    assert tiers["medium"]["advice"]["tier"] == "premium"
    assert tiers["medium"]["advice"]["extra_cost"] == 68
    assert tiers["cheap"]["advice"] is None and tiers["premium"]["advice"] is None
