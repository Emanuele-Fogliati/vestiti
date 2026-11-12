"""The trip board (Manu, 2026-11-12): things to do in order, the day plan against the weather,
the legs and flights between stops, and changes that never move what is booked."""
from datetime import date, timedelta

import httpx

from app import travel
from app.engine.strategy import DayWeather
from app.guide import todo
from app.services.dayplan import plan_days, sky_of

START = date(2027, 1, 14)


def day(i, sky="unknown", prob=30.0):
    d = START + timedelta(days=i)
    if sky == "unknown":
        return DayWeather(d, 14, 4, 1.0, prob, 30, source="climate")
    return {
        "clear": DayWeather(d, 15, 5, 0.0, 5, 20, source="forecast", cloud=20),
        "cloud": DayWeather(d, 12, 5, 0.2, 30, 25, source="forecast", cloud=90),
        "rain": DayWeather(d, 9, 4, 12.0, 90, 30, source="forecast", cloud=100),
        "wind": DayWeather(d, 11, 3, 0.0, 10, 60, source="forecast", gust_kmh=95, cloud=50),
    }[sky]


def tdp():
    return todo.area_for("Torres del Paine", "CL", None, None)


# ---------------------------------------------------------------- things to do

def test_areas_are_written_with_sources_and_valid_items():
    areas = todo.areas()
    assert len(areas) >= 9
    for a in areas:
        assert a.sources and a.items
        assert len({i.id for i in a.items}) == len(a.items)
    assert {a.id for a in areas} >= {"cl-torres-del-paine", "ar-el-chalten", "ar-el-calafate",
                                     "cl-puerto-natales", "ar-ushuaia", "ar-buenos-aires"}


def test_a_stop_finds_its_area_by_name_or_by_distance():
    assert todo.area_for("El Chalten", "AR", None, None).id == "ar-el-chalten"
    # a hotel inside the park, by its coordinates
    assert todo.area_for("Hotel Las Torres", "CL", -50.98, -72.87).id == "cl-torres-del-paine"
    assert todo.area_for("Puerto Natales", "CL", -51.73, -72.5).id == "cl-puerto-natales"
    # not across the border: a Chilean name never gets an Argentine area
    assert todo.area_for("Somewhere", "CL", -49.33, -72.89) is None


def test_other_places_get_their_most_visited_sights_without_numbers():
    t = todo.todo_for("Florence", "IT", 43.7696, 11.2558)
    # what organised trips do from Florence first (days of several sights), then other sights
    assert t.source == "trips" and len(t.items) >= 5
    assert "Florence" not in [i.name for i in t.items]
    dumped = str([i.model_dump() for i in t.items])
    assert "trips" not in dumped  # how many organised trips go there never leaves the server


# ---------------------------------------------------------------- the day plan

def test_sky_of_a_day():
    assert sky_of(day(0, "clear")) == "clear"
    assert sky_of(day(0, "cloud")) == "cloud"
    assert sky_of(day(0, "rain")) == "rain"
    assert sky_of(day(0, "wind")) == "wind"
    assert sky_of(day(0)) == "unknown"


def test_months_ahead_the_plan_follows_the_order():
    a = tdp()
    p = plan_days([day(i) for i in range(5)], a.items, a.rain, a.routes)
    first = [t.item.id for t in p.days[0].things]
    assert first == ["base-torres"]  # the one not to miss comes first
    assert not any(t.moved for d in p.days for t in d.things)
    assert any("forecast arrives" in x for x in p.advice)


def test_a_walk_that_needs_a_view_moves_to_the_clear_day():
    a = tdp()
    skies = ["rain", "cloud", "clear", "wind", "cloud"]
    p = plan_days([day(i, s) for i, s in enumerate(skies)], a.items, a.rain, a.routes)
    by_day = {d.date: [t.item.id for t in d.things] for d in p.days}
    assert "base-torres" in by_day[START + timedelta(days=2)]
    moved = [t for d in p.days for t in d.things if t.item.id == "base-torres"][0]
    assert moved.moved
    # the boat never goes on the windy or the rainy day
    for d in p.days:
        if d.sky in ("rain", "wind"):
            assert "grey-boat" not in [t.item.id for t in d.things]
    # the rainy day gets something that works in the rain
    rainy = p.days[0]
    assert rainy.things and all(t.item.need == "any" for t in rainy.things)


def test_no_clear_day_puts_the_walk_on_the_least_bad_day_marked():
    a = tdp()
    p = plan_days([day(i, "cloud") for i in range(3)], a.items, a.rain)
    bt = [t for d in p.days for t in d.things if t.item.id == "base-torres"][0]
    assert bt.note.startswith("Only if it clears")


def test_the_traveller_says_it_rains_today_and_the_plan_changes():
    a = tdp()
    w = [day(i, "clear") for i in range(3)]
    p = plan_days(w, a.items, a.rain, choices={"weather": {START.isoformat(): "rain"}})
    assert p.days[0].override and p.days[0].sky == "rain"
    assert "base-torres" not in [t.item.id for t in p.days[0].things]


def test_skip_and_pin():
    a = tdp()
    w = [day(i) for i in range(4)]
    p = plan_days(w, a.items, a.rain, choices={
        "skip": ["base-torres"], "pins": {"pumas": (START + timedelta(days=3)).isoformat()}})
    ids = [t.item.id for d in p.days for t in d.things]
    assert "base-torres" not in ids
    assert "pumas" in [t.item.id for t in p.days[3].things]
    assert [t for t in p.days[3].things if t.item.id == "pumas"][0].pinned


def test_the_w_trek_keeps_its_days_whatever_the_sky():
    a = tdp()
    skies = ["clear", "rain", "cloud", "rain", "clear"]
    p = plan_days([day(i, s) for i, s in enumerate(skies)], a.items, a.rain, a.routes,
                  choices={"mode": "w-trek"})
    assert p.mode == "w-trek"
    assert [d.kind for d in p.days] == ["route"] * 5
    assert p.days[1].note.startswith("If the towers are in cloud")  # the rain advice of day 2
    assert any("booked" in x for x in p.advice)


def test_not_in_season_is_left_out_and_said():
    a = todo.area_for("Puerto Madryn", "AR", None, None)
    w = [DayWeather(date(2027, 4, 10) + timedelta(days=i), 18, 8, 0, 20, 20, source="climate")
         for i in range(3)]
    p = plan_days(w, a.items, a.rain)
    assert "Whale watching from Puerto Pirámides" in [i.name for i in p.out_of_season]


def test_a_wet_month_with_no_spare_day_says_so():
    a = todo.area_for("El Chaltén", "AR", None, None)
    p = plan_days([day(i, prob=40) for i in range(2)], a.items, a.rain)
    assert any("one more day" in x for x in p.advice)


# ---------------------------------------------------------------- legs and flights

def test_nearest_airport_prefers_a_real_airport_in_the_same_country():
    assert travel.nearest_airport(-34.6037, -58.3816, "AR")["iata"] == "AEP"
    assert travel.nearest_airport(-50.94, -73.41, "CL")["iata"] in ("PNT", "PUQ")
    assert travel.nearest_airport(-49.3315, -72.8863, "AR")["iata"] == "FTE"


def test_flight_links_have_route_and_date_and_domestic_airlines():
    links = travel.flight_links("AEP", "FTE", date(2027, 1, 9))
    labels = [x["label"] for x in links]
    assert labels[:2] == ["Google Flights", "Skyscanner"]
    assert "Aerolíneas Argentinas" in labels
    assert "2027-01-09" in links[0]["url"] and "/aep/fte/270109/" in links[1]["url"]
    assert "Aviasales" not in labels  # only with a partner marker
    intl = [x["label"] for x in travel.flight_links("MXP", "EZE", date(2027, 1, 5))]
    assert "Aerolíneas Argentinas" not in intl


def test_leg_guess():
    ba = {"lat": -34.6, "lon": -58.38, "country": "AR"}
    cal = {"lat": -50.34, "lon": -72.26, "country": "AR"}
    cha = {"lat": -49.33, "lon": -72.89, "country": "AR"}
    assert travel.guess(ba, cal)["mode"] == "flight"
    g = travel.guess(cal, cha)
    assert g["mode"] == "road" and 2 <= g["hours"] <= 5
    assert travel.guess(None, cal)["mode"] == "flight"


def test_prices_need_a_token_and_read_travelpayouts(monkeypatch):
    assert travel.prices("AEP", "FTE", date(2027, 1, 9)) is None
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "travelpayouts_token", "t")
    monkeypatch.setattr(get_settings(), "travelpayouts_marker", "m1")
    travel._PRICE_CACHE.clear()

    def handler(req):
        assert req.url.params["origin"] == "AEP" and req.url.params["departure_at"] == "2027-01"
        return httpx.Response(200, json={"data": [
            {"departure_at": "2027-01-09T07:00:00-03:00", "price": 142, "airline": "AR", "link": "/search/x"},
            {"departure_at": "2027-01-10T07:00:00-03:00", "price": 98, "airline": "AR", "link": "/search/y"},
            {"departure_at": "2027-01-09T19:00:00-03:00", "price": 120, "airline": "AR"},
            {"departure_at": "2027-01-25T07:00:00-03:00", "price": 60, "airline": "AR"},
        ]})
    c = httpx.Client(transport=httpx.MockTransport(handler))
    p = travel.prices("AEP", "FTE", date(2027, 1, 9), client=c)
    assert [(x["date"], x["price"]) for x in p] == [("2027-01-09", 120), ("2027-01-10", 98)]
    assert p[1]["url"].endswith("marker=m1")
    travel._PRICE_CACHE.clear()


# ---------------------------------------------------------------- the API

def _stop(name, cc, lat, lon, start, days, **kw):
    end = start + timedelta(days=days - 1)
    return {"name": name, "country_code": cc, "latitude": lat, "longitude": lon,
            "start_date": start.isoformat(), "end_date": end.isoformat(), **kw}


def _trip(client):
    assert client.post("/api/auth/guest").status_code == 200
    s = date(2027, 1, 6)
    stops = [_stop("Buenos Aires", "AR", -34.6037, -58.3816, s, 3),
             _stop("El Calafate", "AR", -50.3379, -72.2648, s + timedelta(days=3), 2),
             _stop("El Chaltén", "AR", -49.3315, -72.8863, s + timedelta(days=5), 3),
             _stop("Torres del Paine", "CL", -50.94, -73.41, s + timedelta(days=8), 5)]
    r = client.post("/api/trips", json={"name": "Patagonia", "stops": stops})
    assert r.status_code == 201
    return r.json()


def test_board_shows_days_legs_and_plans(client):
    t = _trip(client)
    b = client.get(f"/api/trips/{t['id']}/board").json()
    assert b["total_days"] == 13 and len(b["stops"]) == 4
    ba, cal, cha, tp = b["stops"]
    assert ba["arrival"]["from_name"] == "Home"
    assert cal["arrival"]["mode"] == "flight"
    assert cal["arrival"]["from_airport"]["iata"] == "AEP" and cal["arrival"]["to_airport"]["iata"] == "FTE"
    assert any(x["label"] == "Google Flights" for x in cal["arrival"]["links"])
    assert cha["arrival"]["mode"] == "bus" and cha["arrival"]["hours"]
    assert tp["arrival"]["border"] is True
    assert tp["todo"]["source"] == "guide" and tp["todo"]["routes"][0]["id"] == "w-trek"
    assert len(tp["plan"]["days"]) == 5
    assert tp["plan"]["days"][0]["things"]
    assert b["return_leg"]["to_name"] == "Home" and b["return_leg"]["date"] == "2027-01-19"


def test_layout_moves_the_days_and_respects_what_is_booked(client):
    t = _trip(client)
    tid = t["id"]
    ids = [s["id"] for s in t["stops"]]
    lay = lambda days, st=None, start=None: client.put(f"/api/trips/{tid}/layout", json={  # noqa: E731
        "start_date": start, "stops": [{"id": i, "days": d, **({"status": st[k]} if st and st[k] else {})}
                                       for k, (i, d) in enumerate(zip(ids, days))]})
    r = lay([4, 2, 3, 5])  # one more day in Buenos Aires: everything after moves
    assert r.status_code == 200
    by = {s["name"]: s for s in r.json()["stops"]}
    assert by["El Calafate"]["start_date"] == "2027-01-10"
    assert by["Torres del Paine"]["end_date"] == "2027-01-19"
    # Torres del Paine booked: it may not move any more
    p = client.patch(f"/api/trips/{tid}/stops/{ids[3]}", json={"status": "fixed", "fixed_note": "refugios booked"})
    assert p.status_code == 200 and p.json()["status"] == "fixed"
    r = lay([5, 2, 3, 5])
    assert r.status_code == 409 and "Torres del Paine is fixed" in r.json()["detail"]
    # take the day from El Calafate instead: allowed, nothing booked moves
    r = lay([5, 1, 3, 5])
    assert r.status_code == 200
    # unlocking in the same change is allowed
    r = lay([5, 2, 3, 5], st=[None, None, None, "flex"])
    assert r.status_code == 200
    assert {s["name"]: s for s in r.json()["stops"]}["Torres del Paine"]["status"] == "flex"
    # a fixed stop can't be removed or have its dates edited
    client.patch(f"/api/trips/{tid}/stops/{ids[3]}", json={"status": "fixed"})
    assert client.delete(f"/api/trips/{tid}/stops/{ids[3]}").status_code == 409
    r = client.patch(f"/api/trips/{tid}/stops/{ids[3]}", json={"end_date": "2027-01-30"})
    assert r.status_code == 409


def test_a_booked_flight_locks_its_day(client):
    t = _trip(client)
    tid, ids = t["id"], [s["id"] for s in t["stops"]]
    r = client.patch(f"/api/trips/{tid}/stops/{ids[1]}", json={
        "arrival": {"mode": "flight", "booked": True, "ref": "AR 1872", "from": "aep", "to": "FTE"}})
    assert r.status_code == 200 and r.json()["arrival"]["from"] == "AEP"
    r = client.put(f"/api/trips/{tid}/layout", json={"stops": [
        {"id": ids[0], "days": 4}, {"id": ids[1], "days": 2}, {"id": ids[2], "days": 3}, {"id": ids[3], "days": 5}]})
    assert r.status_code == 409 and "booked flight to El Calafate" in r.json()["detail"]
    b = client.get(f"/api/trips/{tid}/board").json()
    assert b["stops"][1]["arrival"]["booked"] and b["stops"][1]["arrival"]["ref"] == "AR 1872"
    # bad airport code
    r = client.patch(f"/api/trips/{tid}/stops/{ids[1]}", json={"arrival": {"mode": "flight", "from": "ZZZ"}})
    assert r.status_code == 422


def test_booked_flight_home_keeps_the_end(client):
    t = _trip(client)
    tid, ids = t["id"], [s["id"] for s in t["stops"]]
    r = client.patch(f"/api/trips/{tid}", json={"home_airport": "mxp",
                                                 "return_leg": {"mode": "flight", "booked": True}})
    assert r.status_code == 200 and r.json()["home_airport"] == "MXP"
    b = client.get(f"/api/trips/{tid}/board").json()
    assert b["home_airport"]["iata"] == "MXP"
    assert b["stops"][0]["arrival"]["from_airport"]["iata"] == "MXP"
    r = client.put(f"/api/trips/{tid}/layout", json={"stops": [
        {"id": ids[0], "days": 3}, {"id": ids[1], "days": 2}, {"id": ids[2], "days": 4}, {"id": ids[3], "days": 5}]})
    assert r.status_code == 409 and "flight home" in r.json()["detail"]


def test_plan_choices_are_saved_and_used(client):
    t = _trip(client)
    tid, tp = t["id"], t["stops"][3]["id"]
    r = client.patch(f"/api/trips/{tid}/stops/{tp}", json={"plan": {
        "skip": ["pumas"], "pins": {"grey-boat": "2027-01-16"}, "weather": {"2027-01-14": "rain"},
        "mode": None}, "sleep": "Refugio Paine Grande"})
    assert r.status_code == 200 and r.json()["sleep"] == "Refugio Paine Grande"
    s = client.get(f"/api/trips/{tid}/board").json()["stops"][3]
    days = {d["date"]: d for d in s["plan"]["days"]}
    assert days["2027-01-14"]["sky"] == "rain" and days["2027-01-14"]["override"]
    assert "grey-boat" in [x["id"] for x in days["2027-01-16"]["things"]]
    assert "pumas" not in [x["id"] for d in s["plan"]["days"] for x in d["things"]]
    r = client.patch(f"/api/trips/{tid}/stops/{tp}", json={"plan": {"weather": {"2027-01-14": "snow"}}})
    assert r.status_code == 422


def test_pins_follow_the_stop_when_it_moves(client):
    t = _trip(client)
    tid, ids = t["id"], [s["id"] for s in t["stops"]]
    client.patch(f"/api/trips/{tid}/stops/{ids[3]}", json={"plan": {"pins": {"grey-boat": "2027-01-16"}}})
    r = client.put(f"/api/trips/{tid}/layout", json={"stops": [
        {"id": ids[0], "days": 4}, {"id": ids[1], "days": 2}, {"id": ids[2], "days": 3}, {"id": ids[3], "days": 5}]})
    tp = {s["name"]: s for s in r.json()["stops"]}["Torres del Paine"]
    assert tp["plan"]["pins"]["grey-boat"] == "2027-01-17"


def test_airport_search_and_prices_off(client):
    client.post("/api/auth/guest")
    r = client.get("/api/travel/airports", params={"q": "calafate"}).json()
    assert r[0]["iata"] == "FTE"
    assert client.get("/api/travel/airports", params={"q": "EZE"}).json()[0]["iata"] == "EZE"
    r = client.get("/api/travel/prices", params={"origin": "AEP", "destination": "FTE", "date": "2027-01-09"})
    assert r.status_code == 200 and r.json()["available"] is False


def test_a_sunday_market_goes_on_the_sunday():
    a = todo.area_for("Buenos Aires", "AR", None, None)
    # Wed 6 to Sun 10 January 2027
    w = [DayWeather(date(2027, 1, 6) + timedelta(days=i), 28, 20, 0, 14, 15, source="climate") for i in range(5)]
    p = plan_days(w, a.items, a.rain)
    st = [d.date for d in p.days if "san-telmo" in [t.item.id for t in d.things]]
    assert st == [date(2027, 1, 10)]
    p = plan_days(w[:3], a.items, a.rain)
    assert any("Sunday only" in x for x in p.advice)


def test_months_ahead_a_wet_place_keeps_a_spare_day():
    a = todo.area_for("El Chaltén", "AR", None, None)
    p = plan_days([day(i, prob=35) for i in range(4)], a.items, a.rain)
    assert p.days[-1].kind == "spare" and p.days[-1].title == "Spare day for the weather"
    assert [t.item.id for t in p.days[0].things] == ["laguna-de-los-tres"]
    # with a real forecast there is no guessing: no spare day held back
    p = plan_days([day(i, "clear") for i in range(4)], a.items, a.rain)
    assert p.days[-1].kind != "spare"


def test_layout_keeps_free_days(client):
    t = _trip(client)
    tid, ids = t["id"], [s["id"] for s in t["stops"]]
    r = client.put(f"/api/trips/{tid}/layout", json={"stops": [
        {"id": ids[0], "days": 3}, {"id": ids[1], "days": 2, "gap_before": 1},
        {"id": ids[2], "days": 3}, {"id": ids[3], "days": 5}]})
    assert r.status_code == 200
    by = {s["name"]: s for s in r.json()["stops"]}
    assert by["El Calafate"]["start_date"] == "2027-01-10"
    assert by["Torres del Paine"]["end_date"] == "2027-01-19"


# ---------------------------------------------------------------- flights: every leg, every flight

def _offer(i, dep, price, flight="AR 1872"):
    return {"id": f"off_{i}", "total_amount": str(price), "total_currency": "EUR",
            "owner": {"name": "Aerolíneas Argentinas"}, "passengers": [{"id": "pas_1", "type": "adult"}],
            "conditions": {"change_before_departure": {"allowed": True}, "refund_before_departure": {"allowed": False}},
            "slices": [{"origin": {"iata_code": "AEP"}, "destination": {"iata_code": "FTE"}, "duration": "PT3H15M",
                        "segments": [{"origin": {"iata_code": "AEP"}, "destination": {"iata_code": "FTE"},
                                      "departing_at": f"2027-01-09T{dep}:00", "arriving_at": "2027-01-09T12:00:00",
                                      "marketing_carrier": {"name": "Aerolíneas Argentinas", "iata_code": "AR"},
                                      "marketing_carrier_flight_number": flight.split()[1],
                                      "passengers": [{"baggages": [{"type": "checked", "quantity": 1}]}]}]}]}


def test_duffel_search_lists_every_flight_of_the_day_in_time_order():
    from app.travel import duffel

    def handler(req):
        assert req.url.path == "/air/offer_requests"
        return httpx.Response(201, json={"data": {"offers": [
            _offer(1, "13:00", 150, "AR 1880"), _offer(2, "07:00", 142), _offer(3, "07:00", 120),  # same flight, 2 fares
            _offer(4, "09:30", 98, "AR 1874")]}})
    c = httpx.Client(base_url=duffel.API, transport=httpx.MockTransport(handler))
    offers = duffel.search([{"origin": "AEP", "destination": "FTE", "date": date(2027, 1, 9)}], client=c)
    assert [o["slices"][0]["departs"][11:16] for o in offers] == ["07:00", "09:30", "13:00"]
    assert offers[0]["price"] == 120  # the cheapest fare of that flight
    assert offers[0]["slices"][0]["minutes"] == 195 and offers[0]["bags"] == 1
    assert offers[0]["slices"][0]["segments"][0]["flight"] == "AR 1872"


def test_duffel_booking_uses_the_latest_offer_and_names_every_passenger():
    from app.travel import duffel
    seen = {}

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": _offer(2, "07:00", 142)})
        import json as _j
        seen["body"] = _j.loads(req.content)["data"]
        return httpx.Response(201, json={"data": {"id": "ord_1", "booking_reference": "RZPNX8",
                                                  "total_amount": "142", "total_currency": "EUR",
                                                  "slices": _offer(2, "07:00", 142)["slices"]}})
    c = httpx.Client(base_url=duffel.API, transport=httpx.MockTransport(handler))
    pax = [{"title": "mr", "given_name": "Ada", "family_name": "Rossi", "gender": "m", "born_on": "1990-01-01",
            "email": "a@example.com", "phone_number": "+393331234567"}]
    o = duffel.book("off_2", pax, client=c)
    assert o["booking_reference"] == "RZPNX8"
    assert seen["body"]["passengers"][0]["id"] == "pas_1"
    assert seen["body"]["payments"][0] == {"type": "balance", "currency": "EUR", "amount": "142"}
    import pytest
    with pytest.raises(duffel.DuffelError):
        duffel.book("off_2", pax + pax, client=c)


def test_flights_view_lists_the_flight_legs_with_one_link_for_all(client, monkeypatch):
    t = _trip(client)
    tid = t["id"]
    client.patch(f"/api/trips/{tid}", json={"home_airport": "MXP"})
    r = client.get(f"/api/trips/{tid}/flights").json()
    pairs = [(x["from_airport"]["iata"], x["to_airport"]["iata"]) for x in r["legs"]]
    assert pairs[0] == ("MXP", "EZE") or pairs[0][0] == "MXP"
    assert ("AEP", "FTE") in pairs
    assert r["legs"][-1]["stop_id"] is None  # the flight home
    assert r["all_legs_link"].startswith("https://www.kayak.com/flights/MXP-")
    assert r["search"] is False and r["book"] is False
    # no token: search and booking say so
    q = {"origin": "AEP", "destination": "FTE", "date": (date.today() + timedelta(days=30)).isoformat()}
    assert client.post("/api/travel/flights", json=q).status_code == 503


def test_booking_a_flight_locks_the_leg(client, monkeypatch):
    from app.config import get_settings
    from app.travel import duffel
    t = _trip(client)
    tid, cal = t["id"], t["stops"][1]["id"]
    monkeypatch.setattr(get_settings(), "duffel_access_token", "duffel_test_x")
    monkeypatch.setattr(duffel, "book", lambda offer_id, pax: {
        "order_id": "ord_1", "booking_reference": "RZPNX8", "price": 142.0, "currency": "EUR", "test": True,
        "slices": [{"origin": "AEP", "destination": "FTE", "segments": [{"flight": "AR 1872"}]}]})
    pax = [{"title": "ms", "given_name": "Ada", "family_name": "Rossi", "gender": "f", "born_on": "1990-01-01",
            "email": "a@example.com", "phone_number": "+393331234567"}]
    r = client.post(f"/api/trips/{tid}/flights/book", json={"offer_id": "off_2", "stop_id": cal, "passengers": pax})
    assert r.status_code == 200
    s = client.get(f"/api/trips/{tid}").json()["stops"][1]
    assert s["arrival"]["booked"] and s["arrival"]["ref"] == "RZPNX8" and "AR 1872" in s["arrival"]["note"]
    # live token: no booking
    monkeypatch.setattr(get_settings(), "duffel_access_token", "duffel_live_x")
    r = client.post(f"/api/trips/{tid}/flights/book", json={"offer_id": "off_2", "stop_id": cal, "passengers": pax})
    assert r.status_code == 503
