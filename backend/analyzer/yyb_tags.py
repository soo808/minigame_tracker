"""YYB 标签统计分析 — 写入 yyb_tag_stats 表。"""
from __future__ import annotations

import json
import logging
from collections import defaultdict

from backend import db

logger = logging.getLogger(__name__)

YYB_CHARTS = ("popular", "bestseller", "new_game")


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [str(t).strip() for t in v if t]
        return [str(v).strip()] if v else []
    except (json.JSONDecodeError, TypeError):
        return [t.strip() for t in raw.split(",") if t.strip()]


def _compute_tag_stats(date: str, chart: str, conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT r.appid, r.rank, g.tags,
               COALESCE(ds.is_new, 0) AS is_new
        FROM rankings r
        JOIN games g ON g.appid = r.appid
        LEFT JOIN daily_status ds
          ON ds.date = r.date AND ds.platform = r.platform
         AND ds.chart = r.chart AND ds.appid = r.appid
        WHERE r.date = ? AND r.platform = 'yyb' AND r.chart = ?
        ORDER BY r.rank
        """,
        (date, chart),
    ).fetchall()

    tag_data: dict[str, dict] = defaultdict(
        lambda: {
            "ranks": [],
            "top10": 0,
            "new_entries": 0,
        }
    )

    for row in rows:
        tags = _parse_tags(row["tags"])
        rank = int(row["rank"])
        is_new = bool(row["is_new"])
        for tag in tags:
            td = tag_data[tag]
            td["ranks"].append(rank)
            if rank <= 10:
                td["top10"] += 1
            if is_new:
                td["new_entries"] += 1

    result = []
    for tag, td in tag_data.items():
        ranks = td["ranks"]
        result.append(
            {
                "tag": tag,
                "game_count": len(ranks),
                "avg_rank": sum(ranks) / len(ranks) if ranks else None,
                "top10_count": td["top10"],
                "new_entries": td["new_entries"],
            }
        )
    return result


def run_yyb_tag_analysis(date: str) -> None:
    logger.info("run_yyb_tag_analysis start date=%s", date)
    with db.get_conn() as conn:
        for chart in YYB_CHARTS:
            stats = _compute_tag_stats(date, chart, conn)
            for s in stats:
                conn.execute(
                    """
                    INSERT INTO yyb_tag_stats
                      (date, chart, tag, game_count, avg_rank, top10_count, new_entries)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date, chart, tag) DO UPDATE SET
                      game_count   = excluded.game_count,
                      avg_rank     = excluded.avg_rank,
                      top10_count  = excluded.top10_count,
                      new_entries  = excluded.new_entries
                    """,
                    (
                        date,
                        chart,
                        s["tag"],
                        s["game_count"],
                        s["avg_rank"],
                        s["top10_count"],
                        s["new_entries"],
                    ),
                )
    logger.info("run_yyb_tag_analysis done date=%s", date)
