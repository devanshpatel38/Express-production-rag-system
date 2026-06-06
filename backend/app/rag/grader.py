"""Retrieval grader.

This is the "C" in CRAG (Corrective RAG). After retrieval+rerank gives us our
top candidates, we ask the LLM to score each one: "does this chunk actually
answer the question, or is it tangentially related noise?"

Why this matters: dense retrieval pulls things that *embed similarly* to the
query, not things that *answer* it. A question about error-handling middleware
will pull chunks about other middleware too because they share vocabulary.
The grader is what separates "looks related" from "is actually useful".

Implementation notes:
- Binary score (0.0 = irrelevant, 1.0 = highly relevant) per chunk, plus a short reason.
- We batch all chunks into ONE LLM call to keep latency flat. Quality is slightly
  worse than scoring each chunk individually but the cost saving is huge.
- If grading itself fails (malformed JSON, timeout, etc.) we degrade gracefully:
  return the candidates unchanged with neutral 0.5 scores. The system stays useful.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings
from app.rag.retriever import Candidate


@dataclass
class GradedCandidate:
    candidate: Candidate
    relevance: float   # 0.0 - 1.0
    reason: str        # brief, one line


_PROMPT = """You are grading documentation chunks for relevance to a user's question about Express.js.

Question: {query}

Below are {n} candidate chunks. For each, decide how relevant it is for ANSWERING the question. Score on a 0.0 - 1.0 scale:
- 1.0: directly answers the question
- 0.7: contains key information needed
- 0.4: tangentially related
- 0.0: irrelevant

Chunks:
{chunks}

Respond with ONLY a JSON array of objects, one per chunk, in the same order. No markdown, no preamble:
[{{"id": 1, "score": <float>, "reason": "<under 15 words>"}}, ...]"""


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _format_chunks(candidates: list[Candidate]) -> str:
    blocks = []
    for i, c in enumerate(candidates, start=1):
        # Cap each chunk so the prompt doesn't explode if we have long markdown.
        text = c.text if len(c.text) <= 600 else c.text[:600] + "…"
        blocks.append(f"[#{i}] section: {c.section}\n{text}")
    return "\n\n---\n\n".join(blocks)


def _parse_scores(raw: str, n: int) -> list[tuple[float, str]] | None:
    text = _FENCE_RE.sub("", raw).strip()
    # The model sometimes wraps the array in another object {"results": [...]} -
    # be permissive.
    try:
        parsed = json.loads(text)
    except Exception:
        # Try to salvage an array embedded inside other text.
        m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
        if not m:
            return None
        try:
            parsed = json.loads(m.group(0))
        except Exception:
            return None
    if isinstance(parsed, dict):
        for k in ("results", "scores", "items", "data"):
            if isinstance(parsed.get(k), list):
                parsed = parsed[k]
                break
    if not isinstance(parsed, list) or len(parsed) != n:
        return None
    out: list[tuple[float, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            return None
        try:
            score = float(item.get("score", 0.5))
        except (TypeError, ValueError):
            score = 0.5
        score = max(0.0, min(1.0, score))
        reason = str(item.get("reason") or "")[:160]
        out.append((score, reason))
    return out


class _Grader:
    """LLM-backed grader, provider-agnostic via the generator's client surface."""

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

    def _call(self, prompt: str, max_tokens: int) -> str:
        if self._provider == "openai":
            resp = self._openai.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
        resp = self._gemini.generate_content(
            prompt,
            generation_config={"temperature": 0.0, "max_output_tokens": max_tokens},
        )
        return resp.text or ""

    def grade(self, query: str, candidates: list[Candidate]) -> list[GradedCandidate]:
        if not candidates:
            return []
        prompt = _PROMPT.format(query=query, n=len(candidates), chunks=_format_chunks(candidates))
        # ~40 tokens per chunk for the JSON entry, with a safety floor.
        max_tokens = max(200, 60 * len(candidates))
        try:
            raw = self._call(prompt, max_tokens)
            parsed = _parse_scores(raw, len(candidates))
        except Exception:
            parsed = None

        if parsed is None:
            # Graceful degrade: neutral scores, no filtering effect downstream.
            return [GradedCandidate(c, 0.5, "grading failed; passing through") for c in candidates]
        return [GradedCandidate(c, score, reason) for c, (score, reason) in zip(candidates, parsed)]


@lru_cache
def get_grader() -> _Grader:
    return _Grader()
