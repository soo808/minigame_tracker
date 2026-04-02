"""ADX-related stats + LLM report helpers (rank/genre features from local DB)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from backend import db
from backend.llm_env import chat_completions_create, has_llm_for_chat

logger = logging.getLogger(__name__)


def _end_date_for_platform(conn, platform: str, end_date: str | None) -> str | None:
    if end_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_date):
        return end_date
    row = conn.execute(
        "SELECT MAX(date) AS d FROM rankings WHERE platform = ?", (platform,)
    ).fetchone()
    return row["d"] if row and row["d"] else None


def build_rank_series(
    conn, *, appid: str, platform: str, end_date: str | None, days: int = 30
) -> dict[str, Any]:
    """Best rank per day across all charts for ``platform`` (within window)."""
    end = _end_date_for_platform(conn, platform, end_date)
    if not end:
        return {"appid": appid, "platform": platform, "end_date": None, "series": []}
    d0 = datetime.strptime(end, "%Y-%m-%d")
    start = d0 - timedelta(days=days - 1)
    start_s = start.strftime("%Y-%m-%d")
    rows = conn.execute(
        """
        SELECT date, MIN(rank) AS best_rank
        FROM rankings
        WHERE platform = ? AND appid = ? AND date >= ? AND date <= ?
        GROUP BY date
        ORDER BY date ASC
        """,
        (platform, appid, start_s, end),
    ).fetchall()
    series = [{"date": r["date"], "best_rank": int(r["best_rank"])} for r in rows]
    return {
        "appid": appid,
        "platform": platform,
        "end_date": end,
        "start_date": start_s,
        "days": days,
        "series": series,
    }


def build_genre_trend(
    conn, *, platform: str, end_date: str | None, days: int = 30
) -> dict[str, Any]:
    """Share of in-chart games by genre_major per day (top-100 union that day)."""
    end = _end_date_for_platform(conn, platform, end_date)
    if not end:
        return {"platform": platform, "end_date": None, "by_date": []}
    d0 = datetime.strptime(end, "%Y-%m-%d")
    start = d0 - timedelta(days=days - 1)
    start_s = start.strftime("%Y-%m-%d")
    from backend.analyzer.insight_infer import db_charts_for_platform, insight_chart_top_n

    charts = db_charts_for_platform(platform)
    top_n = insight_chart_top_n()
    ph = ",".join("?" * len(charts))
    dates = conn.execute(
        f"""
        SELECT DISTINCT date FROM rankings
        WHERE platform = ? AND date >= ? AND date <= ? AND chart IN ({ph})
        ORDER BY date ASC
        """,
        (platform, start_s, end, *charts),
    ).fetchall()
    by_date: list[dict[str, Any]] = []
    for dr in dates:
        ds = dr["date"]
        rows = conn.execute(
            f"""
            SELECT g.genre_major AS gmaj, COUNT(*) AS cnt
            FROM (
              SELECT DISTINCT appid FROM rankings
              WHERE date = ? AND platform = ? AND chart IN ({ph}) AND rank <= ?
            ) u
            INNER JOIN games g ON g.appid = u.appid
            GROUP BY g.genre_major
            """,
            (ds, platform, *charts, top_n),
        ).fetchall()
        total = sum(int(r["cnt"]) for r in rows) or 1
        shares = {
            (r["gmaj"] or "(unset)"): round(int(r["cnt"]) / total, 4) for r in rows
        }
        by_date.append({"date": ds, "genre_shares": shares, "union_size": total})
    return {
        "platform": platform,
        "end_date": end,
        "start_date": start_s,
        "days": days,
        "chart_top_n": top_n,
        "by_date": by_date,
    }


def adx_summary_payload(
    *, appid: str | None, platform: str, end_date: str | None, days: int
) -> dict[str, Any]:
    with db.get_conn() as conn:
        genre = build_genre_trend(conn, platform=platform, end_date=end_date, days=days)
        rank_block = None
        if appid:
            rank_block = build_rank_series(
                conn, appid=appid, platform=platform, end_date=end_date, days=days
            )
        return {
            "platform": platform,
            "days": days,
            "rank_series": rank_block,
            "genre_trend": genre,
        }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    if not t:
        return None
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}\s*$", t)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def run_adx_llm_analyze(
    *,
    appid: str,
    platform: str,
    end_date: str | None,
    days: int,
    persist: bool,
) -> dict[str, Any]:
    if not has_llm_for_chat():
        raise RuntimeError("no LLM configured")
    payload = adx_summary_payload(
        appid=appid, platform=platform, end_date=end_date, days=days
    )
    compact = json.dumps(payload, ensure_ascii=False)[:12000]
    messages = [
        {
            "role": "system",
            "content": (
                "你是游戏行业数据分析师。根据输入 JSON（近30天左右排名序列与品类占比），"
                "输出**单个 JSON 对象**（不要 markdown），字段："
                "interpretation（字符串，中文简述）, trend_summary（字符串）, "
                "predictions（字符串数组，最多3条）, suggestions（字符串数组，最多5条）。"
            ),
        },
        {"role": "user", "content": compact},
    ]
    resp = chat_completions_create(
        messages=messages,
        max_tokens=1024,
        temperature=0.3,
    )
    raw = ""
    try:
        raw = (resp.choices[0].message.content or "").strip()
    except (AttributeError, IndexError):
        logger.warning("unexpected LLM response shape")
    parsed = _extract_json_object(raw)
    out: dict[str, Any] = {
        "ok": True,
        "features": payload,
        "llm_raw": raw[:8000],
        "llm_json": parsed,
    }
    if persist and parsed:
        end = payload.get("rank_series") or {}
        end_d = end.get("end_date") or payload["genre_trend"].get("end_date") or ""
        scope_key = f"{platform}:{appid}"
        with db.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO adx_llm_reports
                  (scope_type, scope_key, report_date, payload_json, model, created_at)
                VALUES ('game_rank_genre', ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(scope_type, scope_key, report_date) DO UPDATE SET
                  payload_json = excluded.payload_json,
                  model = excluded.model,
                  created_at = datetime('now')
                """,
                (
                    scope_key,
                    str(end_d),
                    json.dumps(parsed, ensure_ascii=False),
                    getattr(resp, "model", None) or "",
                ),
            )
        out["persisted"] = True
    else:
        out["persisted"] = False
    return out


# ---------------------------------------------------------------------------
# Platform-wide trend analysis
# ---------------------------------------------------------------------------


def build_daily_ranking_digest(
    conn,
    *,
    platform: str,
    date: str,
) -> dict[str, Any]:
    """Build a concrete daily ranking digest for a given date.

    Queries rankings, daily_status, and games tables to produce
    specific data about what changed on *date* compared to previous days.
    """
    from backend.analyzer.insight_infer import db_charts_for_platform

    charts = db_charts_for_platform(platform)
    ph = ",".join("?" * len(charts))

    yesterday = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    last_week = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=7)).strftime(
        "%Y-%m-%d"
    )

    # 1. Today's top 20 per chart (best rank across charts) with yesterday's rank
    top_rows = conn.execute(
        f"""
        SELECT r.appid, g.name, g.genre_major,
               MIN(r.rank) AS best_rank
        FROM rankings r
        JOIN games g ON g.appid = r.appid
        WHERE r.platform = ? AND r.chart IN ({ph}) AND r.date = ?
        GROUP BY r.appid
        ORDER BY best_rank ASC
        LIMIT 20
        """,
        (platform, *charts, date),
    ).fetchall()

    today_top20 = []
    for row in top_rows:
        prev = conn.execute(
            f"""
            SELECT MIN(rank) AS best_rank FROM rankings
            WHERE appid = ? AND platform = ? AND chart IN ({ph}) AND date = ?
            """,
            (row["appid"], platform, *charts, yesterday),
        ).fetchone()
        prev_rank = int(prev["best_rank"]) if prev and prev["best_rank"] else None
        best = int(row["best_rank"])
        today_top20.append({
            "rank": best,
            "name": row["name"],
            "genre": row["genre_major"] or "未分类",
            "prev_rank": prev_rank,
            "delta": (prev_rank - best) if prev_rank else None,
        })

    # 2. New entries (from daily_status)
    new_rows = conn.execute(
        """
        SELECT ds.appid, g.name, g.genre_major,
               MIN(r.rank) AS best_rank
        FROM daily_status ds
        JOIN games g ON g.appid = ds.appid
        LEFT JOIN rankings r ON r.appid = ds.appid AND r.date = ds.date AND r.platform = ds.platform
        WHERE ds.platform = ? AND ds.date = ? AND ds.is_new = 1
        GROUP BY ds.appid
        ORDER BY best_rank ASC
        """,
        (platform, date),
    ).fetchall()
    new_entries = [
        {"name": r["name"], "rank": int(r["best_rank"]) if r["best_rank"] else None,
         "genre": r["genre_major"] or "未分类"}
        for r in new_rows
    ]

    # 3. Dropped (from daily_status)
    drop_rows = conn.execute(
        """
        SELECT ds.appid, g.name, g.genre_major
        FROM daily_status ds
        JOIN games g ON g.appid = ds.appid
        WHERE ds.platform = ? AND ds.date = ? AND ds.is_dropped = 1
        """,
        (platform, date),
    ).fetchall()
    dropped = [
        {"name": r["name"], "genre": r["genre_major"] or "未分类"}
        for r in drop_rows
    ]

    # 4. Biggest risers and fallers (from daily_status rank_delta)
    riser_rows = conn.execute(
        """
        SELECT ds.appid, g.name, g.genre_major, ds.rank_delta,
               MIN(r.rank) AS today_rank
        FROM daily_status ds
        JOIN games g ON g.appid = ds.appid
        LEFT JOIN rankings r ON r.appid = ds.appid AND r.date = ds.date AND r.platform = ds.platform
        WHERE ds.platform = ? AND ds.date = ? AND ds.rank_delta IS NOT NULL AND ds.rank_delta < 0
        GROUP BY ds.appid
        ORDER BY ds.rank_delta ASC
        LIMIT 10
        """,
        (platform, date),
    ).fetchall()
    biggest_risers = [
        {"name": r["name"], "genre": r["genre_major"] or "未分类",
         "rank_delta": int(r["rank_delta"]),
         "today_rank": int(r["today_rank"]) if r["today_rank"] else None}
        for r in riser_rows
    ]

    faller_rows = conn.execute(
        """
        SELECT ds.appid, g.name, g.genre_major, ds.rank_delta,
               MIN(r.rank) AS today_rank
        FROM daily_status ds
        JOIN games g ON g.appid = ds.appid
        LEFT JOIN rankings r ON r.appid = ds.appid AND r.date = ds.date AND r.platform = ds.platform
        WHERE ds.platform = ? AND ds.date = ? AND ds.rank_delta IS NOT NULL AND ds.rank_delta > 0
        GROUP BY ds.appid
        ORDER BY ds.rank_delta DESC
        LIMIT 10
        """,
        (platform, date),
    ).fetchall()
    biggest_fallers = [
        {"name": r["name"], "genre": r["genre_major"] or "未分类",
         "rank_delta": int(r["rank_delta"]),
         "today_rank": int(r["today_rank"]) if r["today_rank"] else None}
        for r in faller_rows
    ]

    # 5. Genre summary for today
    genre_rows = conn.execute(
        f"""
        SELECT COALESCE(g.genre_major, '未分类') AS genre,
               COUNT(DISTINCT r.appid) AS cnt
        FROM rankings r JOIN games g ON g.appid = r.appid
        WHERE r.platform = ? AND r.chart IN ({ph}) AND r.date = ?
        GROUP BY genre ORDER BY cnt DESC
        """,
        (platform, *charts, date),
    ).fetchall()
    genre_summary = {r["genre"]: int(r["cnt"]) for r in genre_rows}

    # 6. vs yesterday genre comparison
    genre_yest_rows = conn.execute(
        f"""
        SELECT COALESCE(g.genre_major, '未分类') AS genre,
               COUNT(DISTINCT r.appid) AS cnt
        FROM rankings r JOIN games g ON g.appid = r.appid
        WHERE r.platform = ? AND r.chart IN ({ph}) AND r.date = ?
        GROUP BY genre ORDER BY cnt DESC
        """,
        (platform, *charts, yesterday),
    ).fetchall()
    genre_yest = {r["genre"]: int(r["cnt"]) for r in genre_yest_rows}

    genre_shifts = []
    all_genres = set(genre_summary.keys()) | set(genre_yest.keys())
    for g in sorted(all_genres):
        t = genre_summary.get(g, 0)
        y = genre_yest.get(g, 0)
        if t != y:
            genre_shifts.append({"genre": g, "today": t, "yesterday": y, "delta": t - y})
    genre_shifts.sort(key=lambda x: -abs(x["delta"]))

    # 7. vs last week: new entry counts and volatility
    new_count_week_ago = conn.execute(
        "SELECT COUNT(*) AS cnt FROM daily_status WHERE platform = ? AND date = ? AND is_new = 1",
        (platform, last_week),
    ).fetchone()
    vol_today = conn.execute(
        "SELECT AVG(ABS(rank_delta)) AS v FROM daily_status WHERE platform = ? AND date = ? AND rank_delta IS NOT NULL",
        (platform, date),
    ).fetchone()
    vol_week = conn.execute(
        "SELECT AVG(ABS(rank_delta)) AS v FROM daily_status WHERE platform = ? AND date = ? AND rank_delta IS NOT NULL",
        (platform, last_week),
    ).fetchone()

    return {
        "date": date,
        "platform": platform,
        "today_top20": today_top20,
        "new_entries": new_entries,
        "new_count": len(new_entries),
        "dropped": dropped,
        "dropped_count": len(dropped),
        "biggest_risers": biggest_risers,
        "biggest_fallers": biggest_fallers,
        "genre_summary": genre_summary,
        "vs_yesterday": {
            "genre_shifts": genre_shifts[:10],
        },
        "vs_last_week": {
            "new_count_today": len(new_entries),
            "new_count_week_ago": int(new_count_week_ago["cnt"]) if new_count_week_ago else 0,
            "volatility_today": round(float(vol_today["v"]), 2) if vol_today and vol_today["v"] else 0.0,
            "volatility_week_ago": round(float(vol_week["v"]), 2) if vol_week and vol_week["v"] else 0.0,
        },
    }


def build_platform_trend_features(
    conn,
    *,
    platform: str,
    end_date: str | None,
    days: int = 30,
) -> dict[str, Any]:
    """Aggregate platform-wide trend features over a time window."""
    end = _end_date_for_platform(conn, platform, end_date)
    if not end:
        return {"platform": platform, "end_date": None, "features": {}}

    d0 = datetime.strptime(end, "%Y-%m-%d")
    start = d0 - timedelta(days=days - 1)
    start_s = start.strftime("%Y-%m-%d")
    mid_s = (d0 - timedelta(days=days // 2)).strftime("%Y-%m-%d")

    from backend.analyzer.insight_infer import db_charts_for_platform

    charts = db_charts_for_platform(platform)
    ph = ",".join("?" * len(charts))

    # 1. Category distribution: first half vs second half
    def _genre_dist(date_lo: str, date_hi: str) -> dict[str, int]:
        rows = conn.execute(
            f"""
            SELECT COALESCE(g.genre_major, '未分类') AS genre,
                   COUNT(DISTINCT r.appid) AS cnt
            FROM rankings r JOIN games g ON g.appid = r.appid
            WHERE r.platform = ? AND r.chart IN ({ph})
              AND r.date >= ? AND r.date <= ?
            GROUP BY genre ORDER BY cnt DESC
            """,
            (platform, *charts, date_lo, date_hi),
        ).fetchall()
        return {r["genre"]: int(r["cnt"]) for r in rows}

    genre_first_half = _genre_dist(start_s, mid_s)
    genre_second_half = _genre_dist(mid_s, end)

    # 2. New entry velocity
    new_entries = conn.execute(
        f"""
        SELECT COUNT(*) AS cnt FROM (
          SELECT r.appid, MIN(r.date) AS first_date
          FROM rankings r
          WHERE r.platform = ? AND r.chart IN ({ph})
          GROUP BY r.appid
          HAVING first_date >= ? AND first_date <= ?
        )
        """,
        (platform, *charts, start_s, end),
    ).fetchone()
    new_entry_count = int(new_entries["cnt"]) if new_entries else 0

    # 3. Rising / falling categories
    all_genres = set(genre_first_half.keys()) | set(genre_second_half.keys())
    rising: list[dict] = []
    falling: list[dict] = []
    for g in all_genres:
        c1 = genre_first_half.get(g, 0)
        c2 = genre_second_half.get(g, 0)
        if c2 > c1:
            rising.append({"genre": g, "from": c1, "to": c2, "delta": c2 - c1})
        elif c2 < c1:
            falling.append({"genre": g, "from": c1, "to": c2, "delta": c1 - c2})
    rising.sort(key=lambda x: -x["delta"])
    falling.sort(key=lambda x: -x["delta"])

    # 4. Rank volatility
    vol_row = conn.execute(
        """
        SELECT AVG(ABS(rank_delta)) AS avg_vol, COUNT(*) AS cnt
        FROM daily_status
        WHERE platform = ? AND date >= ? AND date <= ? AND rank_delta IS NOT NULL
        """,
        (platform, start_s, end),
    ).fetchone()
    avg_volatility = (
        round(float(vol_row["avg_vol"]), 2) if vol_row and vol_row["avg_vol"] else 0.0
    )

    # 5. Top movers (biggest rank climbers recently)
    movers_rows = conn.execute(
        """
        SELECT ds.appid, g.name, g.genre_major, ds.rank_delta
        FROM daily_status ds
        JOIN games g ON g.appid = ds.appid
        WHERE ds.platform = ? AND ds.date = ? AND ds.rank_delta IS NOT NULL
        ORDER BY ds.rank_delta ASC
        LIMIT 10
        """,
        (platform, end),
    ).fetchall()
    top_movers = [
        {
            "appid": r["appid"],
            "name": r["name"],
            "genre": r["genre_major"],
            "rank_delta": int(r["rank_delta"]),
        }
        for r in movers_rows
    ]

    # 6. Genre trend series (reuse existing)
    genre_trend = build_genre_trend(conn, platform=platform, end_date=end, days=days)

    return {
        "platform": platform,
        "end_date": end,
        "start_date": start_s,
        "days": days,
        "genre_first_half": genre_first_half,
        "genre_second_half": genre_second_half,
        "rising_categories": rising[:10],
        "falling_categories": falling[:10],
        "new_entry_count": new_entry_count,
        "avg_rank_volatility": avg_volatility,
        "top_movers": top_movers,
        "genre_trend_series": genre_trend.get("by_date", []),
    }


def run_platform_trend_report(
    *,
    platform: str,
    end_date: str | None = None,
    days: int = 7,
    persist: bool = True,
) -> dict[str, Any]:
    """Generate platform-wide trend report via local LLM (Qwen3).

    Uses both weekly trend features AND a concrete daily ranking digest
    so the LLM can reference specific games, ranks, and changes.
    """
    if not has_llm_for_chat():
        raise RuntimeError("no LLM configured")

    with db.get_conn() as conn:
        features = build_platform_trend_features(
            conn, platform=platform, end_date=end_date, days=days
        )

        report_date = features.get("end_date") or end_date
        if not report_date:
            return {"ok": False, "error": "no ranking data for platform", "features": features}

        daily_digest = build_daily_ranking_digest(
            conn, platform=platform, date=report_date
        )

    # Build a compact data payload with both digest and features
    compact_data: dict[str, Any] = {
        "report_date": report_date,
        "platform": platform,
        # Daily specifics
        "today_top20": daily_digest["today_top20"],
        "new_entries": daily_digest["new_entries"],
        "new_count": daily_digest["new_count"],
        "dropped": daily_digest["dropped"],
        "dropped_count": daily_digest["dropped_count"],
        "biggest_risers": daily_digest["biggest_risers"],
        "biggest_fallers": daily_digest["biggest_fallers"],
        "genre_summary_today": daily_digest["genre_summary"],
        "vs_yesterday": daily_digest["vs_yesterday"],
        "vs_last_week": daily_digest["vs_last_week"],
        # Weekly trends
        "rising_categories_7d": features.get("rising_categories", [])[:5],
        "falling_categories_7d": features.get("falling_categories", [])[:5],
        "avg_rank_volatility_7d": features.get("avg_rank_volatility"),
        "new_entry_count_7d": features.get("new_entry_count"),
        "top_movers_7d": features.get("top_movers", [])[:5],
    }

    compact = json.dumps(compact_data, ensure_ascii=False)[:12000]

    platform_name = {"wx": "微信小游戏", "dy": "抖音小游戏", "yyb": "应用宝小游戏"}.get(
        platform, platform
    )

    messages = [
        {
            "role": "system",
            "content": (
                f"你是资深{platform_name}行业分析师。下面是 {report_date} 当天的排行榜数据"
                "（包含 TOP20 排名及变化、新上榜/跌出游戏、排名升降最大的游戏、"
                "品类分布对比昨天和上周的变化）。\n\n"
                "**要求**：\n"
                "1. 必须引用具体游戏名和排名数据，不能泛泛而谈\n"
                "2. 对比昨天和上周的变化，指出趋势方向\n"
                "3. 解释品类变化的可能原因\n\n"
                "输出**单个 JSON 对象**（不要 markdown fence），字段：\n"
                "- daily_highlights（字符串数组，当天最值得注意的 3-5 条变化，每条必须包含具体游戏名+排名数据）\n"
                "- comparison（字符串，100字内总结与昨天/上周的对比）\n"
                "- platform_summary（字符串，100字内平台趋势总结）\n"
                "- rising_genres（字符串数组，上升品类+代表游戏，最多3条）\n"
                "- falling_genres（字符串数组，下降品类，最多3条）\n"
                "- hot_games（字符串数组，值得关注的游戏+原因+排名数据，最多5条）\n"
                "- predictions（字符串数组，基于数据的趋势预测，最多3条）\n"
                "- recommendations（字符串数组，给投放/开发团队的建议，最多3条）\n"
                "- risk_signals（字符串数组，风险信号，最多2条）"
            ),
        },
        {"role": "user", "content": compact},
    ]

    resp = chat_completions_create(messages=messages, max_tokens=2048, temperature=0.3)
    raw = ""
    try:
        raw = (resp.choices[0].message.content or "").strip()
    except (AttributeError, IndexError):
        logger.warning("unexpected LLM response shape for platform trend")

    parsed = _extract_json_object(raw)

    out: dict[str, Any] = {
        "ok": True,
        "features": features,
        "daily_digest": daily_digest,
        "llm_raw": raw[:8000],
        "llm_json": parsed,
    }

    if persist and parsed:
        scope_key = platform
        with db.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO adx_llm_reports
                  (scope_type, scope_key, report_date, payload_json, model, created_at)
                VALUES ('platform_trend', ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(scope_type, scope_key, report_date) DO UPDATE SET
                  payload_json = excluded.payload_json,
                  model = excluded.model,
                  created_at = datetime('now')
                """,
                (
                    scope_key,
                    str(report_date),
                    json.dumps(parsed, ensure_ascii=False),
                    getattr(resp, "model", None) or "",
                ),
            )
        out["persisted"] = True
    else:
        out["persisted"] = False

    return out
