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
import threading
import time

import httpx

from app.config import Settings, get_settings

log = logging.getLogger(__name__)
_THINK = re.compile(r"<think>.*?</think>", re.S)


class LLMUnavailable(RuntimeError):
    pass


# One model server (a single GPU) serves everyone. Without a cap, a few long itineraries
# (up to 10 minutes each) tie up every worker thread and the GPU, and the site hangs.
# Calls over the cap wait a little, then the caller uses its rule-based fallback.
_slots: threading.BoundedSemaphore | None = None
_slots_lock = threading.Lock()


def _llm_slots(n: int) -> threading.BoundedSemaphore:
    global _slots
    with _slots_lock:
        if _slots is None:
            _slots = threading.BoundedSemaphore(max(1, n))
        return _slots


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

    def public_status(self) -> dict:
        """What any visitor may see: no server address, no list of the models on it."""
        st = self.status()
        return {"enabled": st["enabled"], "available": st["available"], "model": st["model"]}

    def _root(self) -> str:
        return re.sub(r"/v1/?$", "", self.s.llm_base_url.rstrip("/"))

    _ollama_cache: dict[str, bool] = {}

    def is_ollama(self) -> bool:
        """True when the server is Ollama (its native API lets us set the context window)."""
        if self.s.llm_api in ("ollama", "openai"):
            return self.s.llm_api == "ollama"
        root = self._root()
        if root not in self._ollama_cache:
            try:
                with httpx.Client(timeout=3.0, transport=self.transport, trust_env=False) as c:
                    r = c.get(root + "/api/version")
                    self._ollama_cache[root] = r.status_code == 200 and "version" in r.json()
            except Exception:
                self._ollama_cache[root] = False
        return self._ollama_cache[root]

    def chat(self, system: str, user: str, json_mode: bool = False, temperature: float = 0.2,
             max_tokens: int = 1200, num_ctx: int | None = None,
             timeout: float | None = None) -> str:
        """One chat completion. num_ctx asks for a bigger context window (Ollama only;
        other servers use the context size they were started with)."""
        if not self.s.llm_enabled:
            raise LLMUnavailable("LLM disabled")
        qwen3 = "qwen3" in self.s.llm_model.lower()
        if self.s.llm_disable_thinking and qwen3:
            user = user + "\n/no_think"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        timeout = timeout or self.s.llm_timeout_s
        slots = _llm_slots(self.s.llm_max_concurrent)
        if not slots.acquire(timeout=self.s.llm_queue_wait_s):
            raise LLMUnavailable("model busy")
        try:
            if num_ctx and self.is_ollama():
                body = {"model": self.s.llm_model, "messages": messages, "stream": False,
                        "options": {"temperature": temperature, "num_predict": max_tokens,
                                    "num_ctx": min(num_ctx, self.s.llm_num_ctx_max)}}
                if json_mode:
                    body["format"] = "json"
                if self.s.llm_disable_thinking and qwen3:
                    body["think"] = False
                with httpx.Client(timeout=timeout, transport=self.transport, trust_env=False) as c:
                    r = c.post(self._root() + "/api/chat", json=body)
                    r.raise_for_status()
                    text = (r.json().get("message") or {}).get("content") or ""
            else:
                body = {"model": self.s.llm_model, "messages": messages,
                        "temperature": temperature, "max_tokens": max_tokens, "stream": False}
                if json_mode:
                    body["response_format"] = {"type": "json_object"}
                with self._client(timeout) as c:
                    r = c.post("/chat/completions", json=body)
                    r.raise_for_status()
                    text = r.json()["choices"][0]["message"]["content"] or ""
        except Exception as e:
            log.info("LLM call failed: %s", e)
            raise LLMUnavailable(str(e)) from e
        finally:
            slots.release()
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
