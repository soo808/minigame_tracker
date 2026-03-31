"""Scrape 应用宝 detail pages for game description; DeepSeek AI fallback."""
from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Optional

import httpx

from backend import db
from backend.llm_env import chat_completions_create, has_llm_for_chat

logger = logging.getLogger(__name__)

_DETAIL_URL = "https://sj.qq.com/appdetail/{appid}"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://sj.qq.com/",
}

_MAX_DESC_LEN = 500


def _parse_description(html: str) -> Optional[str]:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        page_props = data.get("props", {}).get("pageProps", {})
        app_detail = page_props.get("appDetail", {})
        desc = (
            app_detail.get("introText")
            or app_detail.get("appDesc")
            or app_detail.get("intro")
            or page_props.get("detail", {}).get("appDesc")
        )
        if not desc:
            return None
        s = str(desc).strip()
        return s[:_MAX_DESC_LEN] if s else None
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def fetch_detail(appid: str) -> Optional[str]:
    url = _DETAIL_URL.format(appid=appid)
    try:
        with httpx.Client(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                logger.warning("detail HTTP %s for appid=%s", resp.status_code, appid)
                return None
            return _parse_description(resp.text)
    except Exception as exc:
        logger.error("detail fetch error appid=%s: %s", appid, exc)
        return None


def _ai_generate_description(name: str, tags: Optional[str]) -> Optional[str]:
    if not has_llm_for_chat():
        logger.warning("未配置可用 LLM，跳过 AI 描述兜底")
        return None
    try:
        resp = chat_completions_create(
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"用50字以内简述微信小游戏「{name}」的玩法特色，"
                        f"标签：{tags or '无'}。只输出描述文字，不要加引号。"
                    ),
                }
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        return text[:_MAX_DESC_LEN] if text else None
    except Exception as exc:
        logger.error("DeepSeek description fallback failed name=%s: %s", name, exc)
        return None


def collect_detail_batch(ai_fallback: bool = True) -> dict:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT appid, name, tags FROM games WHERE description IS NULL"
        ).fetchall()

    updated = skipped = failed = 0
    for row in rows:
        appid, name, tags = row["appid"], row["name"], row["tags"]
        desc = fetch_detail(appid)
        if not desc and ai_fallback:
            desc = _ai_generate_description(name, tags)
        if desc:
            with db.get_conn() as conn:
                conn.execute(
                    "UPDATE games SET description = ?, updated_at = datetime('now') WHERE appid = ?",
                    (desc, appid),
                )
            updated += 1
        else:
            failed += 1
        time.sleep(random.uniform(1.0, 2.0))

    logger.info(
        "detail_batch done: updated=%d skipped=%d failed=%d",
        updated,
        skipped,
        failed,
    )
    return {"updated": updated, "skipped": skipped, "failed": failed}
