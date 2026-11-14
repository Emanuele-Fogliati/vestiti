"""The days of a booked trip hour by hour (app.llm.dayplan): the draft from facts, and the model's
version checked so that it can never lose or move a flight, a drive or a bed."""
from datetime import date
from pathlib import Path

from app.llm import dayplan
from app.llm.client import LLMUnavailable
from app.services import booked

MANU = (Path(__file__).parent / "fixtures" / "booked_patagonia_it.txt").read_text(encoding="utf-8")
R = booked.read(MANU, date(2026, 11, 14))


class Settings:
    llm_long_timeout_s = 5
    llm_model = "fake"


class Fake:
    s = Settings()

    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def chat_json(self, system, user, **kw):
        self.asked.append((system, user))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer(user) if callable(self.answer) else self.answer


def _day(d, when):
    return next(x for x in d["days"] if x["date"] == when)


def test_draft_has_every_move_in_order_and_the_guide_hours():
    d = dayplan.rules_days(R)
    assert len(d["days"]) == 15 and d["source"] == "rules"
    first = [r["what"] for r in _day(d, "2027-01-16")["rows"]]
    assert first[0].startswith("Flight Turin") and first[-1].endswith("(next day)")
    natales = [r["what"] for r in _day(d, "2027-01-17")["rows"]]
    assert natales.index("Pick up the car (Hertz)") < natales.index("Border: Río Turbio–Dorotea")
    assert natales[-1] == "Sleep: Hostal Turpial Patagonia, Manuel Bulnes 354"
    torres = _day(d, "2027-01-18")
    assert torres["priority"] == 1 and torres["rows"][0]["at"] == "07:00" and torres["rows"][0]["effort"] == "high"
    assert torres["rows"][0]["note"].startswith("Start early")
    back = [r["what"] for r in _day(d, "2027-01-26")["rows"]]
    assert back.index("Stop at Perito Moreno Glacier (late morning)") < back.index("Car back by 16:00")
    assert all(x["priority"] is None for x in d["days"] if x["date"] in ("2027-01-16", "2027-01-22", "2027-01-29"))
    assert [w["drop"] for w in d["weather"]] == ["2027-01-21", "2027-01-25", "2027-01-28"]


def test_groups_one_base_each():
    gs = dayplan.groups(R)
    tl = R["timeline"]
    assert [[tl[k]["date"] for k in g][0] for g in gs] == ["2027-01-16", "2027-01-22", "2027-01-26"]
    assert sum(len(g) for g in gs) == 15


def test_language_of_the_text():
    assert dayplan.lang_of(MANU) == "Italian"
    assert dayplan.lang_of("We fly to Lima on 3 March, then two nights in Cusco and the train") == "English"


def test_model_answer_is_checked():
    def answer(user):
        return {"days": [
            {"date": "2027-01-22", "title": "Verso El Chaltén", "priority": 7, "rows": [
                {"at": "07:00", "what": "Partenza in auto da Puerto Natales", "effort": None},
                {"at": "25:99", "what": "Orario impossibile", "effort": "extreme"},
                {"at": "~14:30", "what": "Spesa al supermercato a El Calafate", "effort": "zero", "optional": True},
                {"what": ""},
            ]},
            {"date": "2099-01-01", "title": "A day not asked", "rows": [{"at": "10:00", "what": "x"}]},
        ], "weather": {"drop": "2027-01-25", "how": "Se piove, salta il Pliegue Tumbado"}}

    fake = Fake(answer)
    out = dayplan.ai_days(R, 1, "camminatori lenti", "Italian", client=fake)
    assert out["source"] == "llm" and out["groups"] == 3
    assert [d["date"] for d in out["days"]] == ["2027-01-22", "2027-01-23", "2027-01-24", "2027-01-25"]
    d22 = out["days"][0]
    whats = [r["what"] for r in d22["rows"]]
    assert "Orario impossibile" in whats and next(r for r in d22["rows"] if r["what"] == "Orario impossibile")["at"] is None
    assert next(r for r in d22["rows"] if r["what"] == "Orario impossibile")["effort"] is None
    assert "Drive Puerto Natales → El Chaltén, via El Calafate" not in whats  # kept in its own words at 07:00
    assert "Border: Cerro Castillo" in whats  # lost by the model: put back
    assert whats[-1] == "Sleep: Patagonia Hostel, Avenida San Martín 376"
    assert d22["priority"] == 7
    assert out["days"][1]["rows"][0]["at"] == "06:00"  # days it did not write stay the draft
    assert out["weather"] == [{"area": "", "drop": "2027-01-25", "how": "Se piove, salta il Pliegue Tumbado"}]
    system, user = fake.asked[0]
    assert "Italian" in system and "camminatori lenti" in user and "Laguna de los Tres" in user


def test_without_a_model_the_draft_is_the_answer():
    out = dayplan.ai_days(R, 0, client=Fake(LLMUnavailable("down")))
    assert out["source"] == "rules" and out["why"] == "down" and len(out["days"]) == 6
    out = dayplan.ai_days(R, 2, client=Fake(ValueError("bad json")))
    assert out["source"] == "rules" and out["days"][0]["date"] == "2027-01-26"


def test_api_days(client):
    client.post("/api/auth/guest")
    j = client.post("/api/plan/understand", json={"text": MANU}).json()
    assert j["groups"] == 3 and j["lang"] == "Italian" and len(j["plan_days"]) == 15 and j["days"] == 15
    r = client.post("/api/plan/days", json={"text": MANU, "group": 2, "wishes": "niente barche"})
    assert r.status_code == 200, r.text
    assert r.json()["days"][0]["date"] == "2027-01-26"
    assert client.post("/api/plan/days", json={"text": MANU, "group": 9}).status_code == 422
    assert client.post("/api/plan/days", json={"text": "Patagonia a gennaio", "group": 0}).status_code == 422
