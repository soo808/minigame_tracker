"""Rank history series for sparklines and detail charts."""
from __future__ import annotations

from backend import db


def rank_series(
    appid: str,
    platform: str,
    chart: str,
    days: int,
    end_date: str | None = None,
) -> list[dict]:
    """List of {date, rank} ascending by date, within last `days` calendar days."""
    with db.get_conn() as conn:
        if end_date:
            end = end_date
        else:
            row = conn.execute(
                "SELECT MAX(date) AS d FROM rankings WHERE appid = ? AND platform = ? AND chart = ?",
                (appid, platform, chart),
            ).fetchone()
            end = row["d"] if row and row["d"] else None
        if not end:
            return []
        rows = conn.execute(
            """
            SELECT date, rank FROM rankings
            WHERE appid = ? AND platform = ? AND chart = ?
              AND date <= ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (appid, platform, chart, end, days),
        ).fetchall()
    out = [{"date": r["date"], "rank": int(r["rank"])} for r in reversed(rows)]
    return out


def charts_for_platform(platform: str) -> list[str]:
    if platform == "wx":
        return ["popularity", "most_played", "bestseller"]
    if platform == "yyb":
        return ["popular", "bestseller", "new_game"]
    return ["popularity", "bestseller", "fresh_game"]


def all_charts_series_for_platform(
    appid: str,
    platform: str,
    days: int,
    end_date: str | None = None,
) -> dict[str, list[dict]]:
    return {
        c: rank_series(appid, platform, c, days, end_date)
        for c in charts_for_platform(platform)
    }
