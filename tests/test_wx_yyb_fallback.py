"""WX backfill from YYB when Gravity snapshots are failed."""
from __future__ import annotations

import json

import pytest

from backend import db
from backend.wx_yyb_fallback import backfill_wx_from_yyb, FALLBACK_NOTE


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "t.db")
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    return path


def _insert_snapshot(conn, date: str, platform: str, chart: str, status: str, note=None):
    conn.execute(
        """
        INSERT INTO snapshots (date, platform, chart, fetched_at, status, game_count, note)
        VALUES (?, ?, ?, '2026-03-25T10:00:00', ?, ?, ?)
        """,
        (date, platform, chart, status, 0 if status == "failed" else 10, note),
    )


def _insert_game(conn, appid: str, platform: str, name: str, **kw):
    conn.execute(
        """
        INSERT INTO games (appid, platform, name, icon_url, tags, developer, first_seen, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            appid,
            platform,
            name,
            kw.get("icon_url"),
            kw.get("tags"),
            kw.get("developer"),
            "2026-03-25",
            "2026-03-25",
        ),
    )


def _insert_ranking(conn, date: str, platform: str, chart: str, rank: int, appid: str):
    conn.execute(
        """
        INSERT INTO rankings (date, platform, chart, rank, appid)
        VALUES (?, ?, ?, ?, ?)
        """,
        (date, platform, chart, rank, appid),
    )


def test_backfill_when_wx_failed_and_yyb_has_data(db_path):
    date = "2026-03-25"
    with db.get_conn() as conn:
        for i in range(1, 4):
            aid = f"wxpkg{i:03d}"
            _insert_game(conn, aid, "yyb", f"Game{i}", tags=json.dumps(["休闲"]))
            _insert_ranking(conn, date, "yyb", "popular", i, aid)
        _insert_snapshot(conn, date, "wx", "popularity", "failed", "http_401")

    backfill_wx_from_yyb(date)

    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT rank, appid FROM rankings WHERE date=? AND platform='wx' AND chart='popularity' ORDER BY rank",
            (date,),
        ).fetchall()
        snap = conn.execute(
            "SELECT status, note, game_count FROM snapshots WHERE date=? AND platform='wx' AND chart='popularity'",
            (date,),
        ).fetchone()

    assert len(rows) == 3
    assert rows[0]["appid"] == "wxpkg001"
    assert snap["status"] in ("ok", "partial")
    assert snap["note"] == FALLBACK_NOTE
    assert snap["game_count"] == 3


def test_no_overwrite_when_wx_ok(db_path):
    date = "2026-03-26"
    with db.get_conn() as conn:
        _insert_game(conn, "keep_only", "wx", "Kept", tags=None)
        _insert_ranking(conn, date, "wx", "popularity", 1, "keep_only")
        _insert_snapshot(conn, date, "wx", "popularity", "ok", None)
        _insert_game(conn, "yyb_only", "yyb", "YYB Game", tags=None)
        _insert_ranking(conn, date, "yyb", "popular", 1, "yyb_only")

    backfill_wx_from_yyb(date)

    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT appid FROM rankings WHERE date=? AND platform='wx' AND chart='popularity'",
            (date,),
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["appid"] == "keep_only"


def test_run_analysis_subset_does_not_wipe_other_charts_daily_status(db_path):
    """Regression: partial run_analysis only clears target charts' daily_status rows."""
    from backend.analyzer import status as st

    date = "2026-03-27"
    with db.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO games (appid, platform, name, first_seen, updated_at)
            VALUES ('dy1', 'dy', 'Dy Game', ?, ?)
            """,
            (date, date),
        )
        conn.execute(
            """
            INSERT INTO daily_status (date, platform, chart, appid, is_new, is_dropped, rank_delta)
            VALUES (?, 'dy', 'popularity', 'dy1', 0, 0, 0)
            """,
            (date,),
        )

    st.run_analysis(date, {("wx", "popularity")})

    with db.get_conn() as conn:
        dy_row = conn.execute(
            "SELECT 1 FROM daily_status WHERE date=? AND platform='dy' AND chart='popularity'",
            (date,),
        ).fetchone()

    assert dy_row is not None
