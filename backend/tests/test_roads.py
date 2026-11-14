"""Trip legs along the roads (app.api.roads): flights far apart, straight line without network."""
from app.api import roads


def test_far_stops_fly_on_a_great_circle(client):
    r = client.get("/api/roads", params={"pts": "41.9,12.5;-13.5,-71.97"}).json()
    leg = r["legs"][0]
    assert leg["mode"] == "air" and len(leg["line"]) == 33
    assert leg["line"][0] == [12.5, 41.9] and leg["line"][-1] == [-71.97, -13.5]


def test_near_stops_without_network_are_a_line(client):
    r = client.get("/api/roads", params={"pts": "-13.53,-71.97;-13.26,-72.26;-13.16,-72.52"}).json()
    assert [x["mode"] for x in r["legs"]] == ["line", "line"]


def test_bad_points(client):
    assert client.get("/api/roads", params={"pts": "1,2"}).status_code == 422
    assert client.get("/api/roads", params={"pts": "x;y"}).status_code == 422
    assert client.get("/api/roads", params={"pts": "95,0;1,1"}).status_code == 422


def test_arc_is_a_great_circle():
    a = roads.arc((0, 0), (0, 90), 2)
    assert a[1] == [45.0, 0.0]
