"""Start a trip from a sentence, a region or rows (app.services.understand / explore, api/plan)."""
from datetime import date

from app.services import explore
from app.services.understand import read

TODAY = date(2026, 11, 12)


# ---------------------------------------------------------------- reading a sentence

def test_reads_stops_with_their_own_dates():
    r = read("Buenos Aires dal 6 all'8 gennaio, poi El Calafate 9-10 gennaio, El Chaltén dall'11 al 13 "
             "e Torres del Paine 14-18 gennaio", TODAY)
    assert r["mode"] == "stops"
    got = [(s["name"], s["days"], s["start_date"]) for s in r["stops"]]
    assert got == [("Buenos Aires", 3, "2027-01-06"), ("El Calafate", 2, "2027-01-09"),
                   ("El Chaltén", 3, "2027-01-11"), ("Torres del Paine", 5, "2027-01-14")]
    assert r["start_date"] == date(2027, 1, 6) and r["missing"] == []


def test_reads_a_region_with_month_and_length():
    r = read("Voglio andare in Patagonia a gennaio per tre settimane", TODAY)
    assert r["mode"] == "region" and r["area"]["id"] == "patagonia"
    assert r["month"] == 1 and r["days"] == 21 and r["missing"] == []


def test_region_with_places_keeps_them():
    r = read("Patagonia cilena, soprattutto Torres del Paine, fine gennaio", TODAY)
    assert r["mode"] == "region" and r["keep"] == ["cl-torres-del-paine"]
    assert r["start_date"] == date(2027, 1, 20) and "how_long" in r["missing"]


def test_region_with_dates_and_an_end():
    # Manu's own sentence, 2026-11-12: it gave only Ushuaia
    for text in ("patagonia tra cile e argentina  e alla fine all ushuaia dal 16 gennaio 2027 al 30 gennaio 2027",
                 "Patagonia tra Cile e Argentina e alla fine a Ushuaia dal 16 al 30 gennaio",
                 "Patagonia, end in Ushuaia, January 16 to 30"):
        r = read(text, TODAY)
        assert r["mode"] == "region" and r["area"]["id"] == "patagonia", text
        assert r["start_date"] == date(2027, 1, 16) and r["days"] == 15 and r["missing"] == [], text
        assert r["last"] == ["ar-ushuaia"], text
    p = explore.propose(explore.area("patagonia"), r["only"], 15, 1, r["keep"], None, r["last"])
    names = [s["name"] for s in p["stops"]]
    assert p["days"] == 15 and names[-1] == "Ushuaia"
    assert "El Chaltén" in names and any("Torres del Paine" in n for n in names)
    # Patagonia is not Buenos Aires, and 15 days are not worth a flight up to Valdés
    assert "Buenos Aires" not in names and "Punta Pirámides" not in names


def test_a_length_after_a_month_is_not_a_day():
    r = read("Patagonia a gennaio, 10 giorni", TODAY)
    assert r["days"] == 10 and r["start_date"] is None and r["month"] == 1


def test_reads_a_wish_and_asks_where():
    r = read("non so, qualcosa di caldo a febbraio con il mare, 10 giorni", TODAY)
    assert r["mode"] == "open" and r["missing"] == ["where"]
    assert r["month"] == 2 and r["days"] == 10 and set(r["wishes"]) == {"warm", "beach"}


def test_italian_names_home_and_total():
    r = read("Parto da Milano il 5 gennaio, 3 giorni a Buenos Aires, poi El Calafate e El Chaltén, "
             "15 giorni in tutto", TODAY)
    assert r["home"]["name"] == "Milan"
    assert [s["name"] for s in r["stops"]] == ["Buenos Aires", "El Calafate", "El Chaltén"]
    assert sum(s["days"] for s in r["stops"]) == 15 and r["stops"][0]["days"] == 3
    assert r["stops"][0]["start_date"] == "2027-01-05"
    assert [s["name"] for s in read("Roma, Firenze e Venezia a maggio", TODAY)["stops"]] == ["Rome", "Florence", "Venice"]


def test_length_after_a_month_is_the_whole_trip():
    r = read("Tokyo and Kyoto in April, two weeks", TODAY)
    assert r["days"] == 14 and [s["days"] for s in r["stops"]] == [7, 7]


def test_stops_before_a_dated_one_end_the_day_before():
    r = read("Voglio fare tre giorni a Parigi e poi due giorni a Londra dal 3 marzo", TODAY)
    assert [(s["name"], s["start_date"]) for s in r["stops"]] == [("Paris", "2027-02-28"), ("London", "2027-03-03")]


def test_common_words_are_not_places():
    r = read("come si sta a marzo, vorrei una vista sul mare", TODAY)
    assert r["mode"] == "open" and r["stops"] == []


# ---------------------------------------------------------------- regions and the proposed route

def test_patagonia_route_fits_the_days():
    a = explore.area("patagonia")
    for days in (10, 21):
        p = explore.propose(a, None, days, 1)
        names = [s["name"] for s in p["stops"]]
        assert p["days"] == days == sum(s["days"] for s in p["stops"])
        assert "El Chaltén" in names and "El Calafate" in names
        assert any("Torres del Paine" in n for n in names)
        assert len(names) == len(set(names))
    # sights go with the town they are seen from, not as stops of their own
    p = explore.propose(a, None, 21, 1)
    assert not any(s["name"] in ("Perito Moreno Glacier", "Beagle Channel", "Laguna de los Tres") for s in p["stops"])
    calafate = next(s for s in p["stops"] if s["name"] == "El Calafate")
    assert "Perito Moreno Glacier" in calafate["sights"]


def test_keep_and_drop():
    a = explore.area("patagonia")
    p = explore.propose(a, None, 14, 1, keep=["ar-bariloche"], drop=["ar-ushuaia"])
    keys = [s["key"] for s in p["stops"]]
    assert "ar-bariloche" in keys and "ar-ushuaia" not in keys
    assert p["more"] and all(m["key"] not in keys for m in p["more"])


def test_country_and_region_names():
    assert explore.best_area("Giappone ad aprile")[0]["id"] == "c-jp"
    assert explore.best_area("in Toscana")[0]["id"] == "tuscany"
    assert explore.suggest("pata")[0]["id"] == "patagonia"


def test_ideas_follow_the_wish():
    warm = explore.ideas(2, 10, ["warm", "beach"])
    assert warm and all("°C" in i["weather"] for i in warm)
    snow = explore.ideas(2, 7, ["snow"])
    assert snow and len({tuple(i["countries"]) for i in snow}) == len(snow)


# ---------------------------------------------------------------- the API

def test_api_understand_region_then_trip(client):
    client.post("/api/auth/guest")
    r = client.post("/api/plan/understand", json={"text": "Patagonia a gennaio, tre settimane"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "region" and j["proposal"]["days"] == 21
    j2 = client.post("/api/plan/understand", json={"text": "Patagonia, alla fine Ushuaia, dal 16 al 30 gennaio"}).json()
    assert j2["proposal"]["stops"][-1]["name"] == "Ushuaia" and j2["proposal"]["last"] == ["ar-ushuaia"]
    r = client.post("/api/plan/propose", json={"area": "patagonia", "days": 12, "month": 1, "last": ["ar-ushuaia"]})
    assert r.json()["stops"][-1]["name"] == "Ushuaia"
    stops = j["proposal"]["stops"]
    r = client.post("/api/plan/propose", json={"area": "patagonia", "days": 12, "month": 1,
                                                "drop": [stops[-1]["key"]]})
    assert r.status_code == 200 and r.json()["days"] == 12
    stops = r.json()["stops"]
    r = client.post("/api/plan/trip", json={"area": "patagonia", "month": 1, "home": {"lat": 45.46, "lon": 9.19, "country": "IT"},
                                            "stops": [{**s, "elevation_m": s["elevation_m"] or 100} for s in stops]})
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["name"] == "Patagonia" and t["start_estimated"] is True
    assert t["home_airport"] in ("MXP", "LIN", "BGY")
    assert t["stops"][0]["start_date"][5:7] == "01"
    assert sum((date.fromisoformat(s["end_date"]) - date.fromisoformat(s["start_date"])).days + 1 for s in t["stops"]) == 12
    assert any(v["name"] for s in t["stops"] for v in s["visits"])


def test_api_trip_from_rows_keeps_dates(client):
    client.post("/api/auth/guest")
    rows = [{"name": "Buenos Aires", "country": "AR", "lat": -34.6, "lon": -58.38, "days": 3, "kind": "city",
             "start_date": "2027-01-06", "elevation_m": 25},
            {"name": "El Calafate", "country": "AR", "lat": -50.34, "lon": -72.26, "days": 2, "kind": "town",
             "elevation_m": 200},
            {"name": "El Chaltén", "country": "AR", "lat": -49.33, "lon": -72.89, "days": 3, "kind": "town",
             "start_date": "2027-01-12", "elevation_m": 400}]
    r = client.post("/api/plan/trip", json={"stops": rows})
    assert r.status_code == 201, r.text
    t = r.json()
    got = [(s["name"], s["start_date"], s["end_date"]) for s in t["stops"]]
    # a free day between Calafate (9-10) and Chaltén (12)
    assert got == [("Buenos Aires", "2027-01-06", "2027-01-08"), ("El Calafate", "2027-01-09", "2027-01-10"),
                   ("El Chaltén", "2027-01-12", "2027-01-14")]
    assert t["start_estimated"] is False and t["stops"][0]["activities"][0]["type"] == "city"


def test_api_open_wish_gives_ideas(client):
    client.post("/api/auth/guest")
    j = client.post("/api/plan/understand", json={"text": "qualcosa di caldo a febbraio, 10 giorni"}).json()
    assert j["mode"] == "open" and j["ideas"] and "where" in j["missing"]
    assert client.get("/api/plan/suggest?q=tosc").json()[0]["id"] == "tuscany"
    assert client.post("/api/plan/propose", json={"area": "nowhere"}).status_code == 404


# ---------------------------------------------------------------- routes merged from organised trips (2026-11-12)

def _names(p):
    return [s["name"] for s in p["stops"]]


def test_every_stop_has_its_days_planned_with_several_things_a_day():
    a, only = explore.best_area("Perù")
    p = explore.propose(a, only, 14)
    assert p["days"] == 14
    seen = []
    for s in p["stops"]:
        assert [d["day"] for d in s["plan"]] == list(range(1, s["days"] + 1))
        seen += [n for d in s["plan"] for n in d["sights"]]
    assert len(seen) == len(set(seen)), "a sight is planned once"
    cusco = next(s for s in p["stops"] if s["name"] == "Cusco")
    assert any(len(d["sights"]) >= 3 for d in cusco["plan"]), "a city day sees several things"
    assert "Machu Picchu" in seen and "Colca Canyon" in seen
    # the order trips follow: the coast and Arequipa, then the lake, then Cusco and Machu Picchu
    n = _names(p)
    assert n.index("Arequipa") < n.index("Puno") < n.index("Cusco") < n.index("Aguas Calientes")


def test_order_follows_the_trips_not_a_random_walk():
    a, only = explore.best_area("Italia")
    n = _names(explore.propose(a, only, 10))
    assert {"Rome", "Florence", "Venice"} <= set(n)
    if "Siena" in n:  # Siena sits between Florence and Rome, not after Rome
        assert abs(n.index("Siena") - n.index("Florence")) == 1
    a, only = explore.best_area("Giappone")
    n = _names(explore.propose(a, only, 10))
    assert n.index("Tokyo") < n.index("Kyoto") and n.count("Hiroshima") <= 1


def test_a_ring_starts_and_ends_where_the_flights_are():
    a, only = explore.best_area("Islanda")
    for days in (9, 14):
        p = explore.propose(a, only, days)
        n = _names(p)
        assert n[0] == n[-1] == "Reykjavik", n
        assert p["stops"][-1]["key"] == "is-reykjavik~back"
        assert p["days"] == days
        # round the island, no jumping across the highlands
        assert "Akureyri" in n and ("Höfn" in n or days < 9)


def test_no_trip_counts_in_a_proposal():
    a, only = explore.best_area("Patagonia")
    p = explore.propose(a, only, 14)
    import json
    text = json.dumps(p)
    assert '"trips"' not in text and '"programs"' not in text and '"score"' not in text


def test_stop_panel_shows_what_trips_do_from_a_town():
    from app.guide.todo import todo_for
    t = todo_for("Kyoto", "JP", 35.01, 135.77)
    assert t.source == "trips"
    assert any("Kinkaku-ji" in it.name and " · " in it.name for it in t.items)


# --- the guide written by hand: hour by hour, with what the programmes leave out (Manu, 2026-11-12)

def test_guides_cover_the_four_countries_with_hours_and_sources():
    from app.guide.todo import areas
    by = {}
    for a in areas():
        by.setdefault(a.country, []).append(a)
        assert a.sources
        for it in a.items:
            ats = [x.at for x in it.steps]
            assert ats == sorted(ats), (a.id, it.id)
    for c, n in (("PE", 10), ("CL", 8), ("AR", 9), ("IS", 8)):
        areas_c = by[c]
        assert len(areas_c) >= n, c
        # every area has at least one day hour by hour, and things off the programme somewhere
        assert all(any(it.steps for it in a.items) for a in areas_c), c
        assert sum(len(a.extras) + sum(len(it.extras) for it in a.items) for a in areas_c) >= 2 * n, c


def test_guide_sights_are_places_of_the_globe():
    from app import globe
    from app.guide.todo import areas
    names = {(p["country"], p["name"]) for p in globe.by_id().values()}
    missing = [(a.id, n) for a in areas() for it in a.items for n in it.sights if (a.country, n) not in names]
    assert not missing


def test_peru_days_come_from_the_guide_hour_by_hour():
    a, only = explore.best_area("Perù")
    p = explore.propose(a, only, 21)
    by = {s["name"]: s for s in p["stops"]}
    cusco = by["Cusco"]
    items = [t for d in cusco["plan"] for t in d.get("items", [])]
    assert items and all(t["steps"] for t in items[:3])
    # the dirty data of the trek legs is gone: no Llactapata or Nevado Veronica as a day
    seen = [n for s in p["stops"] for d in s["plan"] for n in d["sights"]]
    assert "Llactapata" not in seen and "Nevado Veronica" not in seen
    # with nights in Ollantaytambo, the Sacred Valley is seen from there, not from Cusco
    if by.get("Ollantaytambo", {}).get("days", 0) >= 2:
        assert not any("Sacred Valley" in t["name"] for t in items)
        valley = [t["name"] for d in by["Ollantaytambo"]["plan"] for t in d.get("items", [])]
        assert any("Pisac" in n for n in valley) and any("Moray" in n for n in valley)
    mapi = by["Aguas Calientes"]
    assert any(t["id"] == "mapi" for d in mapi["plan"] for t in d.get("items", []))


def test_half_days_share_a_day_only_when_their_hours_fit():
    from app.guide.todo import Item
    from app.services.explore import _fits
    am = Item.model_validate({"id": "a", "name": "Boat", "steps": [{"at": "09:30", "what": "Boat out"}, {"at": "13:00", "what": "Boat back"}]})
    pm = Item.model_validate({"id": "b", "name": "Park", "steps": [{"at": "13:30", "what": "Go in"}, {"at": "18:30", "what": "Go out"}]})
    dawn = Item.model_validate({"id": "c", "name": "Lick", "steps": [{"at": "04:30", "what": "Boat up"}, {"at": "10:00", "what": "Boat back"}]})
    loose = Item.model_validate({"id": "d", "name": "Museum"})
    assert _fits([am], pm) and _fits([pm], am)
    assert not _fits([am], dawn)
    assert _fits([am, pm], loose)


def test_no_day_tour_to_where_the_trip_sleeps():
    stops = [
        {"name": "Puerto Natales", "country": "CL", "lat": -51.72, "lon": -72.51, "days": 2, "plan": []},
        {"name": "Torres del Paine National Park", "country": "CL", "lat": -51.0, "lon": -73.05, "days": 3, "plan": []},
    ]
    explore._guide_days(stops)
    natales = [t["id"] for d in stops[0]["plan"] for t in d["items"]]
    park = [t["id"] for d in stops[1]["plan"] for t in d["items"]]
    assert "tdp-day-tour" not in natales
    assert "base-torres" in park
    # a stop of one night gets the thing not to miss, not the evening extra
    one = [{"name": "Höfn", "country": "IS", "lat": 64.25, "lon": -15.21, "days": 1, "plan": []}]
    explore._guide_days([{"name": "Vík í Mýrdal", "country": "IS", "lat": 63.42, "lon": -19.01, "days": 2, "plan": []}, *one])
    assert one[0]["plan"][0]["items"][0]["id"] == "lagoon"


def test_iceland_months_and_whales():
    a, only = explore.best_area("Islanda")
    p = explore.propose(a, only, 14, month=1)
    # whales are out of season in January
    husavik = next((s for s in p["stops"] if s["name"] == "Húsavík"), None)
    if husavik:
        assert not any(t["id"] == "whales" for d in husavik["plan"] for t in d.get("items", []))


def test_board_shows_hours_and_extras_of_the_guide():
    from app.guide.todo import todo_for
    t = todo_for("Cusco", "PE", -13.53, -71.97)
    assert t.source == "guide" and t.extras
    assert any(it.steps for it in t.items)


def test_api_trip_keeps_the_day_of_each_visit(client):
    client.post("/api/auth/guest")
    p = client.post("/api/plan/propose", json={"area": "c-pe", "days": 10}).json()
    stops = p["stops"]
    r = client.post("/api/plan/trip", json={"area": "c-pe", "start_date": "2027-05-03",
                                            "stops": [{**s, "elevation_m": s["elevation_m"] or 100} for s in stops]})
    assert r.status_code == 201, r.text
    t = r.json()
    cusco = next(s for s in t["stops"] if s["name"] == "Cusco")
    dated = [v for v in cusco["visits"] if v.get("date")]
    assert dated and all(cusco["start_date"] <= v["date"] <= cusco["end_date"] for v in dated)
