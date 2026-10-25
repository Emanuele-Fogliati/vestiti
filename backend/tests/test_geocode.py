"""Trip-aware geocoding: a stop name is read in the trip's country, near its neighbours."""
import httpx
import pytest

from app.config import get_settings
from app.weather import geocode


def _r(name, admin, cc, lat, lon, pop=0, feature="PPL"):
    return {"name": name, "admin1": admin, "country_code": cc, "country": cc, "latitude": lat,
            "longitude": lon, "elevation": 0, "population": pop, "feature_code": feature}


WORLD = {
    "Lima": [_r("Lima", "Lima", "PE", -12.04, -77.03, 7_700_000, "PPLC"),
             _r("Lima", "Ohio", "US", 40.74, -84.1, 38_000)],
    "Cusco": [_r("Cusco", "Cusco", "PE", -13.53, -71.97, 428_000, "PPLA")],
    "Puno": [_r("Puno", "Puno", "PE", -15.84, -70.02, 116_000, "PPLA")],
    "Aguas Calientes": [_r("Aguas Calientes", "Guerrero", "MX", 17.3, -99.6, 900),
                        _r("Aguas Calientes", "Chihuahua", "MX", 28.4, -106.0, 500)],
}
PERU_ONLY = {"Aguas Calientes": [_r("Aguas Calientes", "Arequipa", "PE", -15.6, -72.9, 50),
                                 _r("Aguas Calientes", "Cuzco Department", "PE", -13.155, -72.52, 4000)]}


def _transport(seen):
    def handle(req):
        q, cc = req.url.params["name"], req.url.params.get("countryCode")
        seen.append((q, cc))
        res = PERU_ONLY.get(q, []) if cc == "PE" else WORLD.get(q, [])
        return httpx.Response(200, json={"results": res})
    return httpx.MockTransport(handle)


@pytest.fixture
def online(monkeypatch):
    s = get_settings().model_copy(update={"weather_enabled": True})
    monkeypatch.setattr(geocode, "get_settings", lambda: s)


def test_trip_country_and_neighbours_pick_the_right_place(online):
    seen = []
    with httpx.Client(transport=_transport(seen)) as c:
        out = geocode.resolve_trip(["Lima", "Cuzco", "Aguas Calientes", "Puno"], client=c)
    picks = [m[0] for m in out]
    assert ("Cusco", None) in seen  # alias: GeoNames has no city called "Cuzco"
    assert [p["country_code"] for p in picks] == ["PE"] * 4
    assert picks[2]["admin"] == "Cuzco Department"  # the one next to Cusco, not Arequipa's
    assert picks[0]["admin"] == "Lima"


def test_single_place_search_is_unchanged(online):
    with httpx.Client(transport=_transport([])) as c:
        out = geocode.resolve_trip(["Lima"], client=c)
    assert out[0][0]["country_code"] == "PE"


def test_a_sight_is_placed_at_the_town_you_sleep_in(online):
    # GeoNames knows a village "Titicaca" in the Amazon, not the lake: use Puno, keep the name
    seen = []
    c = httpx.Client(transport=_transport(seen))
    found = geocode.resolve_trip(["Lima", "Cusco", "Titicaca"], client=c)
    t = found[2][0]
    assert (t["name"], t["admin"], round(t["latitude"], 2)) == ("Titicaca", "Puno", -15.84)
