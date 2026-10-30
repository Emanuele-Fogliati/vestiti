"""Ready-made itineraries: data checks, "Pack my bag for this" and the tour links."""
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

from app import inspire
from app.affiliates.networks import network_for
from app.config import Settings

# Rough boxes around each country: a stop outside its box has wrong coordinates.
BOX = {"PE": (-18.5, -0.0, -81.5, -68.5), "AR": (-55.2, -21.7, -73.6, -53.5),
       "CL": (-56.0, -17.4, -76.0, -66.4), "IS": (63.2, 66.6, -24.6, -13.4),
       "VN": (8.4, 23.4, 102.1, 109.5)}


def test_itineraries_load_and_are_consistent():
    its = inspire.itineraries()
    assert {i.slug for i in its} >= {"peru-coast-andes-titicaca", "patagonia-fitz-roy-torres-del-paine",
                                    "iceland-golden-circle-south-coast", "vietnam-north-to-south"}
    for it in its:
        assert 5 <= it.total_days <= 30
        for s in it.stops:
            lat0, lat1, lon0, lon1 = BOX[s.country_code]
            assert lat0 <= s.lat <= lat1 and lon0 <= s.lon <= lon1, s.name
            assert s.plan and len(s.plan) == s.days
            assert s.do, f"{s.name}: say what is worth it"
        for g in it.group_trips:
            assert str(g.url).startswith("https://")


def test_default_start_is_a_good_month_far_enough():
    it = inspire.get("peru-coast-andes-titicaca")
    d = inspire.default_start(it, today=date(2026, 10, 25))
    assert d == date(2027, 5, 1)
    assert inspire.default_start(it, today=date(2027, 5, 10)) == date(2027, 6, 1)
    assert inspire.default_start(it, today=date(2027, 5, 20)) == date(2027, 7, 1)  # June 1 is too close


def test_stops_are_back_to_back_and_visits_on_their_day():
    it = inspire.get("peru-coast-andes-titicaca")
    stops = inspire.stops_for(it, date(2027, 6, 1))
    assert stops[0]["start_date"] == date(2027, 6, 1)
    for a, b in zip(stops, stops[1:]):
        assert (b["start_date"] - a["end_date"]).days == 1
    assert (stops[-1]["end_date"] - stops[0]["start_date"]).days + 1 == it.total_days
    cusco = next(s for s in stops if s["name"] == "Cusco")
    rainbow = next(v for v in cusco["visits"] if v["name"] == "Rainbow Mountain")
    assert rainbow["date"] == cusco["end_date"].isoformat()  # day 3 of 3


def test_list_and_detail(client):
    cards = client.get("/api/inspire").json()
    assert cards[0]["slug"] == "peru-coast-andes-titicaca" and cards[0]["art"]
    d = client.get("/api/inspire/peru-coast-andes-titicaca?start=2027-06-01").json()
    assert d["start_date"] == "2027-06-01" and d["days"] == 15
    by_name = {s["name"]: s for s in d["stops"]}
    assert by_name["Aguas Calientes"]["art"]["id"].endswith("machu-picchu")
    cusco = by_name["Cusco"]
    assert any(v["art"] and v["art"]["id"].endswith("rainbow-mountain") for v in cusco["visits"])
    assert cusco["plan"] and cusco["do"] and cusco["skip"]
    links = cusco["excursions"][0]["links"]
    assert {x["provider"] for x in links} == {"getyourguide", "viator"}
    assert client.get("/api/inspire/nope").status_code == 404


def test_never_says_how_many_organised_trips_include_a_place(client):
    """Manu, 2026-10-26: no "in 39 of 4,916 organised trips" anywhere, not even in the API."""
    for it in client.get("/api/inspire").json():
        d = client.get(f"/api/inspire/{it['slug']}").json()
        assert "inventory_trips" not in d
        assert all("programs" not in s for s in d["stops"])
        assert "organised trips we read" not in str(d).lower()


def test_pack_my_bag_creates_a_trip_ready_for_the_kit(client):
    assert client.post("/api/auth/guest").status_code == 200
    r = client.post("/api/inspire/peru-coast-andes-titicaca/trip", json={"start_date": "2027-06-01"})
    assert r.status_code == 201
    trip = r.json()
    assert trip["start_estimated"] is False and len(trip["stops"]) == 9
    assert trip["stops"][0]["start_date"] == "2027-06-01"
    assert [s["name"] for s in trip["stops"]][:2] == ["Lima", "Paracas"]
    plans = client.get(f"/api/trips/{trip['id']}/plans").json()
    assert plans["tiers"]["medium"]["items"]
    assert trip["id"] in [t["id"] for t in client.get("/api/trips").json()]


def test_pack_without_a_date_is_a_guess(client):
    client.post("/api/auth/guest")
    trip = client.post("/api/inspire/iceland-golden-circle-south-coast/trip", json={}).json()
    assert trip["start_estimated"] is True and trip["estimate"]["start"] is True
    assert date.fromisoformat(trip["stops"][0]["start_date"]).month in (6, 7, 8)


def test_pack_needs_a_user(client):
    client.cookies.clear()
    assert client.post("/api/inspire/vietnam-north-to-south/trip", json={}).status_code == 401


@pytest.mark.parametrize("provider,host", [("getyourguide", "www.getyourguide.com"), ("viator", "www.viator.com")])
def test_excursion_link_goes_to_the_marketplace_search(client, provider, host):
    r = client.get(f"/api/go/excursion/peru-coast-andes-titicaca/6/0?provider={provider}", follow_redirects=False)
    assert r.status_code == 302
    u = urlparse(r.headers["location"])
    assert u.netloc == host and "Rainbow" in r.headers["location"]


def test_excursion_and_tour_links_only_from_our_data(client):
    base = "/api/go/excursion/peru-coast-andes-titicaca"
    assert client.get(f"{base}/99/0", follow_redirects=False).status_code == 404
    assert client.get(f"{base}/0/99", follow_redirects=False).status_code == 404
    assert client.get(f"{base}/0/0?provider=evil.example", follow_redirects=False).status_code == 404
    r = client.get("/api/go/tour/peru-coast-andes-titicaca/0", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://www.intrepidtravel.com/")
    assert client.get("/api/go/tour/peru-coast-andes-titicaca/9", follow_redirects=False).status_code == 404


def test_tour_networks_track_only_when_configured():
    url = "https://www.getyourguide.com/s/?q=Cusco"
    assert network_for("getyourguide", Settings()).build(url, "c1").tracked is False
    g = network_for("getyourguide", Settings(getyourguide_partner_id="ABC123")).build(url, "c1")
    q = parse_qs(urlparse(g.url).query)
    assert g.tracked and q["partner_id"] == ["ABC123"] and q["cmp"] == ["c1"] and q["q"] == ["Cusco"]
    v_url = "https://www.viator.com/searchResults/all?text=Cusco"
    assert network_for("viator", Settings(viator_pid="P001")).build(v_url, "c1").tracked is False  # mcid missing
    v = network_for("viator", Settings(viator_pid="P001", viator_mcid="42383")).build(v_url, "c1")
    q = parse_qs(urlparse(v.url).query)
    assert v.tracked and q["pid"] == ["P001"] and q["mcid"] == ["42383"] and q["campaign"] == ["c1"]
