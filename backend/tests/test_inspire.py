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
       "VN": (8.4, 23.4, 102.1, 109.5), "JP": (24.0, 45.6, 122.9, 146.0), "NA": (-29.0, -16.9, 11.7, 25.3),
       "NZ": (-47.4, -34.3, 166.3, 178.6), "BO": (-22.9, -9.6, -69.7, -57.4),
       "NO": (57.9, 71.2, 4.5, 31.2), "TZ": (-11.8, -0.9, 29.3, 40.5), "MA": (27.6, 36.0, -13.2, -1.0),
       "NP": (26.3, 30.5, 80.0, 88.3), "CH": (45.8, 47.9, 5.9, 10.5), "AT": (46.3, 49.1, 9.5, 17.2)}
# Rapa Nui is Chile too, 3,700 km out in the Pacific
ISLANDS = {("CL", "Hanga Roa"): (-27.3, -27.0, -109.5, -109.2)}


def test_itineraries_load_and_are_consistent():
    its = inspire.itineraries()
    assert {i.slug for i in its} >= {"peru-coast-andes-titicaca", "patagonia-fitz-roy-torres-del-paine",
                                    "iceland-golden-circle-south-coast", "vietnam-north-to-south"}
    for it in its:
        assert 5 <= it.total_days <= 31
        for s in it.stops:
            lat0, lat1, lon0, lon1 = ISLANDS.get((s.country_code, s.name), BOX[s.country_code])
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
    # the recommended library is listed; the four older hand-written ones only open by link
    slugs = {c["slug"] for c in cards}
    assert "peru-14" in slugs and "peru-coast-andes-titicaca" not in slugs
    assert all(c["weeks"] in (1, 2, 3, 4) and c["months"] and c["destination"] and c["journey"] for c in cards)
    # one card per travel region (Manu, 2026-11-16: not the same trip once per length)
    leads = [c for c in cards if c["lead"]]
    assert len(leads) == len({c["journey"] for c in cards}) == 14
    assert all(c["weeks"] == 2 for c in leads)
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
    mine = next(t for t in client.get("/api/trips").json() if t["id"] == trip["id"])
    # each stop's drawing, in order, for the map (Manu 2026-11-16: drawings, not black dots)
    assert len(mine["arts"]) == len(mine["points"]) == 9
    assert mine["arts"][0]["id"] == mine["art"]["id"] and sum(a is not None for a in mine["arts"]) >= 7


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


def test_regions_cross_borders_and_each_month_has_one_route_per_length():
    """Manu, 2026-11-16: travel regions as tour operators cut them, across borders (Patagonia is
    Chile and Argentina), 1 to 4 weeks, the season deciding the route; a month with no good
    route for a length has none, rather than a bad one."""
    from collections import defaultdict
    by = defaultdict(list)
    for it in inspire.itineraries():
        if it.listed and it.weeks:
            by[it.region].append(it)
    assert len(by) == 14  # + Norway, Tanzania, Morocco, Nepal (2026-11-16)
    for region, its in by.items():
        weeks = {i.weeks for i in its}
        assert {1, 2} <= weeks, region
        for w in weeks:
            ms = [m for i in its if i.weeks == w for m in i.months]
            assert len(ms) == len(set(ms)), (region, w)  # one route per month and length
        assert any(i.best_months for i in its), region
    lands = {r: {c for i in its for c in i.countries} for r, its in by.items()}
    assert lands["patagonia"] == {"AR", "CL"} and lands["andes"] == {"AR", "BO", "CL"}
    assert lands["peru-bolivia"] == {"PE", "BO"} and lands["lakes"] == {"AR", "CL"}


def test_region_page_lists_its_lengths_and_seasons(client):
    d = client.get("/api/inspire/patagonia-14?month=1").json()
    j = d["journey"]
    assert j["name"] == "Patagonia" and j["countries"] == ["AR", "CL"]
    assert sorted({r["weeks"] for r in j["routes"]}) == [1, 2, 3, 4]
    winter = next(r for r in j["routes"] if r["weeks"] == 2 and 7 in r["months"])
    assert winter["slug"] == "patagonia-14-winter" and winter["best_months"] == []


def test_what_to_wear_follows_the_month(client):
    jul = client.get("/api/inspire/peru-14?month=7").json()
    jan = client.get("/api/inspire/peru-14?month=1").json()
    assert jul["start_date"].split("-")[1] == "07" and jul["wear"]["month"] == 7
    names = lambda d: {p["name"] for p in d["wear"]["pieces"]}  # noqa: E731
    assert "Warm down jacket" in names(jul)  # Puno and the Colca at dawn, -5 C
    assert jan["wear"]["rain"] > jul["wear"]["rain"]  # the wet season
    assert any("Waterproof" in n for n in names(jan))
    assert client.get("/api/inspire/peru-14?month=13").status_code == 422


def test_recommended_clothes_are_not_an_expedition():
    """Opus check of all 432 trip-months (2026-11-16): no thick down jacket where it is not
    cold, no rain jacket in a dry month, no rain trousers in warm rain."""
    from app.inspire import wear
    for slug, month in (("buenos-aires-7", 7), ("patagonia-14", 1), ("namibia-14", 7),
                        ("vietnam-7", 7), ("japan-14", 8)):
        w = wear.for_itinerary(inspire.get(slug), month)
        names = {p["name"] for p in w["pieces"]}
        assert "Thick down jacket" not in names and "Lined winter trousers" not in names, (slug, names)
        if w["rain"] < 15:
            assert "Rain jacket" not in names, slug
    hot = {p["name"] for p in wear.for_itinerary(inspire.get("vietnam-7"), 7)["pieces"]}
    assert "Rain trousers" not in hot


def test_pack_in_a_month_starts_that_month(client):
    client.post("/api/auth/guest")
    trip = client.post("/api/inspire/japan-14/trip", json={"month": 4}).json()
    assert date.fromisoformat(trip["stops"][0]["start_date"]).month == 4


def test_every_day_of_a_recommended_trip_comes_from_its_zone_guide():
    """Manu 2026-11-16: "come faccio a vedere che cosa fare nei 4 giorni a El Chaltén?"."""
    from app import trails
    from app.inspire import days
    for it in inspire.itineraries():
        if not it.weeks:
            continue
        for s in it.stops:
            assert s.area and len(s.day_plans) == s.days, (it.slug, s.name)
            known = days._items()[s.area]
            for d in s.day_plans:
                assert all(x in known for x in d.things + ([d.spare] if d.spare else [])), (it.slug, s.name, d)
    for items in days._items().values():
        for x in items.values():
            assert x.trail is None or trails.find(x.trail), x.id


def test_a_fitz_roy_day_is_dressed_apart_from_a_town_day(client):
    j = client.get("/api/inspire/patagonia-14?month=1").json()
    chalten = next(s for s in j["stops"] if s["name"] == "El Chaltén")
    assert [d["kind"] for d in chalten["days"]] == ["arrive", "day", "day", "free"]
    fitz = chalten["days"][1]
    walk = fitz["things"][0]
    assert walk["id"] == "laguna-de-los-tres" and walk["trail"]["id"] == "ar-laguna-de-los-tres" and walk["steps"]
    assert "Hiking boots" in fitz["wear"]
    town = j["stops"][0]["days"][0]  # El Calafate, the day you land
    assert "Hiking boots" not in town["wear"]
    spare = chalten["days"][3]
    assert spare["things"][0]["spare"] and spare["things"][0]["trail"]


def test_torres_del_paine_is_where_you_sleep_not_on_the_ice_field(client):
    j = client.get("/api/inspire/patagonia-14?month=1").json()
    tdp = next(s for s in j["stops"] if s["name"].startswith("Torres del Paine"))
    assert tdp["days"][0]["low"] >= 5  # January on the east side, not 1 °C on the ice
    assert all("Warm down jacket" not in d["wear"] for d in tdp["days"])


def test_any_number_of_days_cuts_or_stretches_the_nearest_route(client):
    """Manu 2026-11-16: "anche volendo 17 giorni, 10 giorni"."""
    j = client.get("/api/inspire/patagonia-14?month=1&days=10").json()
    names = [s["name"] for s in j["stops"]]
    assert j["days"] == 10 and sum(len(s["days"]) for s in j["stops"]) == 10
    assert "El Chaltén" in names and "Ushuaia" not in names  # a line ends sooner, Fitz Roy stays
    j = client.get("/api/inspire/patagonia-14?month=1&days=17").json()
    assert j["days"] == 17 and j["journey"]["id"] == "patagonia"
    # Buenos Aires & Iguazú goes up to three weeks: it stretches, never past what the zones hold
    j = client.get("/api/inspire/buenos-aires-14?month=1&days=35").json()
    assert 21 < j["days"] < 35
    iceland = client.get("/api/inspire/iceland-14?month=7&days=10").json()
    assert iceland["stops"][0]["name"] == iceland["stops"][-1]["name"]  # the ring still comes home
    assert client.get("/api/inspire/patagonia-14?month=1&days=99").status_code == 422
    client.post("/api/auth/guest")
    trip = client.post("/api/inspire/patagonia-14/trip", json={"month": 1, "days": 10}).json()
    assert sum((date.fromisoformat(s["end_date"]) - date.fromisoformat(s["start_date"])).days + 1
               for s in trip["stops"]) == 10


def test_a_recommended_trip_is_edited_on_its_own_page(client):
    """Manu 2026-11-16: "da qui stesso posso direttamente editare il viaggio": days per stop, a stop
    out, any place of the globe in; the days come from the guides, and the trip keeps the edit."""
    edit = "ar-el-calafate:2,ar-el-chalten:5,cl-puerto-natales:1,cl-torres-del-paine-national-park:3"
    it = client.get(f"/api/inspire/patagonia-14?month=1&stops={edit}").json()
    assert it["days"] == 11 and [s["place"] for s in it["stops"]] == [p.split(":")[0] for p in edit.split(",")]
    assert [len(s["days"]) for s in it["stops"]] == [2, 5, 1, 3]
    assert client.get("/api/inspire/patagonia-14?month=1&stops=ar-el-calafate:2,xx-nowhere:3").status_code == 422
    assert client.get("/api/inspire/patagonia-14?month=1&stops=ar-el-calafate:40").status_code == 422
    client.post("/api/auth/guest")
    trip = client.post("/api/inspire/patagonia-14/trip", json={
        "month": 1, "stops": [["ar-el-calafate", 2], ["ar-el-chalten", 5], ["cl-puerto-natales", 1]]}).json()
    assert [s["name"] for s in trip["stops"]] == ["El Calafate", "El Chaltén", "Puerto Natales"]
    assert trip["stops"][0]["start_date"][5:7] == "01" and trip["start_estimated"] is True  # a date of ours


def test_the_bag_on_the_trip_page_follows_the_route(client):
    """Manu 2026-11-16: the clothes sit under the route on the same page and change with it: the
    same trip is updated, its stops replaced, what you said you have kept; nobody else's trip."""
    client.post("/api/auth/guest")
    t = client.post("/api/inspire/patagonia-14/trip", json={"month": 1}).json()
    client.put(f"/api/trips/{t['id']}/selections", json={"tier": "medium", "slot": "headwear", "choice": "have"})
    again = client.post("/api/inspire/patagonia-14/trip", json={
        "month": 7, "trip_id": t["id"], "stops": [["ar-el-calafate", 2], ["ar-el-chalten", 3]]}).json()
    assert again["id"] == t["id"] and [s["name"] for s in again["stops"]] == ["El Calafate", "El Chaltén"]
    assert again["stops"][0]["start_date"][5:7] == "07"
    assert any(x["slot"] == "headwear" and x["kind"] == "have" for x in client.get(f"/api/trips/{t['id']}/plans").json()["tiers"]["medium"]["items"])
    client.post("/api/auth/logout")
    client.post("/api/auth/guest")
    other = client.post("/api/inspire/patagonia-14/trip", json={"month": 1, "trip_id": t["id"]}).json()
    assert other["id"] != t["id"]


def test_every_region_has_a_trip_for_every_month_of_every_length():
    """Manu 2026-11-16: "per ogni mese ... chiunque voglia andare in qualunque posto, in qualunque
    momento, abbia il suo outfit": every travel region, 1 to 4 weeks, a route in all twelve months
    (another route where the season changes it), never a month with nothing."""
    from collections import defaultdict
    from app.guide import ready
    cover = defaultdict(set)
    for t in ready.trips():
        if t.journey:
            cover[(t.journey, round(t.days / 7))] |= set(t.months)
    gaps = {k: sorted(set(range(1, 13)) - v) for k, v in cover.items() if v != set(range(1, 13))}
    assert not gaps, gaps
    for m in range(1, 13):
        assert inspire.custom("lakes", 10, m) is not None and inspire.custom("andes", 17, m) is not None


def test_iceland_in_winter_stays_in_the_south():
    """The operators' winter and aurora trips stay in the south and west (17 of 19), and so do ours."""
    from app.guide import ready
    north = {"is-akureyri", "is-lake-myvatn", "is-husavik", "is-seydisfjordur", "is-isafjordur"}
    for t in ready.trips():
        if t.journey == "iceland" and 1 in t.months:
            assert not north & {s.place for s in t.stops}, t.id
