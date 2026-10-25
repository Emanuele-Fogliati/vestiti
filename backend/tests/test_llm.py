import json

import httpx
import pytest

from app.config import Settings
from app.llm.client import LLMClient, LLMUnavailable, parse_json_loose
from app.llm.itinerary import parse_itinerary


def settings(**kw):
    kw.setdefault("llm_api", "openai")
    kw.setdefault("llm_base_url", "http://llm.test/v1")
    return Settings(llm_enabled=True, llm_model="hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M", **kw)


def transport(reply: str, seen: list):
    def handler(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M"}]})
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})
    return httpx.MockTransport(handler)


def test_chat_strips_thinking_and_disables_it_for_qwen3():
    seen = []
    c = LLMClient(settings(), transport("<think>hmm</think>Hello", seen))
    assert c.chat("sys", "hi") == "Hello"
    assert seen[0]["messages"][1]["content"].endswith("/no_think")


def test_parse_json_loose():
    assert parse_json_loose('Sure! ```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_loose('{"a": [1, 2]} trailing') == {"a": [1, 2]}


def test_unreachable_server_raises():
    def boom(req):
        raise httpx.ConnectError("refused")
    c = LLMClient(settings(), httpx.MockTransport(boom))
    with pytest.raises(LLMUnavailable):
        c.chat("s", "u")
    assert c.status()["available"] is False


def test_itinerary_from_llm_json():
    reply = json.dumps({"trip_name": "Patagonia", "stops": [
        {"name": "El Chaltén", "start_date": "2027-05-06", "end_date": "2027-05-09",
         "activities": [{"type": "hiking", "difficulty": "hard", "max_altitude_m": 1200}]},
        {"name": "Ushuaia", "start_date": "2027-05-10", "end_date": "2027-05-12", "activities": [{"type": "city"}]},
    ]})
    c = LLMClient(settings(), transport(reply, []))
    d = parse_itinerary("anything", client=c)
    assert d.parser == "llm" and [s.name for s in d.stops] == ["El Chaltén", "Ushuaia"]


def test_bad_llm_output_falls_back_to_rules():
    c = LLMClient(settings(), transport("I cannot do that", []))
    d = parse_itinerary("From 1 May 2027: 2 days in Paris", client=c)
    assert d.parser == "rules" and d.stops[0].name == "Paris"


def test_long_text_uses_ollama_native_api_with_big_context():
    seen, paths = [], []

    def handler(req: httpx.Request):
        paths.append(req.url.path)
        body = json.loads(req.content)
        seen.append(body)
        reply = {"trip_name": "Peru", "stops": [{"name": "Lima", "start_date": "2027-05-01",
                 "end_date": "2027-05-02", "activities": [{"type": "city"}]}]}
        return httpx.Response(200, json={"message": {"content": json.dumps(reply)}})

    c = LLMClient(settings(llm_api="ollama"), httpx.MockTransport(handler))
    text = "Giorno 1: Lima. Visita del centro storico e dei musei. " * 700  # ~40k chars
    d = parse_itinerary(text, client=c)
    assert d.parser == "llm" and paths == ["/api/chat"]
    opts = seen[0]["options"]
    assert opts["num_ctx"] >= 16384 and opts["num_ctx"] <= 32768
    assert opts["num_predict"] == 4096 and seen[0]["format"] == "json" and seen[0]["think"] is False


def test_auto_detects_ollama_and_short_text_keeps_openai_path():
    paths = []

    def handler(req: httpx.Request):
        paths.append(req.url.path)
        if req.url.path == "/api/version":
            return httpx.Response(404)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    LLMClient._ollama_cache.clear()
    c = LLMClient(settings(llm_api="auto", llm_base_url="http://other.test/v1"), httpx.MockTransport(handler))
    assert c.chat("s", "u", num_ctx=8192) == "ok"
    assert paths == ["/api/version", "/v1/chat/completions"]


def test_one_stop_per_day_from_the_model_is_merged_and_checked_against_the_text():
    from tests.fixtures_patagonia import BAD_LLM, PATAGONIA
    seen = []
    c = LLMClient(settings(), transport(json.dumps(BAD_LLM), seen))
    d = parse_itinerary(PATAGONIA, client=c)
    assert d.parser == "llm"
    assert [s.name for s in d.stops] == ["Buenos Aires", "El Calafate", "El Chaltén",
                                         "Puerto Natales", "Torres del Paine", "Ushuaia"]
    by = {s.name: s for s in d.stops}
    # dates come from the "Giorno N" numbers, not from the model
    assert (by["Ushuaia"].start_date.day, by["El Chaltén"].end_date.day) == (26, 22)
    acts = [a for s in d.stops for a in s.activities]
    assert all(a.type != "trek_multiday" for a in acts)  # nothing says huts or tents
    assert all(a.max_altitude_m in (None, 1200) for a in acts)  # 2,500 m was invented
    assert by["El Chaltén"].activities[0].max_altitude_m == 1200
    assert by["Buenos Aires"].activities == [type(acts[0])(type="city")]
    assert {"boat", "hiking"} <= {a.type for a in by["Torres del Paine"].activities}
    assert "safari" not in {a.type for a in acts}
    notes = " ".join(s.notes or "" for s in d.stops)
    assert "comprende" not in notes and "abbigliamento" not in notes.lower()  # boilerplate
    assert "ramponi" in (by["Ushuaia"].notes or "")  # facts of the stop stay
    assert "in Italian" in seen[0]["messages"][1]["content"]
    # packing advice ("scarpe comode per i sentieri") is not a hike
    assert [a.type for a in by["Buenos Aires"].activities] == ["city"]
    assert [a.type for a in by["Puerto Natales"].activities] == ["city"]
    hikes = {s.name: next(a for a in s.activities if a.type == "hiking") for s in d.stops
             if any(a.type == "hiking" for a in s.activities)}
    assert {n: h.difficulty for n, h in hikes.items()} == {
        "El Calafate": "easy", "El Chaltén": "hard", "Torres del Paine": "hard", "Ushuaia": "hard"}
    assert {n for n, h in hikes.items() if h.glacier} == {"El Calafate", "Ushuaia"}
    assert d.questions == []  # dates are in the text; the model's own questions are dropped


def _llm(reply):
    return LLMClient(settings(), transport(json.dumps(reply), []))


@pytest.mark.parametrize("filler", [0, 6])
def test_generated_patagonia_dates_come_from_day_numbers(filler):
    from datetime import date

    from tests.fixtures_patagonia import GEN_BAD_LLM, GEN_EXPECTED, generated
    text = generated(filler)
    for d in (parse_itinerary(text, today=date(2026, 10, 25), client=_llm(GEN_BAD_LLM)),
              parse_itinerary(text, today=date(2026, 10, 25), use_llm=False)):
        assert [(s.name, s.start_date.day, s.end_date.day) for s in d.stops] == GEN_EXPECTED
        by = {(s.name, s.start_date.day): s for s in d.stops}
        for key in (("Buenos Aires", 16), ("Puerto Natales", 23), ("Buenos Aires", 30)):
            assert [a.type for a in by[key].activities] == ["city"], key  # filler mentions "sentieri"
        hike = {s.name: a for s in d.stops for a in s.activities if a.type == "hiking"}
        assert hike["El Chaltén"].difficulty == hike["Torres del Paine"].difficulty == "hard"
        assert hike["Ushuaia"].difficulty == "hard" and hike["Ushuaia"].glacier
        assert hike["El Calafate"].glacier
        assert "neve" in by[("Torres del Paine", 24)].notes and "ramponi" in by[("Ushuaia", 26)].notes
        assert d.questions == []
        assert all("abbigliamento" not in (s.notes or "").lower() for s in d.stops)


def test_peru_program_from_an_agency_page():
    from datetime import date

    from tests.fixtures_peru import PERU, PERU_BAD_LLM
    today = date(2026, 10, 25)
    for d in (parse_itinerary(PERU, today=today, client=_llm(PERU_BAD_LLM)),
              parse_itinerary(PERU, today=today, use_llm=False)):
        # a stop is where the traveller sleeps ("Pernottamento a Puno"); no Italy days
        assert [s.name for s in d.stops] == ["Cuzco", "Aguas Calientes", "Cusco", "Puno", "Taquile",
                                             "Chivay", "Arequipa", "Paracas", "Lima"]
        # no dates in the text: day 1 (leaving Italy) is 30 days from today, Cuzco is day 2
        assert [((s.start_date - today).days, (s.end_date - today).days) for s in d.stops] == [
            (31, 32), (33, 34), (35, 35), (36, 36), (37, 37), (38, 38), (39, 40), (41, 41), (42, 42)]
        assert len(d.questions) == 1 and d.questions[0].startswith("Quando parti")
        by = {s.name: s for s in d.stops}
        # the altitude of each night comes from the text
        assert {n: s.elevation_m for n, s in by.items() if s.elevation_m} == {
            "Cuzco": 3400, "Aguas Calientes": 2040, "Cusco": 3400, "Puno": 3827, "Taquile": 4072,
            "Chivay": 3600, "Arequipa": 2500}
        rainbow = next(a for a in by["Puno"].activities if a.type == "hiking")
        assert (rainbow.difficulty, rainbow.max_altitude_m) == ("hard", 5200)
        assert "boat" in {a.type for a in by["Taquile"].activities}
        assert "boat" not in {a.type for a in by["Chivay"].activities}  # the boat back is a transfer
        assert "boat" in {a.type for a in by["Lima"].activities}  # Isole Ballestas
        assert "desert" in {a.type for a in by["Paracas"].activities}
        assert all(a.type != "unknown" for s in d.stops for a in s.activities)  # "patate (forse)"
        assert "homestay" in by["Taquile"].notes
        assert "5200" in by["Puno"].notes and "…" not in by["Puno"].notes
        assert by["Cuzco"].notes is None  # the overnight line is the altitude, not a note
        notes = " ".join(s.notes or "" for s in d.stops)
        assert "Dune buggy e sandboarding Arriviamo" not in notes  # taglines are not sentences


def test_peru_round4_model_answer_is_corrected_by_the_text():
    from datetime import date

    from tests.fixtures_peru import PERU, PERU_PC_LLM
    d = parse_itinerary(PERU, today=date(2026, 10, 25), client=_llm(PERU_PC_LLM))
    by = {s.name: s for s in d.stops}
    hike = next(a for a in by["Puno"].activities if a.type == "hiking")
    assert (hike.difficulty, hike.max_altitude_m) == ("hard", 5200)  # "non facilitano" is not "facile"
    assert "hiking" not in {a.type for a in by["Cusco"].activities}  # "potremo scegliere se ..."
