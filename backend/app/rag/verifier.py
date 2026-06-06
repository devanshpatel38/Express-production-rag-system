"""Post-generation faithfulness check.

Even with good retrieval, an LLM can drift: invent function names, contradict
the docs, or paste in training-data knowledge that disagrees with what we retrieved.
This is where most "I asked the bot a simple question and it lied to me" stories
come from.

The verifier asks a *separate* LLM call: "is this answer fully supported by this
context?" Output is a score in [0, 1] and a list of unsupported claims. If the
score is below the threshold we either retry (rewrite query + new retrieval) or,
if we've exhausted attempts, return a graceful fallback so the user knows the
system isn't confident.

This is intentionally a *single* call, not per-claim. Ragas does per-claim and
that's more accurate but ~5x the latency. For a live chat the single call is
the right tradeoff; the eval harness uses Ragas for the careful version.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings
from app.rag.retriever import Candidate


@dataclass
class FaithfulnessResult:
    score: float                       # 0.0 - 1.0
    unsupported_claims: list[str]      # short list of statements not found in context
    reason: str                        # one-line summary


_PROMPT = """You are auditing whether an AI's answer is faithful to the source documentation it was given.

CONTEXT (the only allowed source of facts):
{context}

QUESTION the user asked: {query}

ANSWER the AI produced:
{answer}

Rate how grounded the answer is in the context. Score in [0.0, 1.0]:
- 1.0: every factual claim in the answer is directly supported by the context
- 0.7: minor unsupported phrasing but no factual errors
- 0.4: some claims aren't in the context (potentially hallucinated)
- 0.0: the answer contradicts or ignores the context

Honest, generic statements like "I don't have enough information" should score 1.0 (it's not making unsupported claims).

Respond with ONLY this JSON shape, no markdown:
{{"score": <float>, "unsupported": ["<claim 1>", "<claim 2>"], "reason": "<under 20 words>"}}"""


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _format_context(candidates: list[Candidate]) -> str:
    blocks = []
    for i, c in enumerate(candidates, start=1):
        text = c.text if len(c.text) <= 800 else c.text[:800] + "…"
        blocks.append(f"[#{i}] {c.section}\n{text}")
    return "\n\n---\n\n".join(blocks)


def _parse(raw: str) -> FaithfulnessResult | None:
    text = _FENCE_RE.sub("", raw).strip()
    try:
        obj = json.loads(text)
    except Exception:
        return None
    try:
        score = max(0.0, min(1.0, float(obj.get("score", 0.5))))
    except (TypeError, ValueError):
        return None
    unsupported = obj.get("unsupported") or []
    if not isinstance(unsupported, list):
        unsupported = []
    unsupported = [str(x)[:240] for x in unsupported[:6]]
    reason = str(obj.get("reason") or "")[:200]
    return FaithfulnessResult(score=score, unsupported_claims=unsupported, reason=reason)


class _Verifier:
    def __init__(self) -> None:
        s = get_settings()
        if s.llm_provider == "openai":
            from openai import OpenAI

            if not s.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY missing but llm_provider=openai")
            self._provider = "openai"
            self._openai = OpenAI(api_key=s.openai_api_key)
            self._model = s.openai_model
        else:
            import google.generativeai as genai

            if not s.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY missing but llm_provider=gemini")
            genai.configure(api_key=s.gemini_api_key)
            self._provider = "gemini"
            self._gemini = genai.GenerativeModel(s.gemini_model)

    def _call(self, prompt: str) -> str:
        if self._provider == "openai":
            resp = self._openai.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=240,
            )
            return resp.choices[0].message.content or ""
        resp = self._gemini.generate_content(
            prompt,
            generation_config={"temperature": 0.0, "max_output_tokens": 240},
        )
        return resp.text or ""

    def verify(self, query: str, answer: str, context: list[Candidate]) -> FaithfulnessResult:
        if not answer.strip() or not context:
            return FaithfulnessResult(0.0, [], "empty answer or context")
        prompt = _PROMPT.format(context=_format_context(context), query=query, answer=answer)
        try:
            raw = self._call(prompt)
            parsed = _parse(raw)
        except Exception:
            parsed = None
        if parsed is None:
            # Same pattern as the grader: failing fail-open keeps the user moving.
            return FaithfulnessResult(score=0.7, unsupported_claims=[], reason="verifier output unparseable; treating as acceptable")
        return parsed


@lru_cache
def get_verifier() -> _Verifier:
    return _Verifier()


# Returned when the loop exhausts attempts and the final answer is still ungrounded.
# Keeping the wording deliberately humble - users prefer "I don't know" to a wrong answer.
FALLBACK_ANSWER = (
    "I couldn't find a confident answer in the Express.js docs for that. "
    "Try rephrasing with a more specific term (e.g. a method name like `app.use`, "
    "`req.query`, or `express.static`), or check the official docs directly."
)
