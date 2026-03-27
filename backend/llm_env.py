"""OpenAI-compatible Chat Completions: official OpenAI、第三方 ChatGPT 转发、DeepSeek 等。"""
from __future__ import annotations

import os


def chat_completion_settings() -> tuple[str | None, str | None, str]:
    """
    Returns (api_key, base_url, model).
    优先 OPENAI_*；未设置时回退 DEEPSEEK_*（兼容旧 .env）。
    """
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL")
    model = (
        os.environ.get("OPENAI_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or "gpt-4o-mini"
    )
    return api_key, base_url, model
