"""Provider-agnostic LLM client: any server that speaks the OpenAI chat-completions API.

Default target is a local Ollama serving a Qwen GGUF from Unsloth on Hugging Face:
    ollama pull hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M
llama.cpp (`llama-server`), vLLM and LM Studio expose the same /v1 API, so switching is
only LLM_BASE_URL + LLM_MODEL. See docs/AI_SETUP.md.

The app never depends on this for correctness: weather, layering, warmth math and
pricing are deterministic. The LLM only parses free text, rewrites explanations and
answers questions, and every caller has a non-LLM fallback.
"""
from __future__ import annotations

import json
import logging
import re
import time

import httpx

from app.config import Settings, get_settings

log = logging.getLogger(__name__)
_THINK = re.compile(r"<think>.*?</think>", re.S)


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    _status_cache: dict[str, tuple[float, bool, str]] = {}

    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None):
        self.s = settings or get_settings()
        self.transport = transport

    def _client(self, timeout: float) -> httpx.Client:
        headers = {"Authorization": f"Bearer {self.s.llm_api_key}"} if self.s.llm_api_key else {}
        return httpx.Client(base_url=self.s.llm_base_url.rstrip("/"), timeout=timeout,
                            headers=headers, transport=self.transport, trust_env=False)

    def status(self) -> dict:
        """Is the model server reachable and does it list our model? Cached for 30 s."""
        if not self.s.llm_enabled:
            return {"enabled": False, "available": False, "model": self.s.llm_model,
                    "base_url": self.s.llm_base_url, "detail": "LLM_ENABLED=false"}
        key = f"{self.s.llm_base_url}|{self.s.llm_model}"
        hit = self._status_cache.get(key)
        if hit and time.time() - hit[0] < 30:
            ok, detail = hit[1], hit[2]
        else:
            ok, detail = False, ""
            try:
                with self._client(3.0) as c:
                    r = c.get("/models")
                    r.raise_for_status()
                    ids = [m.get("id", "") for m in r.json().get("data", [])]
                    listed = any(self.s.llm_model == i or self.s.llm_model in i for i in ids)
                    # llama.cpp ignores the model name, so a reachable server counts as up;
                    # Ollama without the model pulled will fail on chat and we fall back.
                    ok = True
                    detail = "ok" if listed else (
                        f"server reachable but '{self.s.llm_model}' not listed "
                        f"(has: {', '.join(ids[:5]) or 'nothing'})")
            except Exception as e:
                detail = f"unreachable: {e.__class__.__name__}"
            self._status_cache[key] = (time.time(), ok, detail)
        return {"enabled": True, "available": ok, "model": self.s.llm_model,
                "base_url": self.s.llm_base_url, "detail": detail}

    def chat(self, system: str, user: str, json_mode: bool = False, temperature: float = 0.2,
             max_tokens: int = 1200) -> str:
        if not self.s.llm_enabled:
            raise LLMUnavailable("LLM disabled")
        if self.s.llm_disable_thinking and "qwen3" in self.s.llm_model.lower():
            user = user + "\n/no_think"
        body = {
            "model": self.s.llm_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            with self._client(self.s.llm_timeout_s) as c:
                r = c.post("/chat/completions", json=body)
                r.raise_for_status()
                text = r.json()["choices"][0]["message"]["content"] or ""
        except Exception as e:
            log.info("LLM call failed: %s", e)
            raise LLMUnavailable(str(e)) from e
        return _THINK.sub("", text).strip()

    def chat_json(self, system: str, user: str, **kw) -> dict:
        text = self.chat(system, user, json_mode=True, **kw)
        return parse_json_loose(text)


def parse_json_loose(text: str) -> dict:
    """Small local models sometimes wrap JSON in prose or code fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))
