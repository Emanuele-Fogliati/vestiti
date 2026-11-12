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
