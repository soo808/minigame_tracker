"""Write rankings + snapshots; trigger analysis batch gate."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from backend import db
from backend.analyzer import status as analyzer_status

logger = logging.getLogger(__name__)

INGEST_CHART_TO_DB: dict[tuple[str, str], str] = {
    ("wx", "renqi"): "popularity",
    ("wx", "changwan"): "most_played",
    ("wx", "changxiao"): "bestseller",
    ("dy", "renqi"): "popularity",
    ("dy", "changxiao"): "bestseller",
    ("dy", "xinyou"): "fresh_game",
}

def normalize_tags(tags: Any) -> str | None:
    if tags is None:
        return None
    if isinstance(tags, str):
        return tags
    try:
        return json.dumps(tags, ensure_ascii=False)
    except TypeError:
        return None


def map_ingest_chart(platform: str, chart: str) -> str:
    key = (platform, chart)
    if key not in INGEST_CHART_TO_DB:
        raise ValueError(f"invalid chart for platform: {platform} / {chart}")
    return INGEST_CHART_TO_DB[key]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def apply_chart_payload(
    date: str,
    platform: str,
    db_chart: str,
    games: list[dict],
    snapshot_status: str,
    note: str | None = None,
) -> None:
    """Upsert games, replace rankings slice, upsert snapshot; then maybe run_analysis."""
    fetched = now_iso()
    with db.get_conn() as conn:
        for g in games:
            appid = g["appid"]
            name = g["name"]
            icon_url = g.get("icon_url")
            tags = normalize_tags(g.get("tags"))
            developer = g.get("developer")
            conn.execute(
                """
                INSERT INTO games (appid, platform, name, icon_url, tags, developer, first_seen, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(appid) DO UPDATE SET
                  name = excluded.name,
                  icon_url = COALESCE(excluded.icon_url, games.icon_url),
                  tags = COALESCE(excluded.tags, games.tags),
                  developer = COALESCE(excluded.developer, games.developer),
                  first_seen = COALESCE(games.first_seen, excluded.first_seen),
                  updated_at = excluded.updated_at
                """,
                (
                    appid,
                    platform,
                    name,
                    icon_url,
                    tags,
                    developer,
                    date,
                    fetched,
                ),
            )

        conn.execute(
            "DELETE FROM rankings WHERE date = ? AND platform = ? AND chart = ?",
            (date, platform, db_chart),
        )
        for g in games:
            conn.execute(
                """
                INSERT INTO rankings (date, platform, chart, rank, appid)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(date, platform, chart, appid) DO UPDATE SET rank = excluded.rank
                """,
                (date, platform, db_chart, int(g["rank"]), g["appid"]),
            )

        conn.execute(
            """
            INSERT INTO snapshots (date, platform, chart, fetched_at, status, game_count, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, platform, chart) DO UPDATE SET
              fetched_at = excluded.fetched_at,
              status = excluded.status,
              game_count = excluded.game_count,
              note = excluded.note
            """,
            (
                date,
                platform,
                db_chart,
                fetched,
                snapshot_status,
                len(games),
                note,
            ),
        )

    try:
        analyzer_status.maybe_run_analysis_after_snapshot(date)
    except Exception:
        logger.exception("analyzer failed after ingest for date=%s", date)
