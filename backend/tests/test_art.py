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
    assert art.match("Somewhere at sea", 0.0, -30.0) is None
    assert art.match("Machu Picchu Pueblo", None, None).id == "pe-machu-picchu"


def test_approved_places_match_their_stops_and_not_namesakes():
    m = lambda n, la=None, lo=None: (art.match(n, la, lo) or S(id=None)).id
    assert m("Reykjavik", 64.14, -21.94) == "is-reykjavik"
    assert m("El Chaltén", -49.33, -72.89) == "ar-fitz-roy"
    assert m("Caminito, La Boca, Buenos Aires") == "ar-la-boca"
    assert m("Buenos Aires", -34.60, -58.38) == "ar-buenos-aires"
    assert m("Iguaçu") == "ar-iguazu-falls"
    assert m("San Pedro de Atacama", -22.91, -68.20) == "cl-san-pedro-de-atacama"
    assert m("Valle de la Luna", -22.93, -68.26) == "cl-valle-de-la-luna"
    assert m("Hội An") == "vn-hoi-an" and m("Saigon") == "vn-ho-chi-minh-city"
    # namesakes far from the drawn place never get its scene (they may get their own one day)
    assert m("Santiago de Compostela", 42.88, -8.54) != "cl-santiago"
    assert m("Osorno", -40.57, -73.13) != "cl-osorno-volcano"  # the city, 60 km from the volcano
    assert m("Valle de la Luna", -16.57, -68.09) != "cl-valle-de-la-luna"  # La Paz, Bolivia
    assert m("Ho Chi Minh Mausoleum") != "vn-ho-chi-minh-city"  # in Hanoi, not Ho Chi Minh City
    assert m("Agra Fort") != "in-taj-mahal" and m("Catacombs of Rome") != "it-colosseum"
    # cities whose symbol is a monument get it from their coordinates
    assert m("Agra", 27.18, 78.01) == "in-taj-mahal" and m("Rome", 41.90, 12.50) == "it-colosseum"
    assert m("Rio de Janeiro", -22.91, -43.17) == "br-christ-the-redeemer"


def test_city_names_match_only_as_the_whole_name_and_far_namesakes_are_ignored():
    m = lambda n, la=None, lo=None: (art.match(n, la, lo) or S(id=None)).id
    assert m("Lima") == "pe-lima-costa-verde" and m("Lima Cathedral") != "pe-lima-costa-verde"
    assert m("Paris") == "fr-paris" and m("Eiffel Tower") == "fr-paris" and m("Notre-Dame de Paris") != "fr-paris"
    assert m("Chiang Mai") == "th-doi-suthep" and m("Rome") == "it-colosseum"
    # a stop named after a landmark but far from it is another place
    assert m("Venice Beach", 33.985, -118.47) != "it-venice" and m("Venice", 45.44, 12.33) == "it-venice"
    assert m("Grand Canyon of the Yellowstone", 44.72, -110.48) != "us-grand-canyon"


def test_globe_places_get_their_own_scene_only():
    from app import globe
    got = {(p[1], p[2]): p[7] for p in globe.payload()["places"]}
    wrong = {"Acropolis of Lindos": "gr-acropolis-of-athens", "Palazzo Venezia": "it-venice",
             "Hagia Sophia of Trabzon": "tr-istanbul", "Agra Fort": "in-taj-mahal", "Lima Cathedral": "pe-lima-costa-verde"}
    for (name, cc), want in got.items():
        if name in wrong:
            assert want is None or want != wrong[name], name
    assert got.get(("Eiffel Tower", "FR")) == "fr-paris" and got.get(("Paris", "FR")) == "fr-paris"


def test_library_has_the_approved_calibration_set():
    ids = {lm.id for lm in art.landmarks()}
    assert len(ids) >= 45 and {"is-gullfoss", "vn-cu-chi-tunnels", "jo-petra", "cl-osorno-volcano"} <= ids
    for lm in art.landmarks():
        assert lm.id.startswith(lm.country.lower() + "-")


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
    # a redrawn scene must show at once: no long browser cache, a cheap 304 when unchanged
    assert r.headers["cache-control"] == "no-cache"
    assert client.get("/api/art/landmarks/pe-machu-picchu.svg",
                      headers={"If-None-Match": r.headers["etag"]}).status_code == 304
    trip = client.post("/api/trips", json={"name": "Peru", "stops": [
        {"name": n, "latitude": la, "longitude": lo, "notes": no, "start_date": "2027-05-01",
         "end_date": "2027-05-02"} for n, la, lo, no in PERU[:3]] + [
        {"name": "Somewhere at sea", "latitude": 0.0, "longitude": -30.0, "start_date": "2027-05-03",
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
    assert '<g style="--il-sky:#AFCFF0;' in out and "--il-obj:#D9C092" in out
    sky = re.search(r"<rect [^>]*fill=\"var\(--il-sky\)\"[^>]*>", out)[0]
    assert "stroke" not in sky and "filter" not in sky
    sun = re.search(r"<circle [^>]*fill=\"var\(--il-sun\)\"[^>]*>", out)[0]
    assert 'stroke="var(--il-near)"' in sun and "url(#il-pe-huacachina-shadow)" in sun
    # clipped stripes get the outline of their clip shape
    from app.art.render import render
    body = ('<rect width="320" height="180" fill="var(--il-sky)"/>'
            '<clipPath id="il-pe-x-clip"><path d="M0 180 L160 40 L320 180 Z"/></clipPath>'
            '<g clip-path="url(#il-pe-x-clip)"><rect y="100" width="320" height="20" fill="var(--il-acc)"/></g>')
    rb = render("pe-x", body, None)
    assert '<path d="M0 180 L160 40 L320 180 Z" fill="none" stroke="var(--il-near)"' in rb
    assert art.rendered("pe-nope") is None


def test_every_place_has_a_full_palette():
    from app.art.lint import TOKENS, palette_problems
    for lm in art.landmarks():
        assert palette_problems(dict(lm.palette)) == [], lm.id
    assert palette_problems({"sky": "#FFFFFF"})
    assert palette_problems({t: "red" for t in TOKENS})


def test_same_position_names_go_to_the_nearest(monkeypatch):
    far = art.Landmark("in-agra-fort", "Agra Fort", "IN", 27.18, 78.02, 3, ("red fort of agra",))
    near = art.Landmark("in-red-fort", "Red Fort", "IN", 28.656, 77.241, 3, ("red fort",))
    monkeypatch.setattr(art, "landmarks", lambda: (far, near))
    assert art.match("Red Fort", 28.65, 77.24).id == "in-red-fort"
    assert art.match("Red Fort of Agra", 27.18, 78.02).id == "in-agra-fort"


def test_names_with_unsplittable_letters_fold_to_ascii():
    assert art._norm("Tromsø") == "tromso"
    assert art._norm("Svolvær") == "svolvaer"
    assert art._norm("Ærø") == "aero"
    assert art._norm("Łódź") == "lodz"
    assert art._norm("Þingvellir") == "thingvellir"
    assert art._norm("Straße") == "strasse"
