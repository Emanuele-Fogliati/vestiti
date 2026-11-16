"""Every place's own text (app.guide/places.json): the card a place or its drawing opens."""
import json
from pathlib import Path

from app import guide

GUIDE = Path(guide.__file__).with_name("places.json")


def test_guide_endpoint_by_name_and_country(client):
    r = client.get("/api/globe/guide", params={"name": "Huacachina", "country": "PE"})
    assert r.status_code == 200 and r.json()["fun_fact"] and r.json()["source"].startswith("https://")
    # the same name in another country is not this place
    assert client.get("/api/globe/guide", params={"name": "Huacachina", "country": "CL"}).status_code == 404
    assert client.get("/api/globe/guide", params={"name": "Huacachina"}).status_code == 422


def test_guides_are_valid_and_unambiguous():
    gs = guide.guides()
    seen: dict[tuple[str, str], int] = {}
    for i, g in enumerate(gs):
        for n in {guide._norm(n) for n in g.names}:
            k = (n, g.country)
            assert k not in seen, f"{n} ({g.country}) has two texts"
            seen[k] = i
    # never the number of organised trips (Manu, 2026-10-26)
    raw = GUIDE.read_text(encoding="utf-8").lower()
    assert "organised trips" not in raw and "tour operators include" not in raw
    assert json.loads(GUIDE.read_text(encoding="utf-8"))
