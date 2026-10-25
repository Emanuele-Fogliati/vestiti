"""No place shows up in the wrong country: verified registry, trip-level checks, the API's
"Is this the place?" flag, and the audit. The known bad cases are here: Aguas Calientes and
Machu Picchu geocoded to Mexico, Titicaca to an Amazon village at 234 m."""
import json

import httpx
import pytest

from app.config import get_settings
from app.places import audit, countries, registry
from app.places.verify import check_stops, expected_countries
from app.weather import geocode


def _r(name, admin, cc, lat, lon, pop=0, feature="PPL", elev=0):
    return {"name": name, "admin1": admin, "country_code": cc, "country": cc, "latitude": lat,
            "longitude": lon, "elevation": elev, "population": pop, "feature_code": feature}


# what GeoNames answers worldwide, and inside one country
WORLD = {
    "Aguas Calientes": [_r("Aguas Calientes", "Guerrero", "MX", 16.84, -99.64, 1660),
                        _r("Aguas Calientes", "Chihuahua", "MX", 28.4, -106.0, 500)],
    "Machu Picchu": [_r("Machu Picchu", "Washington", "US", 47.41, -121.67, 0)],
    "Titicaca": [_r("Titicaca", "San Martín", "PE", -7.2, -76.7, 300, elev=234)],
    "Santa Teresa": [_r("Santa Teresa", "Espírito Santo", "BR", -19.93, -40.6, 21_000),
                     _r("Santa Teresa", "Nayarit", "MX", 22.48, -104.73, 900)],
    "Chucuito": [_r("Chucuito", "Loreto", "PE", -4.1, -73.3, 900, elev=110),
                 _r("Chucuito", "Puno", "PE", -15.89, -69.89, 1000, elev=3875)],
    "Zorritos": [_r("Zorritos", "Tumbes", "PE", -3.68, -80.68, 12_000)],
    "Kyoto Station": [_r("Kyoto Station", "Kyoto", "JP", 34.98, 135.76, 0)],
}
IN_COUNTRY = {
    ("Santa Teresa", "PE"): [_r("Santa Teresa", "Cusco", "PE", -13.13, -72.6, 6000, elev=1550)],
}


def _transport(seen=None):
    def handle(req):
        q, cc = req.url.params["name"], req.url.params.get("countryCode")
        if seen is not None:
            seen.append((q, cc))
        res = IN_COUNTRY.get((q, cc), []) if cc else WORLD.get(q, [])
        if cc and not res:
            res = [x for x in WORLD.get(q, []) if x["country_code"] == cc]
        return httpx.Response(200, json={"results": res})
    return httpx.MockTransport(handle)


@pytest.fixture
def online(monkeypatch):
    s = get_settings().model_copy(update={"weather_enabled": True})
    monkeypatch.setattr(geocode, "get_settings", lambda: s)
    geocode._cache.clear()


# ------------------------------------------------------------------ the registry
def test_every_registry_place_is_verified_with_an_iso_country_and_sources():
    rows = json.loads(registry.SEED.read_text(encoding="utf-8"))["places"]
    ids = [p["id"] for p in rows]
    assert len(ids) == len(set(ids))
    by_id = {p["id"]: p for p in rows}
    for p in rows:
        assert countries.is_code(p["country_code"]), p["id"]
        assert p["id"].startswith(p["country_code"].lower() + "-"), p["id"]
        assert p["latitude"] is not None and (p.get("elevation_m") is not None or p["kind"] == "region"), p["id"]
        v = p.get("verified") or {}
        assert v.get("ok") is True and len(v.get("sources", [])) >= 2, (p["id"], v)
        if p.get("base"):  # a sight's town is in the same country
            assert by_id[p["base"]]["country_code"] == p["country_code"], p["id"]


def test_the_known_bad_cases_are_pinned_to_peru():
    mp = registry.lookup("Machu Picchu")
    assert [p.country_code for p in mp] == ["PE"]
    at = registry.as_result(mp[0], "Machu Picchu")
    assert at["country_code"] == "PE" and at["base"] == "Aguas Calientes"
    assert 1800 < at["elevation_m"] < 2300  # you sleep in Aguas Calientes, not on the summit
    assert {p.country_code for p in registry.lookup("Aguas Calientes")} == {"PE"}
    # Titicaca is shared: one entry per side of the border, never the Amazon village
    assert {p.country_code for p in registry.lookup("Lago Titicaca")} == {"PE", "BO"}
    for p in registry.lookup("Titicaca"):
        assert registry.as_result(p)["elevation_m"] > 3700


# ------------------------------------------------------------------ countries in the text
def test_countries_named_in_a_trip_text():
    assert set(countries.mentioned("Viaggio in Perù e Bolivia, 15 giorni")) == {"PE", "BO"}
    assert set(countries.mentioned("Patagonia Express")) == {"AR", "CL"}
    assert set(countries.mentioned("Trip to Peru and Bolivia")) == {"PE", "BO"}
    assert not countries.mentioned("mali di stagione")  # Italian word, not the country


def test_home_country_in_the_text_is_not_a_trip_country():
    text = "Partenza dall'Italia con volo per Lima. Perù e Bolivia in 15 giorni."
    exp = expected_countries(text, ["PE", "PE"], [{"PE", "US"}, {"PE"}, {"BO", "BR"}])
    assert exp == {"PE", "BO"}


# ------------------------------------------------------------------ geocoding a trip
def test_aguas_calientes_and_machu_picchu_never_go_to_mexico(online):
    with httpx.Client(transport=_transport()) as c:
        found, checks, cc = geocode.resolve_and_check(
            ["Lima", "Cusco", "Aguas Calientes", "Machu Picchu", "Titicaca"], client=c)
    assert [m[0]["country_code"] for m in found] == ["PE"] * 5
    assert all(ch.status == "ok" for ch in checks)
    assert cc == {"PE"}
    # alone, too: a one-stop trip has no neighbours to vote
    with httpx.Client(transport=_transport()) as c:
        assert geocode.resolve_trip(["Machu Picchu"], client=c)[0][0]["country_code"] == "PE"
        assert geocode.resolve_trip(["Aguas Calientes"], client=c)[0][0]["country_code"] == "PE"


def test_titicaca_is_the_lake_not_the_amazon_village(online):
    with httpx.Client(transport=_transport()) as c:
        found = geocode.resolve_trip(["Cusco", "Titicaca"], client=c)
    t = found[1][0]
    assert t["country_code"] == "PE" and t["elevation_m"] > 3700 and t["latitude"] < -15


def test_a_name_unknown_to_the_registry_is_searched_inside_the_trip_country(online):
    seen = []
    with httpx.Client(transport=_transport(seen)) as c:
        found, checks, _ = geocode.resolve_and_check(["Cusco", "Santa Teresa", "Aguas Calientes"], client=c)
    st = found[1][0]
    assert (st["country_code"], st["admin"]) == ("PE", "Cusco")
    assert ("Santa Teresa", "PE") in seen
    assert checks[1].status == "ok"


def test_the_altitude_in_the_program_picks_the_right_homonym(online):
    with httpx.Client(transport=_transport()) as c:
        found, checks, _ = geocode.resolve_and_check(["Puno", "Chucuito", "Copacabana"], client=c,
                                                     altitudes=[3830, 3870, 3840])
    assert found[1][0]["admin"] == "Puno"
    assert checks[1].status == "ok"


def test_what_cannot_be_fixed_is_flagged_never_shown_as_right(online):
    with httpx.Client(transport=_transport()) as c:
        found, checks, _ = geocode.resolve_and_check(
            ["Lima", "Cusco", "Kyoto Station", "Puno"], client=c, text="Viaggio in Perù")
    assert found[2][0]["country_code"] == "JP"  # the only match there is: kept, but...
    assert checks[2].status == "check"
    assert set(checks[2].codes) >= {"country", "far"}
    assert "Japan" in " ".join(checks[2].issues)
    assert [ch.status for i, ch in enumerate(checks) if i != 2] == ["ok"] * 3


def test_far_but_same_country_is_fine_when_near_a_neighbour():
    stops = [{"name": "Lima", "country_code": "PE", "latitude": -12.05, "longitude": -77.04, "elevation_m": 150},
             {"name": "Zorritos", "country_code": "PE", "latitude": -3.68, "longitude": -80.68, "elevation_m": 10},
             {"name": "Cusco", "country_code": "PE", "latitude": -13.53, "longitude": -71.97, "elevation_m": 3400}]
    assert [c.status for c in check_stops(stops)] == ["ok"] * 3


# ------------------------------------------------------------------ the API
PERU = {"name": "Peru", "countries": ["PE"], "stops": [
    {"name": "Lima", "country_code": "PE", "latitude": -12.05, "longitude": -77.04, "elevation_m": 150,
     "start_date": "2027-05-01", "end_date": "2027-05-02"},
    {"name": "Cusco", "country_code": "PE", "latitude": -13.53, "longitude": -71.97, "elevation_m": 3400,
     "start_date": "2027-05-03", "end_date": "2027-05-05"},
    {"name": "Aguas Calientes", "country_code": "MX", "latitude": 16.84, "longitude": -99.64, "elevation_m": 34,
     "start_date": "2027-05-06", "end_date": "2027-05-06"},
]}


def test_a_stop_in_the_wrong_country_is_asked_about_until_confirmed(client):
    assert client.post("/api/auth/guest").status_code == 200
    t = client.post("/api/trips", json=PERU).json()
    assert t["countries"] == ["PE"]
    st = {s["name"]: s for s in t["stops"]}
    assert st["Lima"]["place_status"] == st["Cusco"]["place_status"] == "ok"
    ac = st["Aguas Calientes"]
    assert ac["place_status"] == "check" and "Mexico" in ac["place_note"]
    # the traveller fixes it: picks the Peruvian one -> checked again, now fine
    fixed = client.patch(f"/api/trips/{t['id']}/stops/{ac['id']}", json={
        "country_code": "PE", "latitude": -13.155, "longitude": -72.525, "elevation_m": 2040}).json()
    assert fixed["place_status"] == "ok" and fixed["place_note"] is None
    # or says "yes, it's right": it stays confirmed, whatever the checks say
    client.patch(f"/api/trips/{t['id']}/stops/{ac['id']}", json={
        "country_code": "MX", "latitude": 16.84, "longitude": -99.64})
    again = client.get(f"/api/trips/{t['id']}").json()
    assert next(s for s in again["stops"] if s["id"] == ac["id"])["place_status"] == "check"
    ok = client.patch(f"/api/trips/{t['id']}/stops/{ac['id']}", json={"place_confirmed": True}).json()
    assert ok["place_status"] == "confirmed"
    trip = client.get(f"/api/trips/{t['id']}").json()
    assert next(s for s in trip["stops"] if s["id"] == ac["id"])["place_status"] == "confirmed"


def test_adding_a_far_stop_by_hand_is_checked(client):
    assert client.post("/api/auth/guest").status_code == 200
    t = client.post("/api/trips", json={**PERU, "stops": PERU["stops"][:2]}).json()
    s = client.post(f"/api/trips/{t['id']}/stops", json={
        "name": "Machu Picchu", "country_code": "US", "latitude": 47.41, "longitude": -121.67,
        "elevation_m": 1500, "start_date": "2027-05-06", "end_date": "2027-05-06"}).json()
    assert s["place_status"] == "check"


def test_parse_reads_the_trip_in_its_country_offline(client):
    assert client.post("/api/auth/guest").status_code == 200
    r = client.post("/api/ai/parse-itinerary",
                    json={"text": "Perù: Lima, Cusco, Machu Picchu, Titicaca"}).json()
    assert [s["place"]["country_code"] for s in r["stops"]] == ["PE"] * 4
    assert all(s["check"]["status"] == "ok" for s in r["stops"])
    assert r["countries"] == ["PE"]


# ------------------------------------------------------------------ the audit
class FakeSources:
    """What the public sources would say, without network."""
    def __init__(self, osm="PE", ground=3400.0, hits=None):
        self.osm, self.ground, self.hits = osm, ground, hits

    def osm_country(self, lat, lon):
        return self.osm

    def geonames(self, name, country=None, count=10):
        if country is None:
            return [{"country_code": "MX"}]
        return self.hits if self.hits is not None else [
            {"id": 1, "name": name, "country_code": country, "latitude": -13.52, "longitude": -71.97}]

    def osm_search(self, name, country, limit=5, kind=None):
        return []

    def srtm(self, points):
        return [self.ground for _ in points]


CUSCO = {"id": "pe-cusco", "name": "Cusco", "kind": "town", "country_code": "PE",
         "latitude": -13.53, "longitude": -71.97, "elevation_m": 3400, "aliases": []}


def test_audit_verifies_a_good_place_and_names_its_homonyms_abroad():
    r = audit.check_place(CUSCO, FakeSources())
    assert r["ok"] and len(r["sources"]) >= 2
    assert "same name also in MX" in r["notes"]


def test_audit_flags_coordinates_in_another_country():
    r = audit.check_place({**CUSCO, "latitude": 16.84, "longitude": -99.64}, FakeSources(osm="MX"))
    assert not r["ok"]
    assert any("Mexico" in p for p in r["problems"])
    assert any("km away" in p for p in r["problems"])  # and no Peruvian Cusco near there


def test_audit_flags_a_wrong_elevation_and_an_unknown_name():
    assert not audit.check_place({**CUSCO, "elevation_m": 234}, FakeSources())["ok"]
    r = audit.check_place(CUSCO, FakeSources(hits=[]))
    assert not r["ok"] and any("no source knows" in p for p in r["problems"])


def test_audit_reads_the_landmark_catalog_with_country_codes():
    arts = audit.art_places()
    assert arts and all(countries.is_code(a["country_code"]) for a in arts)
    assert any(a["id"] == "pe-machu-picchu" for a in arts)


def test_a_stop_in_another_country_never_gets_a_peruvian_landmark():
    from app.art import match
    assert match("Aguas Calientes", -13.155, -72.525, country="PE").id.endswith("machu-picchu")
    assert match("Aguas Calientes", 16.84, -99.64, country="MX") is None
