import sys
import types
from unittest.mock import MagicMock

from app.models.schemas import ChatMessage
from app.rag import generator as g
from app.rag.retriever import Candidate


def _cand(**kw):
    base = dict(
        chunk_id="c1", text="Total greenhouse gas emissions: 346", source_path="imac.pdf",
        title="iMac", section="Carbon footprint", score=0.9, page=7, units="kg CO2e",
        chunk_type="table_row", table_title="Product carbon footprint",
    )
    base.update(kw)
    return Candidate(**base)


def test_user_message_includes_page_units_table():
    msg = g.build_user_message("What is the footprint?", [_cand()])
    assert "Page 7" in msg
    assert "Units: kg CO2e" in msg
    assert "Table: Product carbon footprint" in msg
    assert "Question: What is the footprint?" in msg


def test_prose_chunk_omits_units_line():
    msg = g.build_user_message("q", [_cand(units="", table_title="", chunk_type="prose")])
    assert "Page 7" in msg
    assert "Units:" not in msg and "Table:" not in msg


def test_system_prompt_instructions():
    p = g.SYSTEM_PROMPT
    assert "Answer ONLY from the provided context" in p
    assert "say so plainly" in p
    assert "WITH their units" in p
    assert "page number" in p
    assert "Express" not in p


def test_both_providers_share_template(monkeypatch):
    # stub openai
    openai_mod = types.ModuleType("openai")
    openai_mod.OpenAI = MagicMock()
    monkeypatch.setitem(sys.modules, "openai", openai_mod)
    # stub google.generativeai
    genai = types.ModuleType("google.generativeai")
    genai.configure = MagicMock()
    model = MagicMock()
    chat = MagicMock()
    chat.send_message.return_value.text = "ok"
    model.start_chat.return_value = chat
    genai.GenerativeModel = MagicMock(return_value=model)
    google = types.ModuleType("google")
    google.generativeai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    cands = [_cand()]
    hist = [ChatMessage(role="user", content="hi")]
    oa = g._OpenAIGenerator("k", "m")
    msgs = oa._build_messages("Q?", cands, hist)
    gm = g._GeminiGenerator("k", "m")
    assert genai.GenerativeModel.call_args.kwargs["system_instruction"] == msgs[0]["content"] == g.SYSTEM_PROMPT

    assert gm.generate("Q?", cands, hist) == "ok"
    sent = chat.send_message.call_args.args[0]
    assert sent == msgs[-1]["content"] == g.build_user_message("Q?", cands)
