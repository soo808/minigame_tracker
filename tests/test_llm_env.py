"""Tests for local-first + cloud fallback LLM routing."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import backend.llm_env as le


def test_iter_chat_endpoints_cloud_only(monkeypatch):
    monkeypatch.delenv("OPENAI_LOCAL_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_LOCAL_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://cloud/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-x")
    eps = le.iter_chat_endpoints()
    assert len(eps) == 1
    assert eps[0] == ("sk", "http://cloud/v1", "gpt-x")


def test_iter_chat_endpoints_local_then_cloud(monkeypatch):
    monkeypatch.setenv("OPENAI_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("OPENAI_LOCAL_MODEL", "qwen3:14b")
    monkeypatch.delenv("OPENAI_LOCAL_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://cloud/v1")
    eps = le.iter_chat_endpoints()
    assert len(eps) == 2
    assert eps[0][0] == "ollama"
    assert eps[0][1] == "http://127.0.0.1:11434/v1"
    assert eps[0][2] == "qwen3:14b"
    assert eps[1][0] == "sk"


def test_has_llm_for_chat_local_only(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_LOCAL_BASE_URL", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("OPENAI_LOCAL_MODEL", "m")
    assert le.has_llm_for_chat() is True


def test_has_llm_for_chat_false_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_LOCAL_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_LOCAL_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    assert le.has_llm_for_chat() is False


def test_chat_completions_fallback_after_connection_error(monkeypatch):
    monkeypatch.setenv("OPENAI_LOCAL_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("OPENAI_LOCAL_MODEL", "local")
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://cloud.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-fallback")

    ok_resp = MagicMock()
    ok_resp.model = "gpt-fallback"
    ok_resp.choices = [MagicMock(message=MagicMock(content="ok"))]

    client1 = MagicMock()
    client1.chat.completions.create.side_effect = ConnectionError("refused")
    client2 = MagicMock()
    client2.chat.completions.create.return_value = ok_resp

    with patch("openai.OpenAI", side_effect=[client1, client2]):
        out = le.chat_completions_create(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=10,
        )
    assert out is ok_resp
    assert client1.chat.completions.create.called
    assert client2.chat.completions.create.called
