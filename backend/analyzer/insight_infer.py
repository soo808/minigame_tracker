"""Batch LLM inference for monetization, gameplay tags, and virality (source=ai).

Uses updated_by='llm_batch' for machine-generated rows. Never overwrites
game_monetization with source=manual (UPSERT WHERE).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend import db
from backend.llm_env import chat_completions_create, has_llm_for_chat

logger = logging.getLogger(__name__)

VALID_MONETIZATION = frozenset({"iaa", "iap", "hybrid", "unknown"})
VALID_CHANNEL = frozenset(
    {"wechat_share", "douyin_content", "group_play", "live_mount"}
)

CANONICAL_GAMEPLAY_TAGS: list[tuple[str, str]] = [
    ("loot_box", "开箱类"),
    ("target_like", "靶心类"),
    ("merge", "合成合合"),
    ("ld_like", "LD类"),
    ("hidden_object", "寻物解谜"),
    ("tower_number", "数字爬塔"),
    ("sim", "模拟经营"),
    ("td", "塔防策略"),
    ("idle_card", "放置卡牌"),
    ("action_shooter", "动作射击"),
    ("pvp_arena", "竞技对战"),
    ("survival_slg", "生存SLG"),
]

# Short Chinese / typo labels -> canonical slug (values must exist in CANONICAL_GAMEPLAY_TAGS).
GAMEPLAY_SLUG_ALIASES: dict[str, str] = {
    "塔防": "td",
    "合成": "merge",
    "开箱": "loot_box",
    "靶心": "target_like",
    "寻物": "hidden_object",
    "爬塔": "tower_number",
    "放置": "idle_card",
    "卡牌": "idle_card",
    "射击": "action_shooter",
    "动作": "action_shooter",
    "对战": "pvp_arena",
    "竞技": "pvp_arena",
    "生存": "survival_slg",
    "slg": "survival_slg",
    "ld": "ld_like",
    "ld类": "ld_like",
}


def _norm_gameplay_lookup_key(s: str) -> str:
    s = (s or "").strip().replace("\u3000", " ")
    while "  " in s:
        s = s.replace("  ", " ")
    return s


def _build_name_to_slug() -> dict[str, str]:
    d: dict[str, str] = {}
    for slug, name in CANONICAL_GAMEPLAY_TAGS:
        k = _norm_gameplay_lookup_key(name)
        if k:
            d[k] = slug
    return d


def _resolve_gameplay_slug(
    raw: str,
    slug_to_id: dict[str, int],
    name_to_slug: dict[str, str],
) -> str | None:
    """Map LLM output (English slug, case variant, Chinese label, alias) to a DB slug."""
    t = _norm_gameplay_lookup_key(raw)
    if not t:
        return None
    if t in slug_to_id:
        return t
    low = t.lower()
    if low in slug_to_id:
        return low
    if re.fullmatch(r"[A-Za-z0-9_-]+", t):
        cand = low.replace("-", "_")
        if cand in slug_to_id:
            return cand
    if t in name_to_slug:
        s = name_to_slug[t]
        return s if s in slug_to_id else None
    if t in GAMEPLAY_SLUG_ALIASES:
        s = GAMEPLAY_SLUG_ALIASES[t]
        return s if s in slug_to_id else None
    logger.debug("insight gameplay slug unresolved: %r", t[:80])
    return None


LLM_BATCH_UPDATED_BY = "llm_batch"
DEFAULT_BATCH_SIZE = 12
TOP50_CHARTS_MAX_LIMIT = 200


def db_charts_for_platform(platform: str) -> tuple[str, ...]:
    """DB ``chart`` values for the three API charts (must match main._charts_for_api)."""
    if platform == "wx":
        return ("popularity", "bestseller", "most_played")
    if platform == "yyb":
        return ("popular", "bestseller", "new_game")
    return ("popularity", "bestseller", "fresh_game")


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        parts = s.split("```")
        s = parts[1] if len(parts) > 1 else s
        if s.startswith("json"):
            s = s[4:].lstrip()
    return s.strip()


def _extract_json_array(text: str) -> str | None:
    """First top-level JSON array substring (handles extra prose around it)."""
    start = text.find("[")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


INSIGHT_MAX_OUTPUT_TOKENS = 8192


def _message_content_to_str(content: Any) -> str:
    """Normalize Chat Completions message.content (str or multimodal-style list)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                t = p.get("text")
                if isinstance(t, str):
                    parts.append(t)
                elif isinstance(t, dict):
                    parts.append(str(t.get("value") or t.get("content") or ""))
                else:
                    parts.append(str(p))
            else:
                parts.append(str(p))
        return "".join(parts)
    return str(content)


def _validate_parsed_items(items: Any, games: list[dict]) -> str | None:
    """Return error message if parsed JSON array is unusable; else None."""
    if not isinstance(items, list):
        return "模型输出不是 JSON 数组"
    n_g, n_i = len(games), len(items)
    if n_g > 0 and n_i == 0:
        return (
            "模型返回空 JSON 数组，未包含任何游戏结果；请重试或换用更服从 JSON 输出的模型"
        )
    if n_g == 1 and n_i != 1:
        return f"单游戏推断应返回 1 条 JSON 对象，实际 {n_i} 条，请重试"
    if n_g > 1 and n_i != n_g:
        return f"本批共 {n_g} 款游戏，模型返回 {n_i} 条，数量不一致请重试"
    return None


def ensure_canonical_gameplay_tags(conn) -> None:
    for slug, name in CANONICAL_GAMEPLAY_TAGS:
        conn.execute(
            "INSERT OR IGNORE INTO gameplay_tags (slug, name) VALUES (?, ?)",
            (slug, name),
        )


def _resolve_ranking_date(conn, platform: str, ranking_date: str | None) -> str | None:
    if ranking_date:
        return ranking_date
    row = conn.execute(
        "SELECT MAX(date) AS d FROM rankings WHERE platform = ?",
        (platform,),
    ).fetchone()
    d = row["d"] if row else None
    return str(d) if d else None


def _fetch_candidates(
    conn,
    limit: int,
    only_missing: bool,
    force: bool,
    *,
    platform: str = "wx",
    ranking_date: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Prefer games that appear on ``platform``'s charts for the given calendar day,
    ordered by best (minimum) rank that day. Fallback: all eligible games by appid.
    Returns (candidates, resolved_date_or_none).
    """
    missing_sql = ""
    if only_missing and not force:
        missing_sql = """
          AND (
            m.appid IS NULL
            OR m.monetization_model = 'unknown'
            OR m.source = 'ai'
          )
        """
    base_filter = f"(m.source IS NULL OR m.source != 'manual'){missing_sql}"

    resolved = _resolve_ranking_date(conn, platform, ranking_date)
    if resolved:
        sql_ranked = f"""
            WITH best AS (
              SELECT appid, MIN(rank) AS best_rank
              FROM rankings
              WHERE date = ? AND platform = ?
              GROUP BY appid
            )
            SELECT g.appid, g.name, g.tags, g.description, g.genre_major, g.genre_minor
            FROM games g
            LEFT JOIN game_monetization m ON m.appid = g.appid
            INNER JOIN best b ON b.appid = g.appid
            WHERE {base_filter}
            ORDER BY b.best_rank ASC, g.appid ASC
            LIMIT ?
        """
        rows = conn.execute(sql_ranked, (resolved, platform, limit)).fetchall()
        if rows:
            return [dict(r) for r in rows], resolved

    sql_fallback = f"""
        SELECT g.appid, g.name, g.tags, g.description, g.genre_major, g.genre_minor
        FROM games g
        LEFT JOIN game_monetization m ON m.appid = g.appid
        WHERE {base_filter}
        ORDER BY g.appid ASC
        LIMIT ?
    """
    rows = conn.execute(sql_fallback, (limit,)).fetchall()
    return [dict(r) for r in rows], resolved


def _fetch_top50_union_candidates(
    conn,
    platform: str,
    resolved_date: str,
    *,
    insight_gap_only: bool,
    limit: int,
) -> list[dict[str, Any]]:
    """
    Games appearing in the top 50 on any of the three charts for ``platform`` on
    ``resolved_date``, excluding manual monetization. Optionally keep only games
    missing monetization / unknown model / gameplay tags / virality rows.
    """
    charts = db_charts_for_platform(platform)
    ph = ",".join("?" * len(charts))
    gap_sql = ""
    if insight_gap_only:
        gap_sql = """
          AND (
            m.appid IS NULL
            OR m.monetization_model IS NULL
            OR m.monetization_model = 'unknown'
            OR NOT EXISTS (
              SELECT 1 FROM game_gameplay_tags ggt WHERE ggt.appid = g.appid
            )
            OR NOT EXISTS (
              SELECT 1 FROM virality_assumptions v WHERE v.appid = g.appid
            )
          )
        """
    sql = f"""
        WITH top50 AS (
          SELECT DISTINCT r.appid
          FROM rankings r
          WHERE r.date = ? AND r.platform = ? AND r.chart IN ({ph}) AND r.rank <= 50
        ),
        br AS (
          SELECT r.appid, MIN(r.rank) AS best_rank
          FROM rankings r
          INNER JOIN top50 t ON t.appid = r.appid
          WHERE r.date = ? AND r.platform = ? AND r.chart IN ({ph}) AND r.rank <= 50
          GROUP BY r.appid
        )
        SELECT g.appid, g.name, g.tags, g.description, g.genre_major, g.genre_minor
        FROM games g
        INNER JOIN br ON br.appid = g.appid
        LEFT JOIN game_monetization m ON m.appid = g.appid
        WHERE (m.source IS NULL OR m.source != 'manual')
        {gap_sql}
        ORDER BY br.best_rank ASC, g.appid ASC
        LIMIT ?
    """
    params: list[Any] = [
        resolved_date,
        platform,
        *charts,
        resolved_date,
        platform,
        *charts,
        limit,
    ]
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def _fetch_single_candidate(
    conn, appid: str, only_missing: bool, force: bool
) -> tuple[list[dict[str, Any]], str | None]:
    """Exactly one game; skips if manual monetization or only_missing mismatch."""
    row = conn.execute(
        """
        SELECT g.appid, g.name, g.tags, g.description, g.genre_major, g.genre_minor,
               m.source AS mon_source, m.monetization_model AS mon_model
        FROM games g
        LEFT JOIN game_monetization m ON m.appid = g.appid
        WHERE g.appid = ?
        """,
        (appid.strip(),),
    ).fetchone()
    if not row:
        return [], "找不到该游戏"
    d = dict(row)
    if d.get("mon_source") == "manual":
        return [], "该游戏变现为人工标注，不进行 AI 推断"
    if only_missing and not force:
        ok = (
            d.get("mon_source") is None
            or (d.get("mon_model") or "unknown") == "unknown"
            or d.get("mon_source") == "ai"
        )
        if not ok:
            return [], "已有人工/完整变现记录且未开启强制，跳过推断"
    game = {
        "appid": d["appid"],
        "name": d["name"],
        "tags": d["tags"],
        "description": d["description"],
        "genre_major": d["genre_major"],
        "genre_minor": d["genre_minor"],
    }
    return [game], None


def _ai_insight_batch(games: list[dict]) -> tuple[list[dict[str, Any]], str | None]:
    if not has_llm_for_chat():
        logger.warning("未配置可用 LLM（本地 OPENAI_LOCAL_* 或云端 OPENAI_* / DEEPSEEK_*）")
        return [], "未配置可用 LLM（OPENAI_LOCAL_* 或 OPENAI_* / DEEPSEEK_*）"

    slug_lines = [f"  - {slug}（{name}）" for slug, name in CANONICAL_GAMEPLAY_TAGS]
    slug_block = "\n".join(slug_lines)
    allowed_slugs = [s for s, _ in CANONICAL_GAMEPLAY_TAGS]
    slug_str = ", ".join(allowed_slugs)
    game_lines = []
    for i, g in enumerate(games):
        desc = (g.get("description") or "")[:200]
        game_lines.append(
            f"{i + 1}. appid={g['appid']} 名称={g['name']} 标签={g.get('tags') or '无'} "
            f"大类={g.get('genre_major') or '无'} 小类={g.get('genre_minor') or '无'} 简介片段={desc}"
        )
    prompt = f"""你是中国微信/抖音小游戏竞品分析师。根据下列游戏的名称、标签、品类与简介片段，推断变现与玩法、传播假设。
输出 **仅一个** JSON 数组，不要 markdown。数组每项对应输入同序号游戏，字段：
- index: 整数，从 1 起，与输入序号一致
- monetization_model: 必须是 iaa | iap | hybrid | unknown 之一
- mix_note: 字符串，30 字内，说明推断依据摘要
- evidence_summary: 字符串数组，2~4 条短句，中文
- gameplay_slugs: **字符串数组，元素必须是下列英文 slug 之一**（小写、下划线，与左列一致），**禁止**在数组里写中文。每款游戏选 **1~3 个** 最接近的 slug；若品类模糊也要选出最接近的 1 个，**不要**输出空数组 []。可选 slug 与中文说明如下：
{slug_block}
（同上 slug 单行枚举，便于核对：{slug_str}）
- virality_hypothesis: 字符串，40 字内；若无把握写空字符串 ""
- virality_channels: 字符串数组，元素只能是 wechat_share | douyin_content | group_play | live_mount 之一，可空数组

游戏列表：
{chr(10).join(game_lines)}
"""
    try:
        resp = chat_completions_create(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=INSIGHT_MAX_OUTPUT_TOKENS,
            temperature=0.2,
        )
        used_model = getattr(resp, "model", None) or "unknown"
        choice = resp.choices[0]
        msg_obj = choice.message
        raw = _message_content_to_str(getattr(msg_obj, "content", None)).strip()
        finish = getattr(choice, "finish_reason", None)
        if not raw:
            msg = f"模型返回空正文 (finish_reason={finish}, model={used_model})"
            logger.warning("insight LLM: %s", msg)
            return [], msg

        cleaned = _strip_json_fence(raw)
        try:
            items = json.loads(cleaned)
        except json.JSONDecodeError as e:
            extracted = _extract_json_array(cleaned)
            if extracted:
                try:
                    items = json.loads(extracted)
                except json.JSONDecodeError:
                    return [], f"JSON 解析失败: {e}"
            else:
                hint = "（可能被截断，可减小每批游戏数）" if finish == "length" else ""
                logger.warning(
                    "insight LLM JSON: %s model=%s preview=%r", e, used_model, cleaned[:200]
                )
                return [], f"JSON 解析失败: {e}{hint}"

        if isinstance(items, dict):
            items = [items]

        err = _validate_parsed_items(items, games)
        if err:
            logger.warning(
                "insight LLM item count: %s model=%s preview=%r",
                err,
                used_model,
                cleaned[:240],
            )
            return [], err
        assert isinstance(items, list)
        return items, None
    except ImportError as exc:
        if getattr(exc, "name", None) == "openai" or "openai" in str(exc):
            msg = (
                "未安装 openai 包：请在运行 uvicorn 的同一 Python 环境中执行 "
                "pip install openai 或 pip install -r requirements.txt，然后重启后端"
            )
            logger.error("insight LLM: %s (%s)", msg, exc)
            return [], msg
        logger.exception("insight LLM batch import failed: %s", exc)
        return [], f"依赖导入失败: {exc!s}"
    except Exception as exc:
        logger.exception("insight LLM batch failed: %s", exc)
        return [], f"请求异常: {exc!s}"


def _norm_monetization(m: str) -> str:
    m = (m or "unknown").strip().lower()
    return m if m in VALID_MONETIZATION else "unknown"


def _apply_batch(
    conn, games: list[dict], items: list[dict]
) -> dict[str, int]:
    by_index: dict[int, dict] = {}
    for item in items:
        try:
            idx = int(item.get("index", 0)) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(games):
            by_index[idx] = item

    n_mon = n_gp = n_vir = 0
    slug_to_id: dict[str, int] = {}
    for slug, _ in CANONICAL_GAMEPLAY_TAGS:
        r = conn.execute(
            "SELECT id FROM gameplay_tags WHERE slug = ?", (slug,)
        ).fetchone()
        if r:
            slug_to_id[slug] = int(r["id"])
    name_to_slug = _build_name_to_slug()

    for idx, g in enumerate(games):
        appid = g["appid"]
        item = by_index.get(idx) or {}
        model = _norm_monetization(str(item.get("monetization_model", "unknown")))
        mix_note = (item.get("mix_note") or "")[:120] or None
        ev = item.get("evidence_summary")
        if isinstance(ev, list):
            ev_json = json.dumps([str(x)[:200] for x in ev[:6]], ensure_ascii=False)
        elif isinstance(ev, str) and ev.strip():
            ev_json = json.dumps([ev.strip()[:200]], ensure_ascii=False)
        else:
            ev_json = json.dumps([], ensure_ascii=False)

        cur = conn.execute(
            """
            INSERT INTO game_monetization
              (appid, monetization_model, mix_note, confidence, evidence_summary,
               ad_placement_notes, source, updated_by, updated_at)
            VALUES (?, ?, ?, 0.55, ?, NULL, 'ai', ?, datetime('now'))
            ON CONFLICT(appid) DO UPDATE SET
              monetization_model = excluded.monetization_model,
              mix_note = excluded.mix_note,
              confidence = excluded.confidence,
              evidence_summary = excluded.evidence_summary,
              source = 'ai',
              updated_by = excluded.updated_by,
              updated_at = datetime('now')
            WHERE game_monetization.source != 'manual'
            """,
            (appid, model, mix_note, ev_json, LLM_BATCH_UPDATED_BY),
        )
        if cur.rowcount and cur.rowcount > 0:
            n_mon += 1

        conn.execute(
            """
            DELETE FROM game_gameplay_tags
            WHERE appid = ? AND source = 'ai' AND updated_by = ?
            """,
            (appid, LLM_BATCH_UPDATED_BY),
        )
        slugs = item.get("gameplay_slugs") or []
        if isinstance(slugs, str):
            slugs = [s.strip() for s in re.split(r"[,，\s]+", slugs) if s.strip()]
        resolved_slugs: list[str] = []
        for raw in slugs:
            if len(resolved_slugs) >= 3:
                break
            rs = _resolve_gameplay_slug(str(raw), slug_to_id, name_to_slug)
            if rs and rs not in resolved_slugs:
                resolved_slugs.append(rs)
        role = "primary"
        for s in resolved_slugs:
            cur2 = conn.execute(
                """
                INSERT OR IGNORE INTO game_gameplay_tags
                  (appid, tag_id, role, source, updated_by, updated_at)
                VALUES (?, ?, ?, 'ai', ?, datetime('now'))
                """,
                (appid, slug_to_id[s], role, LLM_BATCH_UPDATED_BY),
            )
            if cur2.rowcount:
                n_gp += 1

        conn.execute(
            """
            DELETE FROM virality_assumptions
            WHERE appid = ? AND source = 'ai' AND updated_by = ?
            """,
            (appid, LLM_BATCH_UPDATED_BY),
        )
        hyp = (item.get("virality_hypothesis") or "").strip()[:200]
        ch = item.get("virality_channels") or []
        if isinstance(ch, str):
            ch = [c.strip() for c in re.split(r"[,，\s]+", ch) if c.strip()]
        ch = [c for c in ch if c in VALID_CHANNEL][:4]
        if hyp or ch:
            conn.execute(
                """
                INSERT INTO virality_assumptions
                  (appid, channels, hypothesis, evidence, confidence, source, updated_by, updated_at)
                VALUES (?, ?, ?, ?, 0.5, 'ai', ?, datetime('now'))
                """,
                (
                    appid,
                    json.dumps(ch, ensure_ascii=False) if ch else None,
                    hyp or "（模型未给出明确假设）",
                    "LLM 批量推断，需业务复核",
                    LLM_BATCH_UPDATED_BY,
                ),
            )
            n_vir += 1

    return {
        "monetization_updated": n_mon,
        "gameplay_links_added": n_gp,
        "virality_inserted": n_vir,
    }


def run_insight_infer_batch(
    *,
    limit: int = 120,
    batch_size: int = DEFAULT_BATCH_SIZE,
    only_missing: bool = True,
    force: bool = False,
    platform: str = "wx",
    ranking_date: str | None = None,
    appid: str | None = None,
    top50_charts: bool = False,
    insight_gap_only: bool = True,
) -> dict[str, Any]:
    """
    Run LLM batches over up to ``limit`` candidate games.
    If ``appid`` is set, only that game is inferred (ignores ranking-based selection).
    If ``top50_charts``, candidates are the union of top-50 across three platform charts.
    Otherwise, when rankings exist for ``platform`` and ``ranking_date`` (or latest),
    candidates are chart games ordered by best rank that day.
    """
    total: dict[str, Any] = {
        "candidates": 0,
        "batches": 0,
        "monetization_updated": 0,
        "gameplay_links_added": 0,
        "virality_inserted": 0,
        "errors": [],
        "platform": platform,
        "ranking_date": None,
        "appid": None,
        "top50_charts": bool(top50_charts),
    }

    with db.get_conn() as conn:
        ensure_canonical_gameplay_tags(conn)
        if appid and appid.strip():
            aid = appid.strip()
            total["appid"] = aid
            candidates, single_err = _fetch_single_candidate(
                conn, aid, only_missing, force
            )
            total["candidates"] = len(candidates)
            if single_err:
                total["errors"].append(single_err)
                return total
        elif top50_charts:
            resolved = _resolve_ranking_date(conn, platform, ranking_date)
            total["ranking_date"] = resolved
            if not resolved:
                total["errors"].append("该平台暂无榜单日期，无法推断前50并集")
                return total
            cap = min(limit, TOP50_CHARTS_MAX_LIMIT)
            gap = insight_gap_only and not force
            candidates = _fetch_top50_union_candidates(
                conn,
                platform,
                resolved,
                insight_gap_only=gap,
                limit=cap,
            )
            total["candidates"] = len(candidates)
        else:
            candidates, resolved = _fetch_candidates(
                conn,
                limit,
                only_missing,
                force,
                platform=platform,
                ranking_date=ranking_date,
            )
            total["ranking_date"] = resolved
            total["candidates"] = len(candidates)

        fail_batches = 0
        first_fail: str | None = None
        for i in range(0, len(candidates), batch_size):
            chunk = candidates[i : i + batch_size]
            items, batch_err = _ai_insight_batch(chunk)
            if not items and chunk:
                fail_batches += 1
                if first_fail is None:
                    first_fail = batch_err or "empty LLM response"
                continue
            stats = _apply_batch(conn, chunk, items)
            total["batches"] += 1
            total["monetization_updated"] += stats["monetization_updated"]
            total["gameplay_links_added"] += stats["gameplay_links_added"]
            total["virality_inserted"] += stats["virality_inserted"]

        if fail_batches:
            total["errors"].append(
                f"共 {fail_batches} 批失败（每批最多 {batch_size} 款）；首错：{first_fail}"
            )

    return total
