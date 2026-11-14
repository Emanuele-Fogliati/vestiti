"""The ranking of what to do in each zone (docs/RANKING.md, Manu 2026-11-14)."""
from app import globe
from app.guide import rank, ready
from app.guide.todo import SCORE_KEYS, areas
from app.services import explore


def _area(aid):
    return next(a for a in areas() if a.id == aid)


def test_scores_follow_the_rubric():
    for a in areas():
        scored = [it for it in a.items if it.scores]
        for it in scored:
            if any(getattr(it.scores, k) == 5 for k in SCORE_KEYS):
                assert it.why, f"{a.id}/{it.id}: a 5 must be explained in why"
        if len(scored) < 4:
            continue
        for k in SCORE_KEYS:
            fives = sum(1 for it in scored if getattr(it.scores, k) == 5)
            assert fives <= len(scored) / 2, f"{a.id}: more than half the things have {k} 5"


def test_no_answers_keep_the_written_order():
    a = _area("ar-el-chalten")
    keep, hard = rank.ordered(a.items, None)
    assert [i.id for i in keep] == [i.id for i in a.items] and hard == []
    keep, _ = rank.ordered(a.items, rank.Prefs())
    assert keep[0].id == "laguna-de-los-tres"


def test_fitz_roy_first_even_for_culture():
    keep, _ = rank.ordered(_area("ar-el-chalten").items, rank.Prefs(likes=["culture", "history"]))
    assert keep[0].id == "laguna-de-los-tres"


def test_easy_drops_the_hard_walks_and_its_alternative_takes_the_place():
    keep, hard = rank.ordered(_area("ar-el-chalten").items, rank.Prefs(effort="easy"))
    assert keep[0].id == "laguna-capri"
    assert {"laguna-de-los-tres", "laguna-torre", "pliegue-tumbado"} <= {i.id for i in hard}
    assert all(rank.effort_of(i) <= 2 for i in keep)


def test_reads_what_the_traveller_likes():
    p = rank.read("Un viaggio spirituale in Giappone, niente trekking")
    assert p.effort == "easy" and "culture" in p.likes
    p = rank.read("Patagonia, I love hiking and photography")
    assert p.effort == "some" and {"landscape", "nature"} <= set(p.likes)
    assert rank.read("Patagonia a gennaio").empty()


def test_ready_trips_are_real_zones_of_their_region():
    P = globe.by_id()
    for t in ready.trips():
        a = explore.area(t.region)
        assert a, t.id
        for s in t.stops:
            p = P[s.place]
            assert explore.inside(a, p["lat"], p["lon"], p["country"]), f"{t.id}: {s.place} not in {t.region}"
            assert ready._area(p), f"{t.id}: {s.place} has no hand-written area"


def test_patagonia_week_is_the_ready_trip_with_fitz_roy_and_a_spare_day():
    p = explore.propose(explore.area("patagonia"), None, 7, 1)
    assert p["ready"]["id"] == "patagonia-7"
    assert [(s["key"], s["days"]) for s in p["stops"]] == [("ar-el-calafate", 3), ("ar-el-chalten", 4)]
    ch = p["stops"][1]["plan"]
    things = [i["id"] for d in ch for i in d.get("items", [])]
    assert "laguna-de-los-tres" in things
    assert ch[-1]["kind"] == "free"  # the buffer for the weather


def test_ready_trip_for_two_and_three_weeks_and_not_for_ten_days():
    a = explore.area("patagonia")
    assert explore.propose(a, None, 14, 1)["ready"]["id"] == "patagonia-14"
    assert explore.propose(a, None, 21, 1)["ready"]["id"] == "patagonia-21"
    assert explore.propose(a, None, 10, 1)["ready"] is None
    # a stop kept or dropped: the merged route, as before
    assert explore.propose(a, None, 14, 1, drop=["ar-ushuaia"])["ready"] is None


def test_easy_traveller_gets_no_fitz_roy_day():
    p = explore.propose(explore.area("patagonia"), None, 7, 1, prefs=rank.Prefs(effort="easy"))
    ch = p["stops"][1]
    things = [i["id"] for d in ch["plan"] for i in d.get("items", [])]
    assert "laguna-de-los-tres" not in things and "laguna-capri" in things
    assert "Laguna de los Tres, under Fitz Roy" in ch["also"]


def test_api_propose_with_the_two_answers(client):
    client.post("/api/auth/guest")
    r = client.post("/api/plan/propose", json={"area": "patagonia", "days": 7, "month": 1,
                                                "likes": ["landscape"], "effort": "easy"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ready"]["id"] == "patagonia-7" and j["effort"] == "easy" and j["likes"] == ["landscape"]
    assert client.post("/api/plan/propose", json={"area": "patagonia", "effort": "extreme"}).status_code == 422


def test_api_understand_reads_the_answers(client):
    client.post("/api/auth/guest")
    j = client.post("/api/plan/understand", json={"text": "Patagonia una settimana a gennaio, niente trekking"}).json()
    assert j["effort"] == "easy" and j["proposal"]["effort"] == "easy"
    assert j["proposal"]["ready"]["id"] == "patagonia-7"


def test_japan_two_weeks_is_the_ready_trip_through_the_alps():
    p = explore.propose(explore.area("c-jp"), None, 14, 4)
    assert p["ready"]["id"] == "japan-14"
    names = [s["name"] for s in p["stops"]]
    assert names[0] == "Tokyo" and "Kyoto" in names and "Takayama" in names
    assert sum(s["days"] for s in p["stops"]) == 14


def test_a_ready_round_trip_comes_back_to_the_start():
    p = explore.propose(explore.area("c-is"), None, 14, 7)
    assert p["ready"]["id"] == "iceland-14"
    keys = [s["key"] for s in p["stops"]]
    assert keys[0] == "is-reykjavik" and keys[-1] == "is-reykjavik~back"
    assert len(keys) == len(set(keys))
    p = explore.propose(explore.area("c-pe"), None, 14, 7)
    assert p["ready"]["id"] == "peru-14" and p["stops"][-1]["key"] == "pe-lima~back"
