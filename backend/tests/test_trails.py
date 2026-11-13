"""Trekking trails (app.trails): the hand-written data, the computed geometry and the plan agree."""
import json

import pytest

from app import art, trails
from app.trails import DATA, GEO, km

SLOTS = {f"{c}-{s}" for c in ("IT", "AR", "CL", "PE", "IS") for s in ("A", "B")}


def test_every_trail_file_is_valid_and_planned():
    planned = {p["id"]: p for p in trails.plan()}
    assert len(planned) == len(trails.plan()), "a trail is planned twice"
    for t in trails.trails():
        assert t.id in planned, f"{t.id} is not in list.json"
        assert planned[t.id]["country"] == t.country
        assert (DATA / t.country.lower() / f"{t.id}.json").exists(), f"{t.id}: file in the wrong folder"


def test_plan_slots_and_status():
    for p in trails.plan():
        assert p["slot"] in SLOTS, p["id"]
        assert p["slot"].startswith(p["country"]), p["id"]
        assert p["status"] in ("todo", "draft", "checked", "drawn"), p["id"]
        assert 2 <= len(p["scenes"]) <= 6, p["id"]
        if p["status"] != "todo":
            assert p["id"] in trails.by_id(), f"{p['id']} is {p['status']} but has no data file"


@pytest.mark.parametrize("t", trails.trails(), ids=lambda t: t.id)
def test_scenes_exist_and_differ(t):
    scenes = [p.scene for p in t.points if p.scene]
    assert len(scenes) == len(set(scenes)), f"{t.id}: two points share a drawing"
    for s in scenes:
        assert s in art.by_id(), f"{t.id}: scene {s} is not in the art catalog"


@pytest.mark.parametrize("t", trails.trails(), ids=lambda t: t.id)
def test_geo_matches_the_trail(t):
    """Once built, the computed trail must agree with the points and the published numbers."""
    status = {p["id"]: p["status"] for p in trails.plan()}[t.id]
    g = trails.geo(t.id)
    if status in ("checked", "drawn"):
        assert g, f"{t.id} is {status}: build its geo (tools/trails/build_trails.py)"
    if not g:
        return
    assert [p["id"] for p in g["points"]] == [p.id for p in t.points], f"{t.id}: rebuild its geo"
    for p, gp in zip(t.points, g["points"]):
        assert km(p.lat, p.lon, gp["lat"], gp["lon"]) <= 0.8, f"{t.id}: {p.id} is off the path"
    if t.published:
        assert abs(g["km"] - t.published.km) / t.published.km <= 0.3, \
            f"{t.id}: {g['km']} km computed vs {t.published.km} published"
        if t.published.gain_m >= 200:
            assert abs(g["gain_m"] - t.published.gain_m) / t.published.gain_m <= 0.3, \
                f"{t.id}: +{g['gain_m']} m computed vs +{t.published.gain_m} published"


def test_geo_files_belong_to_trails():
    for f in GEO.glob("*.json") if GEO.exists() else []:
        assert f.stem in trails.by_id(), f"{f.name} has no trail"
        json.loads(f.read_text(encoding="utf-8"))


def test_activity_for_the_clothes():
    from app.schemas import ActivityIn
    for t in trails.trails():
        a = trails.activity(t)
        ActivityIn.model_validate(a)
        assert a["type"] == ("trek_multiday" if t.kind == "multiday" else "hiking")


def test_trails_near_a_stop():
    names = [t.id for t in trails.near(-49.331, -72.886, "AR", "El Chaltén")]
    assert "ar-laguna-de-los-tres" in names and "ar-laguna-torre" in names
    assert not any(n.startswith("cl-") for n in names)
