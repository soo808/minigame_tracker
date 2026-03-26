import json

import pytest

from backend import db


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def _insert_game(conn, appid, platform, name, tags=None, developer=None):
    conn.execute(
        """
        INSERT OR IGNORE INTO games (appid, platform, name, tags, developer, first_seen, updated_at)
        VALUES (?, ?, ?, ?, ?, '2026-03-25', '2026-03-25')
        """,
        (appid, platform, name, tags, developer),
    )


def _insert_ranking(conn, date, platform, chart, rank, appid):
    conn.execute(
        """
        INSERT OR IGNORE INTO rankings (date, platform, chart, rank, appid)
        VALUES (?, ?, ?, ?, ?)
        """,
        (date, platform, chart, rank, appid),
    )


def _insert_daily_status(conn, date, platform, chart, appid, is_new=0):
    conn.execute(
        """
        INSERT OR IGNORE INTO daily_status (date, platform, chart, appid, is_new, is_dropped, rank_delta)
        VALUES (?, ?, ?, ?, ?, 0, NULL)
        """,
        (date, platform, chart, appid, is_new),
    )


class TestRunYybTagAnalysis:
    def test_basic_tag_stats(self, tmp_path, monkeypatch):
        _setup_db(tmp_path, monkeypatch)
        date = "2026-03-25"
        with db.get_conn() as conn:
            _insert_game(conn, "wx001", "yyb", "Game A", json.dumps(["休闲", "策略"]))
            _insert_game(conn, "wx002", "yyb", "Game B", json.dumps(["休闲"]))
            _insert_game(conn, "wx003", "yyb", "Game C", None)
            _insert_ranking(conn, date, "yyb", "popular", 1, "wx001")
            _insert_ranking(conn, date, "yyb", "popular", 2, "wx002")
            _insert_ranking(conn, date, "yyb", "popular", 3, "wx003")
            _insert_daily_status(conn, date, "yyb", "popular", "wx001", is_new=1)
            _insert_daily_status(conn, date, "yyb", "popular", "wx002")
            _insert_daily_status(conn, date, "yyb", "popular", "wx003")

        from backend.analyzer.yyb_tags import run_yyb_tag_analysis

        run_yyb_tag_analysis(date)

        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM yyb_tag_stats WHERE date=? AND chart='popular' AND tag='休闲'",
                (date,),
            ).fetchone()

        assert row is not None
        assert row["game_count"] == 2
        assert row["avg_rank"] == pytest.approx(1.5)
        assert row["new_entries"] == 1

    def test_top10_count(self, tmp_path, monkeypatch):
        _setup_db(tmp_path, monkeypatch)
        date = "2026-03-25"
        tag = json.dumps(["角色扮演"])
        with db.get_conn() as conn:
            for i in range(15):
                appid = f"wx{i:03d}"
                _insert_game(conn, appid, "yyb", f"Game {i}", tag)
                _insert_ranking(conn, date, "yyb", "popular", i + 1, appid)
                _insert_daily_status(conn, date, "yyb", "popular", appid)

        from backend.analyzer.yyb_tags import run_yyb_tag_analysis

        run_yyb_tag_analysis(date)

        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT top10_count FROM yyb_tag_stats WHERE date=? AND chart='popular' AND tag='角色扮演'",
                (date,),
            ).fetchone()
        assert row["top10_count"] == 10

    def test_upsert_overwrites_previous(self, tmp_path, monkeypatch):
        _setup_db(tmp_path, monkeypatch)
        date = "2026-03-25"
        with db.get_conn() as conn:
            _insert_game(conn, "wx001", "yyb", "G", json.dumps(["策略"]))
            _insert_ranking(conn, date, "yyb", "popular", 5, "wx001")
            _insert_daily_status(conn, date, "yyb", "popular", "wx001")

        from backend.analyzer.yyb_tags import run_yyb_tag_analysis

        run_yyb_tag_analysis(date)
        run_yyb_tag_analysis(date)

        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT COUNT(*) AS c FROM yyb_tag_stats WHERE date=? AND chart='popular' AND tag='策略'",
                (date,),
            ).fetchone()
        assert rows["c"] == 1

    def test_three_charts_written(self, tmp_path, monkeypatch):
        _setup_db(tmp_path, monkeypatch)
        date = "2026-03-25"
        with db.get_conn() as conn:
            for chart in ("popular", "bestseller", "new_game"):
                appid = f"wx_{chart}"
                _insert_game(conn, appid, "yyb", f"Game {chart}", json.dumps(["休闲"]))
                _insert_ranking(conn, date, "yyb", chart, 1, appid)
                _insert_daily_status(conn, date, "yyb", chart, appid)

        from backend.analyzer.yyb_tags import run_yyb_tag_analysis

        run_yyb_tag_analysis(date)

        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT chart FROM yyb_tag_stats WHERE date=?", (date,)
            ).fetchall()
        charts_found = {r["chart"] for r in rows}
        assert charts_found == {"popular", "bestseller", "new_game"}
