"""QA pipeline: hot-topic Text2SQL skip, reasoning fallback, timeouts."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import backend.llm_env as le


def test_http_timeout_seconds_default(monkeypatch):
    monkeypatch.delenv("LLM_HTTP_TIMEOUT", raising=False)
    monkeypatch.delenv("OPENAI_HTTP_TIMEOUT", raising=False)
    assert le.http_timeout_seconds() == 180.0


def test_http_timeout_seconds_env(monkeypatch):
    monkeypatch.setenv("LLM_HTTP_TIMEOUT", "90")
    assert le.http_timeout_seconds() == 90.0


def test_http_timeout_seconds_clamped(monkeypatch):
    monkeypatch.setenv("LLM_HTTP_TIMEOUT", "10")
    assert le.http_timeout_seconds() == 30.0


def test_extract_completion_text_content():
    msg = MagicMock()
    msg.content = "hello"
    msg.reasoning = None
    msg.model_extra = {}
    resp = MagicMock(choices=[MagicMock(message=msg)])
    assert le.extract_completion_text(resp) == "hello"


def test_extract_completion_text_reasoning_fallback():
    msg = MagicMock()
    msg.content = ""
    msg.reasoning = "step by step … final: done"
    msg.model_extra = {}
    resp = MagicMock(choices=[MagicMock(message=msg)])
    assert le.extract_completion_text(resp) == "step by step … final: done"


def test_extract_completion_text_model_extra_reasoning():
    msg = MagicMock()
    msg.content = None
    msg.reasoning = None
    msg.model_extra = {"reasoning": "from extra"}
    resp = MagicMock(choices=[MagicMock(message=msg)])
    assert le.extract_completion_text(resp) == "from extra"


def test_hot_question_skips_text2sql(monkeypatch):
    calls: list[int] = []

    def track(*_a, **_k):
        calls.append(1)
        return {"sql": None, "rows": [], "error": None}

    monkeypatch.setattr("backend.qa.run_text2sql", track)
    monkeypatch.setattr("backend.qa.search_kb", lambda *_a, **_k: [])
    monkeypatch.setattr("backend.qa.fetch_hot_events", lambda: [])

    def ans(question, sql_result, kb_chunks, hot_events):
        return {
            "answer": "ok",
            "sql": sql_result.get("sql"),
            "sources": [],
        }

    monkeypatch.setattr("backend.qa.answer_question", ans)
    from backend.qa import qa_pipeline

    out = qa_pipeline("今日外部热点", platform="wx")
    assert calls == []
    assert out["answer"] == "ok"


def test_hot_plus_rank_intent_runs_text2sql(monkeypatch):
    calls: list[int] = []

    def track(*_a, **_k):
        calls.append(1)
        return {"sql": "SELECT 1", "rows": [{"a": 1}], "error": None}

    monkeypatch.setattr("backend.qa.run_text2sql", track)
    monkeypatch.setattr("backend.qa.search_kb", lambda *_a, **_k: [])
    monkeypatch.setattr("backend.qa.fetch_hot_events", lambda: [])

    def ans(question, sql_result, kb_chunks, hot_events):
        return {
            "answer": "y",
            "sql": sql_result.get("sql"),
            "sources": [],
        }

    monkeypatch.setattr("backend.qa.answer_question", ans)
    from backend.qa import qa_pipeline

    qa_pipeline("热点里哪些游戏还在榜上", platform="wx")
    assert len(calls) == 1


def test_openai_instantiated_with_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("OPENAI_LOCAL_MODEL", "qwen")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    instances: list[dict] = []

    class CaptureOpenAI:
        def __init__(self, **kwargs):
            instances.append(kwargs)
            self.chat = MagicMock()
            self.chat.completions.create.side_effect = RuntimeError("no network")

    with patch("openai.OpenAI", CaptureOpenAI):
        with pytest.raises(RuntimeError, match="no network"):
            le.chat_completions_create(messages=[{"role": "user", "content": "x"}])
    assert instances
    assert instances[0].get("timeout") == le.http_timeout_seconds()
