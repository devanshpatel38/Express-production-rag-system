"""LLM generation step.

Both providers get the same prompt - we keep the prompt in one place so the
eval harness sees exactly what production sees. Streaming would be a nice
next step but blocks the JSON response shape we want for sources, so it's
left as a future iteration.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.config import get_settings
from app.models.schemas import ChatMessage
from app.rag.retriever import Candidate


SYSTEM_PROMPT = """You are an assistant that answers questions about the Express.js web framework using the provided documentation excerpts.

Rules:
- Answer ONLY from the provided context. If the context does not contain the answer, say so plainly.
- Be concise. Show short code examples when they appear in the context.
- Cite sources inline using the format [#1], [#2] matching the numbered context blocks.
- If the user asks something off-topic (not about Express.js), redirect them politely.
"""


def _format_context(candidates: list[Candidate]) -> str:
    blocks = []
    for i, c in enumerate(candidates, start=1):
        header = f"[#{i}] {c.section} ({c.source_path})"
        blocks.append(f"{header}\n{c.text}")
    return "\n\n---\n\n".join(blocks)


def _format_history(history: list[ChatMessage]) -> list[dict]:
    # We cap history to the last 6 turns to keep prompts small and bills predictable.
    trimmed = history[-6:]
    return [{"role": m.role, "content": m.content} for m in trimmed]


class Generator(Protocol):
    def generate(self, query: str, candidates: list[Candidate], history: list[ChatMessage]) -> str: ...


class _OpenAIGenerator:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def generate(self, query: str, candidates: list[Candidate], history: list[ChatMessage]) -> str:
        context = _format_context(candidates)
        user_msg = f"Context:\n{context}\n\nQuestion: {query}"
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(_format_history(history))
        messages.append({"role": "user", "content": user_msg})

        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.2,
            max_tokens=600,
        )
        return resp.choices[0].message.content or ""


class _GeminiGenerator:
    def __init__(self, api_key: str, model: str) -> None:
        from google import genai
        from google.genai import types as gentypes

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._types = gentypes

    def generate(self, query: str, candidates: list[Candidate], history: list[ChatMessage]) -> str:
        context = _format_context(candidates)
        user_msg = f"Context:\n{context}\n\nQuestion: {query}"

        contents = []
        for m in history[-6:]:
            role = "model" if m.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.content}]})
        contents.append({"role": "user", "parts": [{"text": user_msg}]})

        resp = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=self._types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=600,
            ),
        )
        return resp.text or ""


@lru_cache
def get_generator() -> Generator:
    s = get_settings()
    if s.llm_provider == "openai":
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY missing but llm_provider=openai")
        return _OpenAIGenerator(s.openai_api_key, s.openai_model)
    if not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY missing but llm_provider=gemini")
    return _GeminiGenerator(s.gemini_api_key, s.gemini_model)
