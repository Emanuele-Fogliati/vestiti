from app.engine.strategy import conditions_for_stage, evaluate, reference_kit, requirements, clarifying_questions
from tests.helpers import stage


def plan(*stages):
    conds = [c for s in stages for c in conditions_for_stage(s)]
    reqs = requirements(list(stages), conds)
    kit = reference_kit(reqs)
    return conds, reqs, kit, evaluate(list(stages), conds, kit)


def needed(reqs):
    return {k for k, r in reqs.items() if r.needed}


def test_beach_heat_needs_no_warm_layers():
    s = stage(activities=[{"type": "beach"}], tmax=33, tmin=24)
    _, reqs, _, _ = plan(s)
    n = needed(reqs)
    assert {"base_top", "trousers", "footwear"} <= n
    assert not n & {"insulation_top", "headwear", "gloves", "shell_bottom", "base_bottom"}
    assert "sun_hat" in n


def test_cold_alpine_hike_needs_full_system():
    s = stage(elev=1500, activities=[{"type": "hiking", "difficulty": "hard", "max_altitude_m": 3000}],
              tmax=8, tmin=-2, rain=6, prob=70, wind=35)
    _, reqs, _, ev = plan(s)
    n = needed(reqs)
    assert {"shell_top", "insulation_top", "headwear", "gloves", "base_top"} <= n
    assert reqs["shell_top"].waterproof
    assert reqs["footwear"].ankle_support
    st = ev["stages"][0]
    assert st["slots"]["shell_top"]["status"] in ("worn", "stops", "pack")


def test_city_rain_does_not_force_shell_pants():
    s = stage(tmax=17, tmin=11, rain=4, prob=80, wind=15)
    _, reqs, _, _ = plan(s)
    assert reqs["shell_top"].needed and reqs["shell_top"].waterproof
    assert not reqs["shell_bottom"].needed


def test_unknown_difficulty_covers_hard_version():
    known_easy = stage(activities=[{"type": "hiking", "difficulty": "easy", "max_altitude_m": 2500}], tmax=10, tmin=2)
    unknown = stage(activities=[{"type": "hiking", "difficulty": "unknown", "max_altitude_m": 2500}], tmax=10, tmin=2)
    _, r_easy, _, _ = plan(known_easy)
    _, r_unknown, _, _ = plan(unknown)
    assert len(needed(r_unknown)) >= len(needed(r_easy))
    assert r_unknown["footwear"].ankle_support or not r_easy["footwear"].ankle_support


def test_reference_kit_covers_every_stage():
    a = stage(0, "Chamonix", elev=1035, activities=[{"type": "hiking", "difficulty": "hard", "max_altitude_m": 2600}],
              tmax=18, tmin=7, rain=3, prob=40, wind=15)
    b = stage(1, "Rome", tmax=33, tmin=21)
    _, _, _, ev = plan(a, b)
    assert len(ev["stages"]) == 2
    for st in ev["stages"]:
        for mode in ("moving", "rest"):
            assert st["modes"][mode]["status"] in ("covered", "marginal")


def test_clarifying_questions_for_unknown_altitude():
    s = stage(activities=[{"type": "hiking", "difficulty": "unknown"}])
    qs = clarifying_questions([s])
    assert qs and all("question" in q or "text" in q or isinstance(q, dict) for q in qs)


def test_cold_boat_trip_needs_wind_and_waterproof_shell():
    s = stage(name="Ushuaia", activities=[{"type": "boat"}], tmax=6, tmin=0, prob=20, wind=30)
    _, reqs, _, _ = plan(s)
    assert reqs["shell_top"].needed and reqs["shell_top"].waterproof
    assert "insulation_top" in needed(reqs)


def test_glacier_walk_needs_boots_and_gloves_even_when_mild():
    s = stage(name="El Calafate", activities=[{"type": "hiking", "difficulty": "easy", "glacier": True}],
              tmax=14, tmin=6, prob=10, wind=10)
    _, reqs, _, _ = plan(s)
    fw = reqs["footwear"]
    assert fw.footwear_type == "hiking_boot" and fw.ankle_support and fw.waterproof
    assert reqs["gloves"].needed
