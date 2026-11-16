"""What to wear on a walk (Manu, 2026-11-16): "a walk in Rome in August and you give me mid
socks, sneakers AND hiking shoes and a rain jacket?". A city walk is not a hike, the month's
real climate decides the rain jacket, and the three prices of a piece are one kind of thing."""
from datetime import timedelta

import pytest

from app.engine.fit import ItemSpec, score_item
from app.engine.strategy import DayWeather, SlotRequirement
from app.weather.service import WeatherService, estimate_day

# normal weather of the month (Open-Meteo archive, 2026-11-16): tmin, tmax, mm, rain %, wind
ROME_AUG = (21, 33, 0.8, 19, 16)
LONDON_NOV = (6, 12, 2.0, 40, 18)
CHALTEN_JAN = (6, 15, 2.5, 48, 17)
LUXOR_JUL = (26, 40, 0.0, 0, 15)


@pytest.fixture()
def weather(monkeypatch):
    def use(w):
        def days_for(self, lat, lon, elev, start, end):
            tmin, tmax, mm, prob, wind = w
            out, d = [], start
            while d <= end:
                out.append(DayWeather(date=d, tmax=tmax, tmin=tmin, precip_mm=mm,
                                      precip_prob=prob, wind_kmh=wind, source="climate"))
                d += timedelta(days=1)
            return out
        monkeypatch.setattr(WeatherService, "days_for", days_for)
    return use


def _wear(client, trail_id, month):
    r = client.get(f"/api/trails/{trail_id}/wear", params={"month": month})
    assert r.status_code == 200, r.text
    return {p["slot"]: p for p in r.json()["pieces"]}


def _types(piece):
    return {v["specs"].get("footwear_type") for v in piece["products"].values() if v}


def test_rome_in_august_city_walk(client, weather):
    weather(ROME_AUG)
    w = _wear(client, "it-city-rome-7", 8)
    assert "shell_top" not in w  # 19% rain, flat town: no rain jacket
    assert {"mid_top", "insulation_top", "shell_bottom", "base_bottom"}.isdisjoint(w)
    assert w["footwear"]["footwear_type"] == "sneaker"
    assert _types(w["footwear"]) == {"sneaker"}  # one kind of shoe at all three prices
    assert w["trousers"]["level"] == "light" and w["base_top"]["level"] == "light"
    for v in w["base_top"]["products"].values():
        assert v["specs"]["clo"] < 0.135  # no long sleeves or HEATTECH at 33 °C
    for v in w["socks"]["products"].values():
        assert v["specs"]["clo"] <= 0.03  # no winter or crew hiking socks


def test_london_in_november_city_walk(client, weather):
    weather(LONDON_NOV)
    w = _wear(client, "gb-city-london-1", 11)
    assert w["shell_top"]["waterproof"]  # 40% rain: a rain jacket, rightly
    assert w["footwear"]["footwear_type"] == "sneaker"
    assert _types(w["footwear"]) == {"sneaker"}
    assert "shell_bottom" not in w and "base_bottom" not in w  # no long johns in town at 6 °C


def test_patagonia_in_january_hard_hike(client, weather):
    weather(CHALTEN_JAN)
    w = _wear(client, "ar-laguna-de-los-tres", 1)
    assert w["shell_top"]["waterproof"]
    assert w["footwear"]["footwear_type"] == "hiking_boot" and w["footwear"]["ankle_support"]
    assert _types(w["footwear"]) == {"hiking_boot"}
    for v in w["footwear"]["products"].values():
        assert not v["specs"].get("insulated")  # no snow boots at 6-15 °C
    for v in w["socks"]["products"].values():
        assert v["specs"].get("cut") != "low"  # crew socks in boots


def test_easy_walk_in_the_heat_has_no_mountain_shell(client, weather):
    weather(LUXOR_JUL)
    w = _wear(client, "eg-sight-karnak", 7)
    assert "shell_top" not in w  # 80 m, dry: not "mountain weather turns fast"


def _req(slot, level="light", **kw):
    from app.engine.garments import REF_CLO
    return SlotRequirement(slot, "", slot, needed=True, level=level,
                           ref_clo=REF_CLO[slot][level], **kw)


def test_shoes_far_heavier_than_needed_fail():
    req = _req("footwear", "medium", footwear_type="sneaker")
    boot = score_item(req, ItemSpec("footwear", 0.05, footwear_type="hiking_boot"))
    snow = score_item(req, ItemSpec("footwear", 0.08, footwear_type="hiking_boot", insulated=True))
    trail = score_item(req, ItemSpec("footwear", 0.03, footwear_type="trail_runner"))
    sneaker = score_item(req, ItemSpec("footwear", 0.03, footwear_type="sneaker"))
    assert not boot.passes and not snow.passes
    assert trail.passes and not trail.exact
    assert sneaker.passes and sneaker.exact


def test_socks_follow_the_heat_and_the_shoe():
    hot = _req("socks", "light", footwear_type="sneaker")
    assert not score_item(hot, ItemSpec("socks", 0.04)).passes  # winter socks on a hot day
    assert score_item(hot, ItemSpec("socks", 0.02, cut="low")).exact
    boots = _req("socks", "medium", footwear_type="hiking_boot")
    assert not score_item(boots, ItemSpec("socks", 0.02, cut="low")).passes


def test_offline_estimate_uses_the_months_normals():
    from datetime import date
    rome = estimate_day(41.9, 30, date(2027, 8, 15), 12.48)
    assert rome.precip_prob < 30 and rome.tmax > 28  # not the old flat 35% rain chance
