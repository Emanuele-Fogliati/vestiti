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
        "pe-cusco-cathedral", "pe-machu-picchu", "pe-rainbow-mountain", "pe-uros-titicaca", "pe-taquile",
        "pe-colca-canyon", "pe-arequipa", "pe-paracas-ballestas", "pe-lima-costa-verde"]


def test_name_beats_distance_and_far_places_get_nothing():
    # "Huacachina" is 5 km from Ica: the name wins even with rough coordinates
    assert art.match("Huacachina", -14.06, -75.73).id == "pe-huacachina"
    assert art.match("Reykjavik", 64.14, -21.94) is None
    assert art.match("Machu Picchu Pueblo", None, None).id == "pe-machu-picchu"


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
    assert {x["id"] for x in client.get("/api/art/landmarks").json()} >= {"pe-machu-picchu", "pe-uros-titicaca"}
    r = client.get("/api/art/landmarks/pe-machu-picchu.svg")
    assert r.status_code == 200 and "var(--il-sky)" in r.text and "--il-mid:#" in r.text  # official look
    flat = client.get("/api/art/landmarks/pe-machu-picchu.svg?flat=1").text
    assert flat == art.svg("pe-machu-picchu") and "filter" not in flat
    assert client.get("/api/art/landmarks/nope.svg").status_code == 404
    trip = client.post("/api/trips", json={"name": "Peru", "stops": [
        {"name": n, "latitude": la, "longitude": lo, "notes": no, "start_date": "2027-05-01",
         "end_date": "2027-05-02"} for n, la, lo, no in PERU[:3]] + [
        {"name": "Reykjavik", "latitude": 64.14, "longitude": -21.94, "start_date": "2027-05-03",
         "end_date": "2027-05-04"}]}).json()
    assert [s["art"] and s["art"]["id"] for s in trip["stops"]] == [
        "pe-cusco-cathedral", "pe-machu-picchu", "pe-rainbow-mountain", None]
    summary = next(t for t in client.get("/api/trips").json() if t["id"] == trip["id"])
    assert summary["art"]["id"] == "pe-cusco-cathedral"


def test_library_follows_the_style_guide():
    from app.art.lint import lint_catalog, lint_svg
    assert lint_catalog() == []
    for lm in art.landmarks():
        assert lint_svg(lm.id, art.svg(lm.id)) == [], lm.id


def test_linter_catches_off_style_scenes():
    from app.art.lint import lint_svg
    good = art.svg("pe-machu-picchu")
    assert lint_svg("pe-machu-picchu", good) == []
    assert any("tokens" in p for p in lint_svg("pe-x", good.replace("var(--il-mid)", "#ff0000", 1)))
    assert any("sky" in p for p in lint_svg("pe-x", good.split("\n", 1)[1]))
    assert any("<text>" in p for p in lint_svg("pe-x", good + '<text x="1" y="1">Hi</text>'))
    assert any("bad id" in p or "must be" in p for p in lint_svg("Peru Machu", good))


def test_render_gives_the_official_look():
    """Palette of the place, 1 px --il-near outline and a paper shadow on every filled shape but the sky."""
    out = art.rendered("pe-huacachina")
    assert out.startswith('<defs><filter id="il-pe-huacachina-shadow"')
    assert '<g style="--il-sky:#DDEEF6;' in out and "--il-obj:#2F7FB5" in out
    sky = re.search(r"<rect [^>]*fill=\"var\(--il-sky\)\"[^>]*>", out)[0]
    assert "stroke" not in sky and "filter" not in sky
    sun = re.search(r"<circle [^>]*fill=\"var\(--il-sun\)\"[^>]*>", out)[0]
    assert 'stroke="var(--il-near)"' in sun and "url(#il-pe-huacachina-shadow)" in sun
    # clipped stripes of the Rainbow Mountain get the outline of their clip shape
    rb = art.rendered("pe-rainbow-mountain")
    clip_d = re.search(r'<clipPath id="il-pe-rainbow-mountain-clip"><path d="([^"]+)"', rb)[1]
    assert f'<path d="{clip_d}" fill="none" stroke="var(--il-near)"' in rb
    assert art.rendered("pe-nope") is None


def test_every_place_has_a_full_palette():
    from app.art.lint import TOKENS, palette_problems
    for lm in art.landmarks():
        assert palette_problems(dict(lm.palette)) == [], lm.id
    assert palette_problems({"sky": "#FFFFFF"})
    assert palette_problems({t: "red" for t in TOKENS})
