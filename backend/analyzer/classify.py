"""Game genre classification: rule-based (~80%) + DeepSeek API batch fallback."""
from __future__ import annotations

import json
import logging
from typing import Optional

from backend import db
from backend.llm_env import chat_completion_settings

logger = logging.getLogger(__name__)

_RULES: list[tuple[str, str, list[str]]] = [
    ("角色扮演", "ARPG", ["角色扮演", "arpg", "rpg", "传奇", "仙侠", "武侠", "奇迹"]),
    ("休闲益智", "消除", ["消除", "合并", "连连看", "祖玛"]),
    ("休闲益智", "益智", ["益智", "解谜", "推理", "数独"]),
    ("休闲益智", "休闲", ["休闲", "超休闲", "小游戏"]),
    ("策略经营", "SLG", ["slg", "策略", "三国", "征战", "战争"]),
    ("策略经营", "经营", ["经营", "模拟", "建造", "塔防", "种田"]),
    ("动作射击", "射击", ["fps", "tps", "枪战", "射击", "吃鸡"]),
    ("动作射击", "动作", ["动作", "格斗", "砍杀", "战斗"]),
    ("体育竞速", "竞速", ["赛车", "竞速", "飞车", "漂移"]),
    ("体育竞速", "体育", ["体育", "足球", "篮球", "棒球", "网球"]),
    ("卡牌棋牌", "卡牌", ["卡牌", "集卡", "ccg", "tcg"]),
    ("卡牌棋牌", "棋牌", ["棋牌", "麻将", "扑克", "斗地主", "象棋"]),
]


def _classify_by_rules(tags: str) -> Optional[tuple[str, str]]:
    if not tags or not tags.strip():
        return None
    tags_lower = tags.lower()
    for major, minor, keywords in _RULES:
        if any(kw.lower() in tags_lower for kw in keywords):
            return (major, minor)
    return None


def _ai_classify_batch(games: list[dict]) -> dict[str, tuple[str, str]]:
    api_key, base_url, model = chat_completion_settings()
    if not api_key or not base_url:
        logger.warning("OPENAI_* / DEEPSEEK_* 未配置完整，跳过 AI 分类")
        return {}

    valid_majors = [
        "角色扮演",
        "休闲益智",
        "策略经营",
        "动作射击",
        "体育竞速",
        "卡牌棋牌",
        "其他",
    ]
    game_list = "\n".join(
        f"{i + 1}. 游戏名：{g['name']}，标签：{g['tags'] or '无'}"
        for i, g in enumerate(games)
    )
    prompt = (
        f"请对以下微信小游戏进行大类分类，大类必须从以下选项中选择：{', '.join(valid_majors)}。\n"
        f"输出格式为 JSON 数组，每项包含 index（从1开始）、major、minor 三个字段，minor 为细分玩法（2~4字）。\n\n"
        f"{game_list}\n\n只输出 JSON，不要其他内容。"
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:].lstrip()
        items = json.loads(raw)
        result: dict[str, tuple[str, str]] = {}
        for item in items:
            idx = int(item.get("index", 0)) - 1
            if 0 <= idx < len(games):
                appid = games[idx]["appid"]
                major = item.get("major", "其他")
                minor = item.get("minor", "")
                if major not in valid_majors:
                    major = "其他"
                result[appid] = (major, str(minor) if minor else "")
        return result
    except Exception as exc:
        logger.error("DeepSeek batch classify failed: %s", exc)
        return {}


def classify_games_batch(force: bool = False) -> dict:
    where = "" if force else "WHERE genre_major IS NULL"
    with db.get_conn() as conn:
        rows = conn.execute(
            f"SELECT appid, name, tags FROM games {where}"
        ).fetchall()

    rule_classified = ai_classified = fallback_other = 0
    ai_pending: list[dict] = []

    for row in rows:
        result = _classify_by_rules(row["tags"] or "")
        if result:
            major, minor = result
            with db.get_conn() as conn:
                conn.execute(
                    "UPDATE games SET genre_major=?, genre_minor=?, updated_at=datetime('now') WHERE appid=?",
                    (major, minor, row["appid"]),
                )
            rule_classified += 1
        else:
            ai_pending.append(
                {"appid": row["appid"], "name": row["name"], "tags": row["tags"]}
            )

    for i in range(0, len(ai_pending), 20):
        batch = ai_pending[i : i + 20]
        ai_results = _ai_classify_batch(batch)
        for game in batch:
            if game["appid"] in ai_results:
                major, minor = ai_results[game["appid"]]
                ai_classified += 1
            else:
                major, minor = "其他", ""
                fallback_other += 1
            with db.get_conn() as conn:
                conn.execute(
                    "UPDATE games SET genre_major=?, genre_minor=?, updated_at=datetime('now') WHERE appid=?",
                    (major, minor, game["appid"]),
                )

    logger.info(
        "classify_batch done: rule=%d ai=%d other=%d",
        rule_classified,
        ai_classified,
        fallback_other,
    )
    return {
        "rule_classified": rule_classified,
        "ai_classified": ai_classified,
        "fallback_other": fallback_other,
    }
