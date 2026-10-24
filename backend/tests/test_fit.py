from app.engine.fit import ItemSpec, score_item
from app.engine.strategy import SlotRequirement


def shell_req():
    return SlotRequirement(slot="shell_top", code="L3", name="Shell jacket", needed=True, level="medium",
                           ref_clo=0.14, waterproof=True, waterproof_grade_mm=10000, windproof=True)


def test_waterproof_jacket_passes():
    r = score_item(shell_req(), ItemSpec("shell_top", 0.14, waterproof_mm=20000, waterproof=True, windproof=True,
                                         breathability_g=15000, weight_g=400))
    assert r.passes and r.stars >= 4


def test_water_resistant_jacket_fails_and_is_capped():
    r = score_item(shell_req(), ItemSpec("shell_top", 0.12, waterproof_mm=2000, waterproof=False, windproof=True))
    assert not r.passes and r.stars <= 2 and r.issues


def test_stars_are_in_range():
    r = score_item(shell_req(), ItemSpec("shell_top", 0.0))
    assert 1 <= r.stars <= 5
