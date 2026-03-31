import pytest

from backend import db


def test_genre_columns_exist_after_init(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    with db.get_conn() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()}
    assert "genre_major" in cols
    assert "genre_minor" in cols


def test_init_db_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.init_db()


def test_insight_tables_exist_after_init(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    with db.get_conn() as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    for t in (
        "gameplay_tags",
        "game_gameplay_tags",
        "game_monetization",
        "virality_assumptions",
    ):
        assert t in names
