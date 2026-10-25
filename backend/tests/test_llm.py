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
    assert (by["Ushuaia"].start_date.day, by["El Chaltén"].end_date.day) == (27, 23)
    acts = [a for s in d.stops for a in s.activities]
    assert all(a.type != "trek_multiday" for a in acts)  # nothing says huts or tents
    assert all(a.max_altitude_m in (None, 1200) for a in acts)  # 2,500 m was invented
    assert by["El Chaltén"].activities[0].max_altitude_m == 1200
    assert by["Buenos Aires"].activities == [type(acts[0])(type="city")]
    assert {"boat", "hiking"} <= {a.type for a in by["Torres del Paine"].activities}
    assert "safari" not in {a.type for a in acts}
    assert all(s.notes is None for s in d.stops)  # the same boilerplate on every stop
    assert "in Italian" in seen[0]["messages"][1]["content"]
