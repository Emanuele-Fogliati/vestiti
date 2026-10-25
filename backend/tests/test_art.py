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


# ---------------------------------------------------------------- image model (ComfyUI)

import io  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.art import generate  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import PlaceArt  # noqa: E402


def _png(colour=(120, 140, 110)) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (768, 512), (235, 235, 230))
    d = ImageDraw.Draw(im)
    d.polygon([(0, 512), (300, 150), (600, 512)], fill=colour)
    d.ellipse((600, 40, 680, 120), fill=(255, 210, 20))  # a yellow sun
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def fake_comfy(calls: list):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path == "/prompt":
            wf = __import__("json").loads(req.content)["prompt"]
            assert wf["1"]["inputs"]["ckpt_name"] == "flux1-schnell-fp8.safetensors"
            assert "flat vector illustration" in wf["2"]["inputs"]["text"]
            return httpx.Response(200, json={"prompt_id": "p1"})
        if req.url.path == "/history/p1":
            if calls.count("/history/p1") < 2:
                return httpx.Response(200, json={})  # still running
            return httpx.Response(200, json={"p1": {"status": {"status_str": "success"}, "outputs": {
                "7": {"images": [{"filename": "vestiti_00001_.png", "subfolder": "", "type": "output"}]}}}})
        if req.url.path == "/view":
            return httpx.Response(200, content=_png())
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture()
def art_on(monkeypatch):
    monkeypatch.setenv("ART_IMAGE_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_comfy_round_trip_and_palette():
    calls = []
    png = generate.comfy_generate("Hallgrimskirkja church. " + generate.STYLE, 7,
                                  transport=fake_comfy(calls), poll_s=0)
    assert calls[0] == "/prompt" and calls[-1] == "/view"
    from PIL import Image
    toned = Image.open(io.BytesIO(generate.tone(png, "yellow-black"))).convert("RGB")
    colours = {toned.getpixel(p) for p in [(20, 20), (300, 450), (640, 80)]}
    sky, near_ish, sun = (toned.getpixel((20, 20)), toned.getpixel((300, 450)), toned.getpixel((640, 80)))
    assert len(colours) == 3
    assert abs(sun[0] - 0xFF) < 12 and abs(sun[2] - 0x0A) < 30  # the sun takes --il-sun
    assert sum(near_ish) < sum(sky)  # mountain darker than sky, both from the grey ramp
    assert abs(near_ish[0] - near_ish[2]) < 20  # no green left


def test_unreachable_comfy_is_a_clean_failure(art_on, db, monkeypatch):
    monkeypatch.setenv("ART_IMAGE_URL", "http://127.0.0.1:9")  # nothing listens
    monkeypatch.setenv("ART_IMAGE_TIMEOUT_S", "2")
    get_settings.cache_clear()
    row = generate.request(db, "Nowhere Town", "IS", 64.0, -20.0, enqueue=False)
    assert row.status == "pending"
    row = generate.generate(db, row.key)
    assert row.status == "failed" and row.error and row.image is None
    # a failed place is not retried on every page view
    assert generate.request(db, "Nowhere Town", "IS", 64.0, -20.0, enqueue=False).status == "failed"


def test_generation_off_never_queues(db):
    assert generate.request(db, "Vik", "IS", 63.42, -19.0) is None
    assert db.get(PlaceArt, generate.place_key("Vik", "IS", 63.42, -19.0)) is None


def test_place_api_queues_draws_and_serves(art_on, client, db, monkeypatch):
    monkeypatch.setattr(generate, "pick_subject", lambda n, cc: ("Hallgrimskirkja", "a tall concrete church"))
    queued = []
    monkeypatch.setattr(generate._jobs, "put", queued.append)
    monkeypatch.setattr(generate, "_ensure_worker", lambda: None)
    assert client.post("/api/auth/guest").status_code == 200
    body = {"name": "Reykjavik", "country_code": "IS", "latitude": 64.1466, "longitude": -21.9426}
    r = client.post("/api/art/places", json=body).json()
    assert r["status"] == "pending" and queued == [r["key"]]
    # asking again while it is being drawn does not queue it twice
    assert client.post("/api/art/places", json={**body, "latitude": 64.12}).json()["status"] == "pending"
    assert len(queued) == 1
    # the worker draws it (here with the fake ComfyUI)
    db.expire_all()
    row = generate.generate(db, r["key"], transport=fake_comfy([]))
    assert row.status == "ready" and row.subject == "Hallgrimskirkja"
    r = client.post("/api/art/places", json=body).json()
    assert r["status"] == "ready" and r["label"] == "Hallgrimskirkja"
    img = client.get(r["url"] + "&theme=cobalt")
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp"
    assert client.get("/api/art/places/nope.webp").status_code == 404
