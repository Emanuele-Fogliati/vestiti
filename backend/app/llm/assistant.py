"""LLM explanations and Q&A about a computed plan. The deterministic "why" text is
always the source of truth; the model only rephrases it or answers from it."""
from __future__ import annotations

import json

from app.llm.client import LLMClient, LLMUnavailable

EXPLAIN_SYSTEM = """You explain a travel clothing plan to a traveller in plain English.
Use ONLY the facts in the JSON you are given. Never invent temperatures, products or prices.
Keep it under 90 words, friendly and direct, no lists, no markdown headings.
If the facts say the clothing model is an estimate, say so briefly."""

ASK_SYSTEM = """You answer a traveller's question about their packing plan.
Use ONLY the plan facts given as JSON. If the answer is not in the facts, say you don't know
and suggest what to check. Under 120 words. Never recommend products that are not in the facts.
Never claim certainty about weather beyond the given data."""


def explain(topic: str, facts: dict, fallback: str, client: LLMClient | None = None) -> dict:
    client = client or LLMClient()
    try:
        text = client.chat(EXPLAIN_SYSTEM,
                           f"Explain: {topic}\nFacts:\n{json.dumps(facts, default=str)[:6000]}",
                           temperature=0.3, max_tokens=300)
        if text:
            return {"text": text, "source": "llm", "model": client.s.llm_model}
    except LLMUnavailable:
        pass
    return {"text": fallback, "source": "rules", "model": None}


def ask(question: str, facts: dict, client: LLMClient | None = None) -> dict:
    client = client or LLMClient()
    try:
        text = client.chat(ASK_SYSTEM,
                           f"Question: {question}\nPlan facts:\n{json.dumps(facts, default=str)[:9000]}",
                           temperature=0.2, max_tokens=400)
        if text:
            return {"text": text, "source": "llm", "model": client.s.llm_model}
    except LLMUnavailable:
        pass
    notes = []
    for st in facts.get("stages", [])[:6]:
        notes.append(f"{st.get('name')}: " + " ".join(st.get("notes", [])[:2]))
    return {"text": "The AI assistant is offline right now, so here is what the plan says. "
                    + " ".join(notes), "source": "rules", "model": None}
