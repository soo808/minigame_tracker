import pytest

from backend import db


def test_yyb_tag_stats_table_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='yyb_tag_stats'"
        ).fetchone()
    assert row is not None, "yyb_tag_stats table should exist after init_db()"


def test_yyb_tag_stats_primary_key(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    with db.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO yyb_tag_stats (date, chart, tag, game_count, avg_rank, top10_count, new_entries)
            VALUES ('2026-03-25', 'popular', '角色扮演', 10, 55.5, 3, 2)
            """
        )
        conn.execute(
            """
            INSERT INTO yyb_tag_stats (date, chart, tag, game_count, avg_rank, top10_count, new_entries)
            VALUES ('2026-03-25', 'popular', '角色扮演', 12, 50.0, 4, 3)
            ON CONFLICT(date, chart, tag) DO UPDATE SET
              game_count = excluded.game_count,
              avg_rank = excluded.avg_rank,
              top10_count = excluded.top10_count,
              new_entries = excluded.new_entries
            """
        )
        row = conn.execute(
            "SELECT game_count FROM yyb_tag_stats WHERE date='2026-03-25' AND chart='popular' AND tag='角色扮演'"
        ).fetchone()
    assert row["game_count"] == 12
