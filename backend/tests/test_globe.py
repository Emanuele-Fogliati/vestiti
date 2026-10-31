"""Globe places: one compact response, every place inside its own country, pictures only for named places."""
import gzip
import json

from app import globe


def test_places_endpoint_is_compact_and_gzipped(client):
    r = client.get("/api/globe/places", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    # revalidated every time, so new landmark scenes reach the globe at once; 304 when unchanged
    assert r.headers["cache-control"] == "no-cache" and r.headers["etag"]
    again = client.get("/api/globe/places", headers={"Accept-Encoding": "gzip", "If-None-Match": r.headers["etag"]})
    assert again.status_code == 304
    d = r.json()  # the test client decompresses
    assert d["fields"][:7] == ["id", "name", "country", "kind", "lat", "lon", "level"]
    assert len(d["places"]) > 1000
    # never how many organised trips include a place, nor how many we read (Manu, 2026-10-26)
    assert "inventory_trips" not in d and "trips" not in d["fields"]
    raw, gz = globe.payload_bytes()
    assert json.loads(gzip.decompress(gz)) == json.loads(raw)
    # 250 KB until 31 Oct; raised because every new landmark scene adds its id to some places
    assert len(gz) < 300_000  # stays light enough for a phone


def test_places_have_valid_rows():
    d = globe.payload()
    kinds = {"city", "town", "landmark", "nature", "island", "region"}
    ids = set()
    for pid, name, cc, kind, lat, lon, lvl, art, art_label, its, _parent in d["places"]:
        assert pid not in ids
        ids.add(pid)
        assert name and len(cc) == 2 and cc.isupper() and kind in kinds
        assert -90 <= lat <= 90 and -180 <= lon <= 180
        assert lvl in range(1, 7)
        assert (art is None) == (art_label is None)
        assert all(0 <= i < len(d["itineraries"]) for i in its)
    # most visited first
    levels = [p[6] for p in d["places"]]
    assert levels == sorted(levels, reverse=True)
    assert levels[0] == 6 and levels[-1] == 1


def test_popularity_levels():
    assert [globe.level(t) for t in (109, 60, 59, 30, 15, 8, 5, 4, 3)] == [6, 6, 5, 5, 4, 3, 2, 1, 1]


def test_cusco_gets_its_picture_and_itinerary_but_not_its_neighbours():
    d = globe.payload()
    by_id = {p[0]: p for p in d["places"]}
    cusco = by_id["pe-cusco"]
    assert cusco[2] == "PE" and abs(cusco[4] + 13.53) < 0.1 and abs(cusco[5] + 71.97) < 0.1
    assert cusco[7] is not None and "cusco" in cusco[7]
    assert any(d["itineraries"][i]["slug"].startswith("peru") for i in cusco[9])
    # a place near Cusco with no scene of its own gets no picture (no borrowed landmark)
    assert by_id["pe-sacsayhuaman"][7] is None


# ---- places inside a city (Manu, 2026-10-26): Florence from far away, its sights up close


def test_sights_belong_to_their_city():
    b = globe.by_id()
    parent = lambda pid: b[pid]["parent"]  # noqa: E731
    for sight in ("it-uffizi-gallery", "it-ponte-vecchio", "it-boboli-gardens", "it-florence-cathedral"):
        assert parent(sight) == "it-florence", sight
    assert parent("pe-qorikancha") == parent("pe-sacsayhuaman") == "pe-cusco"
    assert parent("fr-eiffel-tower") == "fr-paris"
    # a city state is part of the city around it, and its sights go to that city too
    assert parent("va-vatican-city") == parent("va-st-peters-basilica") == "it-rome"
    # cities and places that are destinations of their own stay on the world view
    for top in ("it-florence", "it-rome", "pe-cusco", "pe-machu-picchu", "jo-petra"):
        assert top not in b or parent(top) is None, top
    # one level only, always a city or town, always in the same country or the city-state rule
    for p in b.values():
        if p["parent"]:
            c = b[p["parent"]]
            assert c["parent"] is None and c["kind"] in ("city", "town"), p["id"]


def test_hierarchy_rules():
    from app.globe.hierarchy import parents
    city = {"id": "c", "kind": "city", "country": "IT", "lat": 43.77, "lon": 11.256, "trips": 50}
    near = {"id": "s", "kind": "landmark", "country": "IT", "lat": 43.768, "lon": 11.25, "trips": 10}
    big = {"id": "b", "kind": "landmark", "country": "IT", "lat": 43.78, "lon": 11.26, "trips": 80}
    far = {"id": "f", "kind": "landmark", "country": "IT", "lat": 44.2, "lon": 11.256, "trips": 5}
    other = {"id": "o", "kind": "landmark", "country": "FR", "lat": 43.77, "lon": 11.257, "trips": 5}
    assert parents([city, near, big, far, other]) == {"s": "c"}


def test_trip_from_picks(client):
    client.post("/api/auth/guest")
    picks = ["it-uffizi-gallery", "it-rome", "it-ponte-vecchio", "it-florence"]
    res = client.post("/api/globe/trip", json={"places": picks, "month": 5})
    assert res.status_code == 201, res.text
    t = res.json()
    stops = t["stops"]
    # the sights are visits of the city you sleep in; cities in the order of the first pick
    assert [s["name"] for s in stops] == ["Florence", "Rome"]
    assert [v["name"] for v in stops[0]["visits"]] == ["Uffizi Gallery", "Ponte Vecchio"]
    assert stops[1]["visits"] == []
    assert stops[0]["start_date"].startswith(("2026-05", "2027-05", "2028-05"))
    assert t["start_estimated"] is True and t["estimate"]["days"] is True
    assert all("city" in [a["type"] for a in s["activities"]] for s in stops)
    # a sight alone: the trip stops in its city, with that one sight
    only = client.post("/api/globe/trip", json={"places": ["pe-qorikancha"]}).json()["stops"]
    assert [(s["name"], [v["name"] for v in s["visits"]]) for s in only] == [("Cusco", ["Qorikancha"])]
    assert only[0]["elevation_m"] > 3000  # Cusco's altitude, for the kit


def test_trip_from_picks_errors(client):
    client.post("/api/auth/guest")
    assert client.post("/api/globe/trip", json={"places": []}).status_code == 422
    assert client.post("/api/globe/trip", json={"places": ["nope"]}).status_code == 404
    many = [p["id"] for p in globe.by_id().values() if p["parent"] is None][:21]
    assert client.post("/api/globe/trip", json={"places": many}).status_code == 422
    client.cookies.clear()
    assert client.post("/api/globe/trip", json={"places": ["it-florence"]}).status_code == 401


def test_sights_inside_a_city_have_their_own_spot():
    b = globe.by_id()
    spots = {(b[i]["lat"], b[i]["lon"]) for i in ("it-uffizi-gallery", "it-palazzo-vecchio", "it-florence-cathedral",
                                                 "it-florence-baptistery", "it-ponte-vecchio")}
    assert len(spots) == 5  # not one dot for all of them (the trip reading rounds to ~1 km)
    for p in b.values():  # an exact position never moves a place far from where the trips put it
        assert abs(p["lat"]) <= 90 and abs(p["lon"]) <= 180
