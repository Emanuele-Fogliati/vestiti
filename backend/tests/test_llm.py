import json

import httpx
import pytest

from app.config import Settings
from app.llm.client import LLMClient, LLMUnavailable, parse_json_loose
from app.llm.itinerary import parse_itinerary


def settings(**kw):
    return Settings(llm_enabled=True, llm_base_url="http://llm.test/v1", llm_model="hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M", **kw)


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
