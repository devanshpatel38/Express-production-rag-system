"""Adaptive query router.

The first decision in a self-healing loop should NOT be "embed and retrieve".
It should be "is this even a question we should try to answer?". If the user
asks something off-topic, retrieval will find junk, grading will reject it,
the rewriter will spin its wheels, and we'll burn three LLM calls before
giving up. Routing upfront is the cheap escape hatch.

Three buckets:
  - clear      : an Express question; run the standard pipeline
  - ambiguous  : likely Express but vague ("how does that work?"); turn on HyDE
  - off_topic  : not about Express; short-circuit with a polite redirect

We use a tiny constrained prompt and a single token of output so this stage
adds ~150ms, not seconds. If the classifier itself fails we default to `clear`
so the system stays useful even when the router is misbehaving.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from app.config import get_settings


Intent = Literal["clear", "ambiguous", "off_topic"]


@dataclass
class RoutingDecision:
    intent: Intent
    reason: str  # one short sentence; surfaces in the healing trace


_PROMPT = """You are a routing classifier for a chatbot grounded in the Express.js documentation.

Classify the user's question into exactly one of:
- "clear": Specific question about Express.js (routing, middleware, req/res, error handling, etc.)
- "ambiguous": Likely about Express but too vague to retrieve well (e.g. "how does that work?", "what should I do?")
- "off_topic": Not about Express.js at all (e.g. weather, other frameworks, general programming unrelated to Express)

Respond with ONLY a JSON object on a single line, no markdown fences:
{"intent": "<one of: clear, ambiguous, off_topic>", "reason": "<short explanation under 15 words>"}

Question: """


# Strip ```json ... ``` fences some models stubbornly add even when told not to.
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse(raw: str) -> RoutingDecision:
    text = _FENCE_RE.sub("", raw).strip()
    try:
        obj = json.loads(text)
        intent = obj.get("intent", "clear")
        if intent not in ("clear", "ambiguous", "off_topic"):
            intent = "clear"
        reason = (obj.get("reason") or "").strip()[:160] or "no reason given"
        return RoutingDecision(intent=intent, reason=reason)
    except Exception:
        # Defensive: a malformed classifier output should never break the request.
        return RoutingDecision(intent="clear", reason="classifier returned malformed output; defaulting to clear")


class _OpenAIRouter:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def route(self, query: str) -> RoutingDecision:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "You are a precise classifier. Output only JSON."},
                {"role": "user", "content": _PROMPT + query},
            ],
            temperature=0.0,
            max_tokens=80,
        )
        return _parse(resp.choices[0].message.content or "")


class _GeminiRouter:
    def __init__(self, api_key: str, model: str) -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name=model,
            system_instruction="You are a precise classifier. Output only JSON.",
        )

    def route(self, query: str) -> RoutingDecision:
        resp = self._model.generate_content(
            _PROMPT + query,
            generation_config={"temperature": 0.0, "max_output_tokens": 80},
        )
        return _parse(resp.text or "")


@lru_cache
def get_router():
    s = get_settings()
    if s.llm_provider == "openai":
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY missing but llm_provider=openai")
        return _OpenAIRouter(s.openai_api_key, s.openai_model)
    if not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY missing but llm_provider=gemini")
    return _GeminiRouter(s.gemini_api_key, s.gemini_model)


OFF_TOPIC_REPLY = (
    "I'm specialised on the Express.js documentation, so I can't help with that. "
    "Try asking me about routing, middleware, error handling, request/response objects, "
    "or anything else from the Express docs."
)
