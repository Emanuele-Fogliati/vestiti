"""Days with several places (Moray, Maras and Chinchero on one Peru day) and trips the
traveller only knows as a list of places, with no days or dates."""
import json
from datetime import date, timedelta

import pytest

from app import art
from app.llm.itinerary import parse_itinerary
from app.services.dates import lay_out, spread
from tests.test_llm import _llm, settings, transport

TODAY = date(2026, 10, 25)


def _visits(d):
    return {s.name: [(v.name, v.date and (v.date - d.stops[0].start_date).days) for v in s.visits]
            for s in d.stops}


# ---------------------------------------------------------------- several places in one day

def test_peru_days_list_every_place_they_visit():
    from tests.fixtures_peru import PERU, PERU_BAD_LLM
    for d in (parse_itinerary(PERU, today=TODAY, use_llm=False),
              parse_itinerary(PERU, today=TODAY, client=_llm(PERU_BAD_LLM))):
        v = _visits(d)  # day offsets from the first stop (Cuzco starts on program day 2)
        assert v["Aguas Calientes"] == [("Moray", 2), ("Maras", 2), ("Chinchero", 2),
                                        ("Ollantaytambo", 2), ("Machu Picchu", 3)]
        assert v["Cuzco"] == [("Lima", 0)]  # day 2: Lima city tour, then the flight to Cuzco
        assert [n for n, _ in v["Puno"]] == ["Montagne Arcobaleno", "Valle Roja"]
        assert [n for n, _ in v["Taquile"]] == ["Isole Uros"]
        assert [n for n, _ in v["Arequipa"]] == ["Valle del Colca", "Yanque", "Pinchollo", "Maca"]
        assert [n for n, _ in v["Paracas"]] == ["Oasi di Huacachina"]
        assert [n for n, _ in v["Lima"]] == ["Isole Ballestas"]
        # where you slept the night before is not a visit (Taquile on the way to Chivay), nor
        # the stop itself, nor a transfer ("partenza in bus per Paracas", "volo per Cuzco")
        assert "Taquile" not in [n for n, _ in v["Chivay"]]
        for s in d.stops:
            assert all(x.name.lower() != s.name.lower() for x in s.visits)
        assert not any("Ital" in x.name for s in d.stops for x in s.visits)


def test_peru_visits_find_their_landmark_by_name():
    from tests.fixtures_peru import PERU
    d = parse_itinerary(PERU, today=TODAY, use_llm=False)
    by = {s.name: s for s in d.stops}
    named = {v.name: art.match(v.name, None, None) for s in d.stops for v in s.visits}
    assert named["Machu Picchu"] and named["Isole Uros"] and named["Montagne Arcobaleno"]
    assert named["Isole Ballestas"] and named["Valle del Colca"] and named["Oasi di Huacachina"]
    assert named["Machu Picchu"].id == art.match("Aguas Calientes", None, None).id
    assert len(by["Aguas Calientes"].visits) == 5


def test_patagonia_days_keep_their_places_and_dates():
    from tests.fixtures_patagonia import PATAGONIA, generated
    v = _visits(parse_itinerary(PATAGONIA, today=TODAY, use_llm=False))
    assert v["El Calafate"] == [("Perito Moreno", 2)]
    assert v["El Chaltén"] == [("Laguna de los Tres", 4)]
    assert v["Torres del Paine"] == [("Mirador Base Torres", 7), ("Lago Grey", 8)]
    assert v["Ushuaia"] == [("Canale di Beagle", 10), ("Laguna Esmeralda", 11)]
    assert v["Buenos Aires"] == [] and v["Puerto Natales"] == []
    gen = parse_itinerary(generated(6), today=TODAY, use_llm=False)
    assert all(len(s.visits) <= 12 for s in gen.stops)


def test_model_visits_are_kept_only_when_the_text_names_them():
    reply = {"trip_name": "Peru", "stops": [
        {"name": "Cusco", "start_date": "2027-05-01", "end_date": "2027-05-04",
         "activities": [{"type": "city"}], "visits": ["Moray", "Pisac", "Atlantis"]}]}
    d = parse_itinerary("From 1 May 2027: 4 days in Cusco, we visit Moray and Pisac", client=_llm(reply))
    assert d.parser == "llm" and [v.name for v in d.stops[0].visits] == ["Moray", "Pisac"]


def test_prose_lists_visits_inside_a_stop():
    d = parse_itinerary("From 1 May 2027: 3 days in Cusco visiting Moray, Maras and Chinchero, "
                        "then 2 days in Puno", TODAY, use_llm=False)
    assert [s.name for s in d.stops] == ["Cusco", "Puno"]
    assert [v.name for v in d.stops[0].visits] == ["Moray", "Maras", "Chinchero"]
    assert d.estimate is None and not any(s.days_estimated for s in d.stops)


# ---------------------------------------------------------------- only a list of places

def test_spread_keeps_known_days_and_shares_the_rest():
    assert spread([None] * 4, None) == [2, 2, 2, 2]
    assert spread([None] * 4, 14) == [4, 4, 3, 3]
    assert spread([None, 4, None], 10) == [3, 4, 3]
    assert spread([None, None], 1) == [1, 1]  # every place gets at least a day
    assert spread([3, 2], None) == [3, 2]
    assert lay_out([2, 1], date(2027, 5, 1)) == [(date(2027, 5, 1), date(2027, 5, 2)),
                                                 (date(2027, 5, 3), date(2027, 5, 3))]


@pytest.mark.parametrize("text", [
    "Lima, Cusco, Machu Picchu, Titicaca",
    "Lima\nCusco\nMachu Picchu\nTiticaca",
    "- Lima\n- Cusco\n- Machu Picchu\n- Titicaca",
    "Lima -> Cusco -> Machu Picchu -> Titicaca",
    "Lima - Cusco - Machu Picchu e Titicaca",
])
def test_a_bare_list_of_places_becomes_stops_in_order(text):
    d = parse_itinerary(text, TODAY, use_llm=False)
    assert [s.name for s in d.stops] == ["Lima", "Cusco", "Machu Picchu", "Titicaca"]
    # back to back, 2 days each, from 30 days out: all marked as a guess
    assert [((s.start_date - TODAY).days, (s.end_date - TODAY).days) for s in d.stops] == [
        (30, 31), (32, 33), (34, 35), (36, 37)]
    assert all(s.days_estimated for s in d.stops)
    e = d.estimate
    assert e.start and e.days and e.total_days is None
    assert len(e.questions) == 2 and e.questions == d.questions[:2]


def test_list_with_a_header_gives_the_trip_length_and_start():
    d = parse_itinerary("Dal 5 maggio 2027, 10 giorni: Lima, Cusco 4 giorni, Puno", TODAY, use_llm=False)
    assert [(s.name, s.start_date.day, s.end_date.day, s.days_estimated) for s in d.stops] == [
        ("Lima", 5, 7, True), ("Cusco", 8, 11, False), ("Puno", 12, 14, True)]
    assert (d.estimate.start, d.estimate.days, d.estimate.total_days) == (False, True, 10)
    assert d.questions == []  # length and start are both in the text

    d = parse_itinerary("Perù, 2 settimane: Lima, Cusco (Moray, Maras e Chinchero), Machu Picchu, Titicaca",
                        TODAY, use_llm=False)
    assert [s.name for s in d.stops] == ["Lima", "Cusco", "Machu Picchu", "Titicaca"]
    assert sum((s.end_date - s.start_date).days + 1 for s in d.stops) == 14
    assert [v.name for v in d.stops[1].visits] == ["Moray", "Maras", "Chinchero"]
    assert d.estimate.start and d.estimate.total_days == 14


def test_one_place_per_line_with_its_visits():
    d = parse_itinerary("Lima\nCusco: Moray, Maras, Chinchero\nMachu Picchu\nLago Titicaca", TODAY, use_llm=False)
    assert [s.name for s in d.stops] == ["Lima", "Cusco", "Machu Picchu", "Lago Titicaca"]
    assert [v.name for v in d.stops[1].visits] == ["Moray", "Maras", "Chinchero"]


def test_a_list_does_not_go_to_the_model():
    seen = []
    from app.llm.client import LLMClient
    c = LLMClient(settings(), transport("{}", seen))
    d = parse_itinerary("Lima, Cusco, Machu Picchu, Titicaca", TODAY, client=c)
    assert seen == [] and d.parser == "rules" and len(d.stops) == 4


def test_model_guessing_days_for_bare_places_is_spread_evenly():
    reply = {"trip_name": "Italy", "stops": [
        {"name": "Rome", "start_date": "2027-05-01", "end_date": "2027-05-07"},
        {"name": "Florence", "start_date": "2027-05-08", "end_date": "2027-05-08"}]}
    d = parse_itinerary("We want to see Rome and then Florence", TODAY, client=_llm(reply))
    assert d.parser == "llm"
    assert [(s.end_date - s.start_date).days + 1 for s in d.stops] == [2, 2]
    assert d.stops[0].start_date == TODAY + timedelta(days=30)
    assert d.estimate.start and d.estimate.days


def test_programs_and_prose_with_days_are_not_estimates():
    from tests.fixtures_peru import PERU
    d = parse_itinerary("From 12 June 2027: 3 days in Reykjavik, then 2 days in Rome", TODAY, use_llm=False)
    assert d.estimate is None
    d = parse_itinerary(PERU, today=TODAY, use_llm=False)  # day by day, no start date
    assert (d.estimate.start, d.estimate.days) == (True, False)


# ---------------------------------------------------------------- API

def test_parse_endpoint_returns_visits_and_the_estimate(client):
    client.post("/api/auth/guest")
    r = client.post("/api/ai/parse-itinerary", json={"text": "Lima, Cusco (Moray, Maras), Puno"}).json()
    assert [s["name"] for s in r["stops"]] == ["Lima", "Cusco", "Puno"]
    assert [v["name"] for v in r["stops"][1]["visits"]] == ["Moray", "Maras"]
    assert all(s["days_estimated"] for s in r["stops"])
    assert r["estimate"]["start"] and r["estimate"]["days"]
    assert r["questions"] == []  # the page asks these in its own form


STOPS = [  # Lima 2 days (a guess), Cusco 3 days (chosen), Puno 2 days (a guess)
    {"name": "Lima", "latitude": -12.05, "longitude": -77.04, "start_date": "2027-05-01",
     "end_date": "2027-05-02", "days_estimated": True},
    {"name": "Cusco", "latitude": -13.53, "longitude": -71.97, "start_date": "2027-05-03",
     "end_date": "2027-05-05", "visits": [{"name": "Moray", "date": "2027-05-04"}, {"name": "Machu Picchu"}]},
    {"name": "Puno", "latitude": -15.84, "longitude": -70.02, "start_date": "2027-05-06",
     "end_date": "2027-05-07", "days_estimated": True},
]


def test_trip_keeps_visits_and_shows_it_is_an_estimate(client):
    client.post("/api/auth/guest")
    t = client.post("/api/trips", json={"name": "Peru", "stops": STOPS, "start_estimated": True}).json()
    cusco = t["stops"][1]
    assert [(v["name"], v["date"]) for v in cusco["visits"]] == [("Moray", "2027-05-04"), ("Machu Picchu", None)]
    mp = art.match("Machu Picchu", None, None)
    assert cusco["visits"][1]["art"]["id"] == mp.id
    assert cusco["visits"][0]["art"] is None or cusco["visits"][0]["art"]["id"] != mp.id
    assert t["estimate"] == {"start": True, "days": True, "total_days": 7}
    summary = next(x for x in client.get("/api/trips").json() if x["id"] == t["id"])
    assert summary["estimated"] is True
    copy = client.post(f"/api/trips/{t['id']}/duplicate").json()
    assert copy["estimate"] == t["estimate"] and copy["stops"][1]["visits"][0]["name"] == "Moray"


def test_setting_the_start_and_length_firms_up_the_dates(client):
    client.post("/api/auth/guest")
    t = client.post("/api/trips", json={"name": "Peru", "stops": STOPS, "start_estimated": True}).json()
    tid = t["id"]
    # the start date moves every stop and keeps the days
    r = client.post(f"/api/trips/{tid}/dates", json={"start_date": "2027-06-10"}).json()
    assert [(s["start_date"], s["end_date"]) for s in r["stops"]] == [
        ("2027-06-10", "2027-06-11"), ("2027-06-12", "2027-06-14"), ("2027-06-15", "2027-06-16")]
    assert r["estimate"] == {"start": False, "days": True, "total_days": 7}
    assert r["stops"][1]["visits"][0]["date"] == "2027-06-13"  # still Cusco's second day
    # 11 days: Cusco keeps its 3, Lima and Puno share the other 8
    r = client.post(f"/api/trips/{tid}/dates", json={"total_days": 11}).json()
    days = [(date.fromisoformat(s["end_date"]) - date.fromisoformat(s["start_date"])).days + 1 for s in r["stops"]]
    assert days == [4, 3, 4] and r["stops"][0]["start_date"] == "2027-06-10"
    assert r["estimate"] is None
    # nothing left to guess: a length would overwrite the traveller's own days
    assert client.post(f"/api/trips/{tid}/dates", json={"total_days": 5}).status_code == 422


def test_keeping_the_guess_or_editing_a_stop_clears_the_estimate(client):
    client.post("/api/auth/guest")
    t = client.post("/api/trips", json={"name": "Peru", "stops": STOPS, "start_estimated": True}).json()
    lima = t["stops"][0]
    r = client.patch(f"/api/trips/{t['id']}/stops/{lima['id']}", json={"end_date": "2027-05-03"}).json()
    assert r["days_estimated"] is False
    r = client.patch(f"/api/trips/{t['id']}/stops/{lima['id']}", json={"visits": [{"name": "Miraflores"}]}).json()
    assert [v["name"] for v in r["visits"]] == ["Miraflores"]
    r = client.post(f"/api/trips/{t['id']}/dates", json={"confirm": True}).json()
    assert r["estimate"] is None


def test_a_stop_with_no_landmark_shows_its_first_visit(client):
    client.post("/api/auth/guest")
    t = client.post("/api/trips", json={"name": "Valle", "stops": [
        {"name": "Somewhere", "latitude": 0.0, "longitude": 0.0, "start_date": "2027-05-01",
         "end_date": "2027-05-02", "visits": [{"name": "Nowhere"}, {"name": "Machu Picchu"}]}]}).json()
    assert t["stops"][0]["art"]["id"] == art.match("Machu Picchu", None, None).id


def test_migration_adds_the_new_columns(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy import create_engine, inspect
    url = f"sqlite:///{tmp_path / 'm.db'}"
    env = {**os.environ, "DATABASE_URL": url}
    here = Path(__file__).resolve().parents[1]
    for step in (["upgrade", "head"], ["downgrade", "0002"], ["upgrade", "head"]):
        subprocess.run([sys.executable, "-m", "alembic", *step], cwd=here, env=env, check=True,
                       capture_output=True)
    insp = inspect(create_engine(url))
    assert {"visits", "days_estimated"} <= {c["name"] for c in insp.get_columns("stops")}
    assert "start_estimated" in {c["name"] for c in insp.get_columns("trips")}
