"""Vision LLM that describes a rendered figure region.

Faithfulness guardrail: the model may only report numeric values that are
literally printed in the figure (axis ticks, data labels, legends, titles).
Anything not printed must be reported as "not stated in the figure" - values
are never estimated from where a bar/line/point sits.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from typing import Protocol

from app.config import get_settings

FIGURE_PROMPT = """You are describing a chart or figure from a World Bank report so it can be searched later.

Figure caption: {caption}

Instructions:
- Describe what the figure shows: chart type, panels and their titles, axes and units, series/legend entries, and the qualitative pattern (e.g. rising, falling, higher in X than Y).
- Report a numeric value ONLY if it is literally printed in the figure as a label (axis tick, data label, annotation, title or legend). Quote it exactly as printed.
- If a value is not printed, write "not stated in the figure". Never infer, estimate, or read off a number from the position of a bar, line, or point.
- Do not use outside knowledge. Do not add information that is not visible.
- Be concise: plain prose or a short list, no preamble."""


class VisionDescriber(Protocol):
    def describe(self, png_bytes: bytes, caption: str) -> str: ...


class _OpenAIVision:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def describe(self, png_bytes: bytes, caption: str) -> str:
        b64 = base64.b64encode(png_bytes).decode()
        resp = self._client.chat.completions.create(
            model=self._model,
            temperature=0.0,
            max_tokens=700,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": FIGURE_PROMPT.format(caption=caption)},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
        )
        return resp.choices[0].message.content or ""


class _GeminiVision:
    def __init__(self, api_key: str, model: str) -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._genai = genai
        self._model = genai.GenerativeModel(model)

    def describe(self, png_bytes: bytes, caption: str) -> str:
        resp = self._model.generate_content(
            [FIGURE_PROMPT.format(caption=caption), {"mime_type": "image/png", "data": png_bytes}],
            generation_config={"temperature": 0.0, "max_output_tokens": 700},
        )
        return resp.text or ""


@lru_cache(maxsize=1)
def get_vision_describer() -> VisionDescriber:
    s = get_settings()
    if s.llm_provider == "openai":
        return _OpenAIVision(s.openai_api_key or "", s.openai_model)
    return _GeminiVision(s.gemini_api_key or "", s.gemini_model)
