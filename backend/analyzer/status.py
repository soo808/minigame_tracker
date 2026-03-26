"""Batch gate + daily_status (new / dropped / rank_delta vs yesterday)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from backend import db

logger = logging.getLogger(__name__)

REQUIRED_CHARTS = {
    ("wx", "popularity"),
    ("wx", "bestseller"),
    ("wx", "most_played"),
    ("dy", "popularity"),
    ("dy", "bestseller"),
    ("dy", "fresh_game"),
}

YYB_REQUIRED_CHARTS = {
    ("yyb", "popular"),
    ("yyb", "bestseller"),
    ("yyb", "new_game"),
}


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _fmt_date(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def maybe_run_analysis_after_snapshot(date: str) -> None:
    with db.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT platform, chart FROM snapshots
            WHERE date = ? AND status IN ('ok', 'partial')
            """,
            (date,),
        ).fetchall()
    received = {(r["platform"], r["chart"]) for r in rows}

    if REQUIRED_CHARTS <= received:
        run_analysis(date)

    if YYB_REQUIRED_CHARTS <= received:
        run_analysis(date, YYB_REQUIRED_CHARTS)
        _run_yyb_tag_analysis(date)


def _run_yyb_tag_analysis(date: str) -> None:
    try:
        from backend.analyzer.yyb_tags import run_yyb_tag_analysis

        run_yyb_tag_analysis(date)
    except Exception:
        logger.exception("yyb_tags analysis failed for date=%s", date)


def run_analysis(date: str, charts: set | None = None) -> None:
    """Recompute daily_status for `date` for all REQUIRED charts (or explicit subset)."""
    target = REQUIRED_CHARTS if charts is None else charts
    d0 = _parse_date(date)
    yday = _fmt_date(d0 - timedelta(days=1))
    week_start = _fmt_date(d0 - timedelta(days=7))

    with db.get_conn() as conn:
        for platform, chart in target:
            conn.execute(
                "DELETE FROM daily_status WHERE date = ? AND platform = ? AND chart = ?",
                (date, platform, chart),
            )

        for platform, chart in target:
            cur_t = conn.execute(
                """
                SELECT appid, rank FROM rankings
                WHERE date = ? AND platform = ? AND chart = ?
                ORDER BY rank
                """,
                (date, platform, chart),
            ).fetchall()
            today_map = {r["appid"]: int(r["rank"]) for r in cur_t}

            cur_y = conn.execute(
                """
                SELECT appid, rank FROM rankings
                WHERE date = ? AND platform = ? AND chart = ?
                """,
                (yday, platform, chart),
            ).fetchall()
            yday_map = {r["appid"]: int(r["rank"]) for r in cur_y}

            for appid, rank_t in today_map.items():
                in_y = appid in yday_map
                row_hist = conn.execute(
                    """
                    SELECT 1 FROM rankings
                    WHERE platform = ? AND chart = ? AND appid = ?
                      AND date >= ? AND date < ?
                    LIMIT 1
                    """,
                    (platform, chart, appid, week_start, date),
                ).fetchone()
                is_new = 0 if row_hist else 1
                if in_y:
                    is_new = 0
                    rank_delta = rank_t - yday_map[appid]
                else:
                    rank_delta = None

                conn.execute(
                    """
                    INSERT INTO daily_status (date, platform, chart, appid, is_new, is_dropped, rank_delta)
                    VALUES (?, ?, ?, ?, ?, 0, ?)
                    ON CONFLICT(date, platform, chart, appid) DO UPDATE SET
                      is_new = excluded.is_new,
                      is_dropped = 0,
                      rank_delta = excluded.rank_delta
                    """,
                    (date, platform, chart, appid, is_new, rank_delta),
                )

            for appid, _ in yday_map.items():
                if appid in today_map:
                    continue
                conn.execute(
                    """
                    INSERT INTO daily_status (date, platform, chart, appid, is_new, is_dropped, rank_delta)
                    VALUES (?, ?, ?, ?, 0, 1, NULL)
                    ON CONFLICT(date, platform, chart, appid) DO UPDATE SET
                      is_new = 0,
                      is_dropped = 1,
                      rank_delta = NULL
                    """,
                    (date, platform, chart, appid),
                )

    logger.info("run_analysis completed for date=%s charts=%s", date, target)
