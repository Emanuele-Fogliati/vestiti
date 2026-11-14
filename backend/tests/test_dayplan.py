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
    assert out["weather"] == [{"area": "El Chaltén", "drop": "2027-01-25", "how": "Se piove, salta il Pliegue Tumbado"}]
    system, user = fake.asked[0]
    assert "Italian" in system and "camminatori lenti" in user and "Laguna de los Tres" in user
    assert "Follow the WISHES" in user
    kept = next(r for r in d22["rows"] if r["what"] == "Partenza in auto da Puerto Natales")
    assert kept["fixed"] and kept["effort"] is None


def test_overnight_flights_and_beds_stay_in_place_in_the_models_words():
    def answer(user):
        return {"days": [
            {"date": "2027-01-16", "title": "Verso Buenos Aires", "rows": [
                {"at": "04:40", "what": "Arrivo a Buenos Aires (Ezeiza) (giorno dopo)"},
                {"at": "11:15", "what": "Volo Torino → Buenos Aires (Ezeiza), via Roma"}]},
            {"date": "2027-01-29", "title": "Buenos Aires", "rows": [
                {"at": "08:20", "what": "Volo Ushuaia → Buenos Aires (Aeroparque)"},
                {"at": "16:00", "what": "Cimitero della Recoleta", "effort": "low"},
                {"at": "16:00", "what": "Arrivo a Roma (Fiumicino) (giorno dopo)"},
                {"at": "22:35", "what": "Volo Buenos Aires (Ezeiza) → Roma (Fiumicino)"},
                {"at": "16:00", "what": "Cimitero della Recoleta", "effort": "low"}]},
            {"date": "2027-01-27", "title": "Canale Beagle", "rows": [
                {"at": "09:30", "what": "Al molo turistico"},
                {"what": "Dormi: Ushuaia Center Apartment Suit"}, {"at": "13:00", "what": "Pranzo"}]},
        ]}

    first = dayplan.ai_days(R, 0, "", "Italian", client=Fake(answer))["days"][0]
    assert [r["at"] for r in first["rows"]] == ["11:15", "04:40"]
    out = dayplan.ai_days(R, 2, "", "Italian", client=Fake(answer))["days"]
    ba = next(d for d in out if d["date"] == "2027-01-29")["rows"]
    whats = [r["what"] for r in ba]
    assert whats.count("Cimitero della Recoleta") == 1
    assert whats[-1] == "Arrivo a Roma (Fiumicino) (giorno dopo)" and ba[-1]["fixed"]
    assert not next(r for r in ba if r["what"] == "Cimitero della Recoleta")["fixed"]
    beagle = next(d for d in out if d["date"] == "2027-01-27")["rows"]
    assert beagle[-1]["what"] == "Dormi: Ushuaia Center Apartment Suit" and beagle[-1]["fixed"]


def test_without_a_model_the_draft_is_the_answer():
    out = dayplan.ai_days(R, 0, client=Fake(LLMUnavailable("down")))
    assert out["source"] == "rules" and out["why"] == "down" and len(out["days"]) == 6
    out = dayplan.ai_days(R, 2, client=Fake(ValueError("bad json")))
    assert out["source"] == "rules" and out["days"][0]["date"] == "2027-01-26"


def test_api_days(client):
    client.post("/api/auth/guest")
    j = client.post("/api/plan/understand", json={"text": MANU}).json()
    assert j["groups"] == 3 and j["lang"] == "English" and len(j["plan_days"]) == 15 and j["days"] == 15
    r = client.post("/api/plan/days", json={"text": MANU, "group": 2, "wishes": "niente barche"})
    assert r.status_code == 200, r.text
    assert r.json()["days"][0]["date"] == "2027-01-26"
    assert client.post("/api/plan/days", json={"text": MANU, "group": 9}).status_code == 422
    assert client.post("/api/plan/days", json={"text": "Patagonia a gennaio", "group": 0}).status_code == 422


def test_wishes_the_code_keeps_even_without_a_model():
    assert dayplan.wants("camminiamo piano, niente barche") == {"no_boat": True, "slow": True}
    assert dayplan.wants("we love boats and long hikes") == {"no_boat": False, "slow": False}
    d = dayplan.rules_days(R, "camminiamo piano, niente barche")
    grey = _day(d, "2027-01-20")
    assert "Grey Glacier" not in grey["title"] and any(r["what"] == "Left out for you: Grey Glacier by boat" for r in grey["rows"])
    french = _day(d, "2027-01-19")["rows"][0]
    assert french["optional"] and "Needs a boat" in french["note"]
    torres = _day(d, "2027-01-18")["rows"][0]
    assert torres["optional"] and torres["note"].startswith("Hard for an easy pace")
    assert not any(r["what"] == "Out along the Beagle Channel" for r in _day(d, "2027-01-27")["rows"])
    assert _day(d, "2027-01-28")["title"] == "Free day"
    out = dayplan.ai_days(R, 2, "niente barche", client=Fake(LLMUnavailable("down")))
    assert any(r["what"].startswith("Left out for you: Beagle") for r in out["days"][1]["rows"])
    fake = Fake({"days": [{"date": "2027-01-23", "rows": [
        {"at": "06:00", "what": "Laguna de los Tres", "effort": "high"},
        {"at": "18:00", "what": "Giro in barca sul lago", "effort": "low"}]}]})
    rows = dayplan.ai_days(R, 1, "piano, niente barche", "Italian", client=fake)["days"][1]["rows"]
    assert all(r["optional"] for r in rows if not r["fixed"])
    assert "Grey Glacier by boat" not in fake.asked[0][1]


def test_models_slips_are_mended():
    fake = Fake({"days": [
        {"date": "2027-01-17", "rows": [
            {"at": "11:15", "what": "Volo Buenos Aires (Ezeiza) → El Calafate"},
            {"at": "12:00", "what": "Ritiro auto Hertz"}]},
        {"date": "2027-01-22", "rows": [
            {"at": "07:00", "what": "Partenza in auto per El Chaltén"},
            {"what": "≈ 7–8 h in auto"},
            {"at": "~17:00", "what": "Mirador de los Cóndores"}]},
        {"date": "2027-01-18", "rows": [{"at": "07:00", "what": "Partenza dal Welcome Centre"}]}],
        "weather": {"drop": "2027-01-27", "how": "Se piove, sposta il parco"}})
    out = dayplan.ai_days(R, 0, "", "Italian", client=fake)["days"]
    d17 = [r["what"] for r in _day({"days": out}, "2027-01-17")["rows"]]
    assert "Volo Buenos Aires (Ezeiza) → El Calafate" not in d17 and "Flight Buenos Aires (Ezeiza) → El Calafate" in d17
    assert _day({"days": out}, "2027-01-18")["rows"][0]["effort"] == "high"  # the guide's effort
    g1 = dayplan.ai_days(R, 1, "", "Italian", client=fake)["days"][0]["rows"]
    assert [r["what"] for r in g1].count("≈ 7–8 h on the road") == 0 and any(r["what"] == "≈ 7–8 h in auto" and r["fixed"] for r in g1)
    assert dayplan.ai_days(R, 2, "niente barche", "Italian", client=fake)["weather"][0]["area"] == "Ushuaia"
    d22 = _day(dayplan.rules_days(R), "2027-01-22")["rows"]
    assert next(r for r in d22 if r["what"].startswith("Mirador de los Cóndores"))["at"] == "~17:00"


def test_api_writes_in_english_whatever_the_text(client, monkeypatch):
    client.post("/api/auth/guest")
    seen = {}

    def fake(reading, group, wishes, lang):
        seen["lang"] = lang
        return {"group": group, "groups": 3, "days": [], "weather": [], "source": "rules", "model": None}

    monkeypatch.setattr(dayplan, "ai_days", fake)
    assert client.post("/api/plan/days", json={"text": MANU, "group": 0, "wishes": "camminiamo piano"}).status_code == 200
    assert seen["lang"] == "English"
