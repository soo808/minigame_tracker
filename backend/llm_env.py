"""OpenAI-compatible Chat Completions: local Qwen/Ollama first, then cloud OPENAI_* / DEEPSEEK_*."""
from __future__ import annotations

import errno
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

_LOCAL_KEY_PLACEHOLDER = "ollama"


def _strip_env(name: str) -> str | None:
    v = os.environ.get(name)
    if v is None:
        return None
    s = v.strip()
    return s if s else None


def local_llm_endpoint() -> tuple[str, str, str] | None:
    """Returns (api_key, base_url, model) when OPENAI_LOCAL_BASE_URL + OPENAI_LOCAL_MODEL are set."""
    base_url = _strip_env("OPENAI_LOCAL_BASE_URL")
    model = _strip_env("OPENAI_LOCAL_MODEL")
    if not base_url or not model:
        return None
    key = _strip_env("OPENAI_LOCAL_API_KEY") or _LOCAL_KEY_PLACEHOLDER
    return (key, base_url, model)


def chat_completion_settings() -> tuple[str | None, str | None, str]:
    """
    Returns (api_key, base_url, model) for cloud / third-party only.
    优先 OPENAI_*；未设置时回退 DEEPSEEK_*（兼容旧 .env）。
    """
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL")
    if api_key is not None:
        api_key = api_key.strip() or None
    if base_url is not None:
        base_url = base_url.strip() or None
    model = (
        os.environ.get("OPENAI_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or "gpt-4o-mini"
    )
    model = (model or "gpt-4o-mini").strip() or "gpt-4o-mini"
    return api_key, base_url, model


def iter_chat_endpoints() -> list[tuple[str, str, str]]:
    """
    Ordered (api_key, base_url, model) for chat.completions.
    Local first when OPENAI_LOCAL_BASE_URL + OPENAI_LOCAL_MODEL are both set; then cloud if key+url present.
    """
    out: list[tuple[str, str, str]] = []
    loc = local_llm_endpoint()
    if loc:
        out.append(loc)
    k, b, m = chat_completion_settings()
    if b and k:
        out.append((k, b, m))
    return out


def has_llm_for_chat() -> bool:
    return bool(iter_chat_endpoints())


def _should_fallback(exc: BaseException) -> bool:
    if isinstance(exc, ImportError):
        return False
    mod = sys.modules.get("openai")
    if mod is not None:
        for name in ("APIConnectionError", "APITimeoutError", "RateLimitError"):
            err_cls = getattr(mod, name, None)
            if err_cls and isinstance(exc, err_cls):
                return True
        api_status = getattr(mod, "APIStatusError", None)
        if api_status and isinstance(exc, api_status):
            code = getattr(exc, "status_code", None)
            if code is not None and (code >= 500 or code == 429 or code in (401, 403)):
                return True
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    if isinstance(exc, OSError):
        err = getattr(exc, "errno", None)
        if err in (
            errno.ECONNREFUSED,
            errno.ENETUNREACH,
            errno.ETIMEDOUT,
            errno.EHOSTUNREACH,
        ):
            return True
    return False


def chat_completions_create(
    *,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
    temperature: float | None = None,
    **extra: Any,
) -> Any:
    """
    Try each endpoint from iter_chat_endpoints() in order; on transport/API errors that
    warrant fallback, retry the next endpoint. Re-raises the last error if none succeed.
    """
    endpoints = iter_chat_endpoints()
    if not endpoints:
        raise RuntimeError("no LLM endpoints configured")

    from openai import OpenAI

    last_exc: BaseException | None = None
    for i, (api_key, base_url, model) in enumerate(endpoints):
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            payload: dict[str, Any] = {"model": model, "messages": messages, **extra}
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            if temperature is not None:
                payload["temperature"] = temperature
            return client.chat.completions.create(**payload)
        except ImportError:
            raise
        except Exception as exc:
            last_exc = exc
            if i < len(endpoints) - 1 and _should_fallback(exc):
                logger.warning(
                    "LLM %s (%s) failed: %s; trying fallback endpoint",
                    base_url,
                    model,
                    exc,
                )
                continue
            raise
    assert last_exc is not None
    raise last_exc
