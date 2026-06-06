"""LLM generation step.

Both providers get the same prompt - we keep the prompt in one place so the
eval harness sees exactly what production sees.

Two methods on every generator:
- `generate`: synchronous, returns the full string (used by the eval harness and
  the legacy /chat endpoint).
- `stream`: yields tokens for SSE delivery to the browser. The token stream is
  *only* the answer text - sources and the healing trace ride alongside the
  answer over the SSE channel via separate event types, not inside the token
  stream itself.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Iterator, Protocol

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
    def stream(self, query: str, candidates: list[Candidate], history: list[ChatMessage]) -> Iterator[str]: ...


class _OpenAIGenerator:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def _build_messages(self, query: str, candidates: list[Candidate], history: list[ChatMessage]) -> list[dict]:
        context = _format_context(candidates)
        user_msg = f"Context:\n{context}\n\nQuestion: {query}"
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(_format_history(history))
        messages.append({"role": "user", "content": user_msg})
        return messages

    def generate(self, query: str, candidates: list[Candidate], history: list[ChatMessage]) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=self._build_messages(query, candidates, history),
            temperature=0.2,
            max_tokens=600,
        )
        return resp.choices[0].message.content or ""

    def stream(self, query: str, candidates: list[Candidate], history: list[ChatMessage]) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=self._build_messages(query, candidates, history),
            temperature=0.2,
            max_tokens=600,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


class _GeminiGenerator:
    def __init__(self, api_key: str, model: str) -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        # Gemini's "system_instruction" lives on the model not the message list.
        self._model = genai.GenerativeModel(model_name=model, system_instruction=SYSTEM_PROMPT)

    def _chat_with_history(self, history: list[ChatMessage]):
        # Gemini uses {role, parts} - map history accordingly. "assistant" -> "model".
        gem_history = []
        for m in history[-6:]:
            role = "model" if m.role == "assistant" else "user"
            gem_history.append({"role": role, "parts": [m.content]})
        return self._model.start_chat(history=gem_history)

    def generate(self, query: str, candidates: list[Candidate], history: list[ChatMessage]) -> str:
        chat = self._chat_with_history(history)
        context = _format_context(candidates)
        user_msg = f"Context:\n{context}\n\nQuestion: {query}"
        resp = chat.send_message(user_msg, generation_config={"temperature": 0.2, "max_output_tokens": 600})
        return resp.text or ""

    def stream(self, query: str, candidates: list[Candidate], history: list[ChatMessage]) -> Iterator[str]:
        chat = self._chat_with_history(history)
        context = _format_context(candidates)
        user_msg = f"Context:\n{context}\n\nQuestion: {query}"
        resp = chat.send_message(
            user_msg,
            generation_config={"temperature": 0.2, "max_output_tokens": 600},
            stream=True,
        )
        for chunk in resp:
            text = getattr(chunk, "text", None)
            if text:
                yield text


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
