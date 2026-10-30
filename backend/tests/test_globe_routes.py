"""Routes on the home globe: real shapes by trip length, ready-made itineraries included, and
"Dress me for this trip" turning a route into a trip the kit can run on."""
from datetime import date

from app.globe import routes as gr


def test_routes_endpoint_is_light_and_has_every_length(client):
    r = client.get("/api/globe/routes", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers["etag"]
    d = r.json()
    assert [b["key"] for b in d["buckets"]] == ["1w", "10d", "2w", "3w"]
    keys = {b["key"] for b in d["buckets"]}
    assert all(r["bucket"] in keys for r in d["routes"])
    assert len(d["routes"]) > 150
    assert len({c for r in d["routes"] for c in r["countries"]}) > 50
    _, gz = gr.payload_bytes()
    assert len(gz) < 150_000


def test_every_route_is_sound():
    ids = set()
    for r in gr.routes():
        assert r["id"] not in ids
        ids.add(r["id"])
        assert gr.bucket_of(r["days"]) == r["bucket"], r["id"]
        assert r["days"] == sum(s["days"] for s in r["stops"])
        assert len(r["stops"]) >= 2 and r["title"]
        assert {s["country"] for s in r["stops"]} <= set(r["countries"])
        for s in r["stops"]:
            assert -90 <= s["lat"] <= 90 and -180 <= s["lon"] <= 180
            assert 0 <= s["elevation_m"] < 6000 and s["days"] >= 1
            assert all(1 <= d <= s["days"] and names for d, names in s["visits"])


def test_ready_made_itineraries_replace_their_twin():
    rs = gr.routes()
    peru = next(r for r in rs if r["guide"] == "peru-coast-andes-titicaca")
    assert peru["id"] == "it-peru-coast-andes-titicaca" and peru["best_months"]
    # no read route repeats the guided one: same countries, same length, same shape
    for r in rs:
        if r["guide"] is None and r["countries"] == ["PE"] and r["bucket"] == peru["bucket"]:
            assert gr._overlap([s["name"] for s in r["stops"]], [s["name"] for s in peru["stops"]]) < 0.3


def test_cusco_is_high_and_routes_pass_there():
    through = [r for r in gr.routes() if any(s["name"] == "Cusco" for s in r["stops"])]
    assert len(through) >= 3
    cusco = next(s for r in through for s in r["stops"] if s["name"] == "Cusco")
    assert 3000 < cusco["elevation_m"] < 3700


def test_dress_me_for_a_route(client):
    client.post("/api/auth/guest")
    r = next(r for r in gr.routes() if r["guide"] is None and len(r["stops"]) >= 4)
    res = client.post(f"/api/globe/routes/{r['id']}/trip", json={"start_date": "2027-04-05"})
    assert res.status_code == 201
    trip = res.json()
    stops = trip["stops"]
    assert [s["name"] for s in stops] == [s["name"] for s in r["stops"]]
    assert stops[0]["start_date"] == "2027-04-05"
    for a, b in zip(stops, stops[1:]):  # back to back
        assert date.fromisoformat(b["start_date"]) == date.fromisoformat(a["end_date"]).fromordinal(
            date.fromisoformat(a["end_date"]).toordinal() + 1)
    for s, src in zip(stops, r["stops"]):
        types = [a["type"] for a in s["activities"]]
        assert ("city" in types) == (src["kind"] in ("city", "town"))
        if src["outdoors"] or src["kind"] not in ("city", "town"):
            assert "unknown" in types  # "don't know yet": dressed for easy and harder days
    plans = client.get(f"/api/trips/{trip['id']}/plans").json()
    assert plans["tiers"]["medium"]["items"]


def test_dress_me_without_a_date_is_a_guess(client):
    client.post("/api/auth/guest")
    r = gr.routes()[-1]
    trip = client.post(f"/api/globe/routes/{r['id']}/trip", json={}).json()
    assert trip["start_estimated"] is True and trip["estimate"]["start"] is True


def test_dress_me_errors(client):
    client.post("/api/auth/guest")
    assert client.post("/api/globe/routes/nope/trip", json={}).status_code == 404
    client.cookies.clear()
    assert client.post(f"/api/globe/routes/{gr.routes()[0]['id']}/trip", json={}).status_code == 401


# ---- weather by month


def test_every_route_knows_its_weather():
    for r in gr.routes():
        assert r["months"] and len(r["months"]) == 12, r["id"]
        assert r["best_months"], r["id"]
        for m in r["months"]:
            assert m["lo"] <= m["hi"] and m["level"] in (0, 1, 2)
            if m["level"] == gr.GOOD:
                assert m["note"] is None, r["id"]


def test_best_months_make_sense():
    peru = next(r for r in gr.routes() if r["countries"] == ["PE"] and not r["guide"])
    assert not {1, 2, 3} & set(peru["best_months"])  # Andean rainy season
    assert 7 in peru["best_months"]
    assert "rainy season" in peru["months"][0]["note"]
    japan = next(r for r in gr.routes() if r["countries"] == ["JP"])
    assert {4, 10} <= set(japan["best_months"]) and 8 not in japan["best_months"]  # hot, wet August
    iceland = next(r for r in gr.routes() if r["countries"] == ["IS"] and not r["guide"])
    assert 7 in iceland["best_months"] and 1 not in iceland["best_months"]


def test_stop_month_rules():
    assert gr.stop_month(10, 22, 40, 50) == (gr.GOOD, None)
    assert gr.stop_month(5, 18, 160, 60)[1] == "rainy season"  # Cusco January
    assert gr.stop_month(15, 22, 160, 140)[0] == gr.GOOD       # an average month in a wet place
    assert gr.stop_month(15, 22, 220, 140)[0] == gr.SO_SO      # a very wet one
    assert gr.stop_month(28, 40, 0, 5) == (gr.BAD, "very hot")
    assert gr.stop_month(-8, -2, 30, 40) == (gr.BAD, "cold")
    assert gr.stop_month(25, 32.5, 150, 130, 2.7) == (gr.SO_SO, "hot and humid")  # Kyoto August
    assert gr.stop_month(27, 35.5, 50, 120, 3.1) == (gr.BAD, "hot and humid")   # Bangkok April
    assert gr.stop_month(18, 31, 20, 60, 1.6)[0] == gr.GOOD                       # a dry 31 °C


def test_feels_like():
    assert gr.feels_like(20, 2.0) == 20               # mild: just the temperature
    assert gr.feels_like(31, 1.0) <= 31.5             # dry heat feels like itself
    assert 34 <= gr.feels_like(31, 2.7) <= 37         # sticky
    assert gr.feels_like(35.5, 3.1) >= 41


def test_start_in_the_month_you_pick():
    assert gr.start_in([5], date(2026, 10, 26)) == date(2027, 5, 1)
    assert gr.start_in([11], date(2026, 10, 15)) == date(2026, 11, 1)
    assert gr.start_in([11], date(2026, 10, 26)) == date(2026, 11, 9)  # two weeks away, same month
    assert gr.start_in([10], date(2026, 10, 26)) == date(2027, 10, 1)  # this month is too soon
    assert gr.start_in([], date(2026, 10, 26)) == date(2026, 12, 1)


def test_dress_me_in_a_month(client):
    client.post("/api/auth/guest")
    r = gr.routes()[-1]
    trip = client.post(f"/api/globe/routes/{r['id']}/trip", json={"month": 3}).json()
    assert trip["stops"][0]["start_date"][5:7] == "03"
    assert trip["start_estimated"] is True
    assert client.post(f"/api/globe/routes/{r['id']}/trip", json={"month": 13}).status_code == 422


def test_dress_me_for_a_ready_made_itinerary_keeps_its_guide(client):
    client.post("/api/auth/guest")
    r = next(x for x in gr.routes() if x["guide"])
    trip = client.post(f"/api/globe/routes/{r['id']}/trip", json={"start_date": "2027-06-01"}).json()
    assert trip["source_itinerary"] == r["guide"]
    assert [s["name"] for s in trip["stops"]] == [s["name"] for s in r["stops"]]
