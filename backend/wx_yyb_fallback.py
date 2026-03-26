"""When Gravity wx popularity/bestseller failed, backfill from YYB `popular` / `bestseller` (top 100).

Depends on real YYB ingestion (see `2026-03-25-yyb-scraper.md` Task 1–10, then Task 7b). Without yyb rows in DB,
this module is a no-op for those charts.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend import db
from backend.analyzer import status as analyzer_status
from backend.ingest_service import apply_chart_payload

logger = logging.getLogger(__name__)

# YYB chart -> wx DB chart (see YYB scraper plan)
YYB_TO_WX_CHART: dict[str, str] = {
    "popular": "popularity",
    "bestseller": "bestseller",
}

FALLBACK_NOTE = "yyb_fallback"


def _wx_snapshot_status(conn, date: str, wx_chart: str) -> str | None:
    row = conn.execute(
        """
        SELECT status FROM snapshots
        WHERE date = ? AND platform = 'wx' AND chart = ?
        """,
        (date, wx_chart),
    ).fetchone()
    return row["status"] if row else None


def _load_yyb_games_top100(conn, date: str, yyb_chart: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT r.rank, r.appid, g.name, g.icon_url, g.tags, g.developer
        FROM rankings r
        JOIN games g ON g.appid = r.appid
        WHERE r.date = ? AND r.platform = 'yyb' AND r.chart = ?
        ORDER BY r.rank
        LIMIT 100
        """,
        (date, yyb_chart),
    ).fetchall()
    games: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        tags_val = row["tags"]
        if tags_val and isinstance(tags_val, str):
            try:
                parsed = json.loads(tags_val)
                if isinstance(parsed, list):
                    tags_val = parsed
            except json.JSONDecodeError:
                pass
        games.append(
            {
                "rank": i,
                "appid": row["appid"],
                "name": row["name"],
                "icon_url": row["icon_url"],
                "tags": tags_val,
                "developer": row["developer"],
            }
        )
    return games


def backfill_wx_from_yyb(date: str) -> None:
    """
    For each mapped pair: if wx snapshot is `failed` and YYB has rows, write wx rankings
    via apply_chart_payload with note=yyb_fallback, then run_analysis for backfilled charts only.
    """
    to_apply: list[tuple[str, str, list[dict[str, Any]]]] = []

    with db.get_conn() as conn:
        for yyb_chart, wx_chart in YYB_TO_WX_CHART.items():
            st = _wx_snapshot_status(conn, date, wx_chart)
            if st != "failed":
                if st is not None:
                    logger.debug(
                        "wx_yyb_fallback skip wx/%s: snapshot status=%s (need failed)",
                        wx_chart,
                        st,
                    )
                continue
            games = _load_yyb_games_top100(conn, date, yyb_chart)
            if not games:
                logger.warning(
                    "wx_yyb_fallback skip wx/%s: no yyb data for yyb/%s date=%s",
                    wx_chart,
                    yyb_chart,
                    date,
                )
                continue
            to_apply.append((yyb_chart, wx_chart, games))

    if not to_apply:
        return

    charts_done: set[tuple[str, str]] = set()
    for yyb_chart, wx_chart, games in to_apply:
        snap_status = "ok" if len(games) >= 100 else "partial"
        logger.info(
            "wx_yyb_fallback applying wx/%s from yyb/%s count=%s status=%s",
            wx_chart,
            yyb_chart,
            len(games),
            snap_status,
        )
        apply_chart_payload(
            date,
            "wx",
            wx_chart,
            games,
            snap_status,
            FALLBACK_NOTE,
        )
        charts_done.add(("wx", wx_chart))

    if charts_done:
        try:
            analyzer_status.run_analysis(date, charts_done)
        except Exception:
            logger.exception("wx_yyb_fallback run_analysis failed date=%s", date)
