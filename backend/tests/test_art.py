"""Landmark illustrations: every stop of the Peru trip gets its own place, others fall back."""
import re
from types import SimpleNamespace as S

from app import art

PERU = [  # the stops the agency program becomes (see test_llm), with real coordinates
    ("Cuzco", -13.5319, -71.9675, None),
    ("Aguas Calientes", -13.1547, -72.5254, None),
    ("Cusco", -13.5319, -71.9675, "Escursione alla Montagna Arcobaleno (Vinicunca), 5200 m"),
    ("Puno", -15.8402, -70.0219, None),
    ("Taquile", -15.7700, -69.6800, None),
    ("Chivay", -15.6383, -71.6011, None),
    ("Arequipa", -16.4090, -71.5375, None),
    ("Paracas", -13.8340, -76.2500, None),
    ("Lima", -12.0464, -77.0428, "Isole Ballestas in barca"),
]


def test_peru_trip_gets_one_landmark_per_stop():
    stops = [S(name=n, latitude=la, longitude=lo, notes=no) for n, la, lo, no in PERU]
    assert [lm.id if lm else None for lm in art.assign(stops)] == [
        "cusco-cathedral", "machu-picchu", "rainbow-mountain", "uros-titicaca", "taquile",
        "colca-canyon", "arequipa", "paracas-ballestas", "lima-costa-verde"]


def test_name_beats_distance_and_far_places_get_nothing():
    # "Huacachina" is 5 km from Ica: the name wins even with rough coordinates
    assert art.match("Huacachina", -14.06, -75.73).id == "huacachina"
    assert art.match("Reykjavik", 64.14, -21.94) is None
    assert art.match("Machu Picchu Pueblo", None, None).id == "machu-picchu"


def test_every_landmark_has_a_token_only_svg():
    for lm in art.landmarks():
        body = art.svg(lm.id)
        assert body, lm.id
        assert "<script" not in body and "href" not in body.replace('url(#', '')
        colours = set(re.findall(r'(?:fill|stroke)="([^"]+)"', body)) - {"none"}
        assert all(c.startswith("var(--il-") for c in colours), (lm.id, colours)
    assert art.svg("../config") is None


def test_api_serves_landmarks_and_trips_carry_them(client):
    assert client.post("/api/auth/guest").status_code == 200
    assert {x["id"] for x in client.get("/api/art/landmarks").json()} >= {"machu-picchu", "uros-titicaca"}
    r = client.get("/api/art/landmarks/machu-picchu.svg")
    assert r.status_code == 200 and "var(--il-sky)" in r.text
    assert client.get("/api/art/landmarks/nope.svg").status_code == 404
    trip = client.post("/api/trips", json={"name": "Peru", "stops": [
        {"name": n, "latitude": la, "longitude": lo, "notes": no, "start_date": "2027-05-01",
         "end_date": "2027-05-02"} for n, la, lo, no in PERU[:3]] + [
        {"name": "Reykjavik", "latitude": 64.14, "longitude": -21.94, "start_date": "2027-05-03",
         "end_date": "2027-05-04"}]}).json()
    assert [s["art"] and s["art"]["id"] for s in trip["stops"]] == [
        "cusco-cathedral", "machu-picchu", "rainbow-mountain", None]
    summary = next(t for t in client.get("/api/trips").json() if t["id"] == trip["id"])
    assert summary["art"]["id"] == "cusco-cathedral"
