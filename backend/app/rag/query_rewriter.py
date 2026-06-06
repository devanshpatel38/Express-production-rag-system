"""Query rewriting.

Two distinct rewrite modes; they solve different problems:

1. **HyDE (Hypothetical Document Embeddings)**: short, vague queries don't embed
   well because the embedding model was trained on full sentences, not three-word
   keyword soups. HyDE asks the LLM to *imagine the answer* and we embed that
   imagined answer instead of the query. Answer-to-answer similarity > query-to-answer
   similarity, empirically.

   Use this pre-retrieval when the router says "ambiguous" or the user
   opts in via the API.

2. **Healing rewrite**: triggered inside the loop after retrieval graded poorly.
   The retrieval failed because the query and the docs use different words; the
   rewriter rephrases using terminology more likely to match the docs (function
   names, method signatures, Express-specific jargon).

   Use this *after* a bad retrieval attempt, when we know which terms didn't land.

Both calls are cheap (small max_tokens) and gated behind feature flags so they
never silently double your LLM bill.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.config import get_settings


_HYDE_PROMPT = """You are an Express.js documentation expert. Given the user's question, write a short, factual passage (3-5 sentences) that would directly answer it, in the style of the official Express.js docs. Use exact API names (app.get, req.params, express.static, etc.) where relevant. Do NOT add disclaimers or qualifications. Just write the passage.

Question: {query}

Passage:"""


_REWRITE_PROMPT = """You are improving a search query for an Express.js documentation search engine. The previous retrieval returned poor results.

Original question: {query}

Rewrite this question so it uses terminology that is more likely to appear in technical documentation. Specifically:
- Replace colloquial phrases with API or method names where possible (e.g. "how do I get URL params" -> "req.params route parameters")
- Be specific about what you're looking for
- Keep it concise (one sentence)

Respond with ONLY the rewritten query, no quotes, no explanation, no preamble."""


class Rewriter(Protocol):
    def hyde(self, query: str) -> str: ...
    def rewrite(self, query: str) -> str: ...


class _OpenAIRewriter:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def _chat(self, prompt: str, max_tokens: int) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def hyde(self, query: str) -> str:
        return self._chat(_HYDE_PROMPT.format(query=query), 220)

    def rewrite(self, query: str) -> str:
        return self._chat(_REWRITE_PROMPT.format(query=query), 80)


class _GeminiRewriter:
    def __init__(self, api_key: str, model: str) -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name=model)

    def _gen(self, prompt: str, max_tokens: int) -> str:
        resp = self._model.generate_content(
            prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": max_tokens},
        )
        return (resp.text or "").strip()

    def hyde(self, query: str) -> str:
        return self._gen(_HYDE_PROMPT.format(query=query), 220)

    def rewrite(self, query: str) -> str:
        return self._gen(_REWRITE_PROMPT.format(query=query), 80)


@lru_cache
def get_rewriter() -> Rewriter:
    s = get_settings()
    if s.llm_provider == "openai":
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY missing but llm_provider=openai")
        return _OpenAIRewriter(s.openai_api_key, s.openai_model)
    if not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY missing but llm_provider=gemini")
    return _GeminiRewriter(s.gemini_api_key, s.gemini_model)
