import pytest

from backend import db


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    return db


def _insert_game(db_mod, appid, name, tags, genre_major=None):
    with db_mod.get_conn() as conn:
        conn.execute(
            "INSERT INTO games (appid, platform, name, tags, genre_major, first_seen, updated_at) "
            "VALUES (?, 'wx', ?, ?, ?, '2026-03-26', '2026-03-27')",
            (appid, name, tags, genre_major),
        )


class TestClassifyByRules:
    def test_arpg_maps_to_role_playing(self):
        from backend.analyzer.classify import _classify_by_rules

        assert _classify_by_rules("角色扮演,传奇") == ("角色扮演", "ARPG")

    def test_slg_maps_to_strategy(self):
        from backend.analyzer.classify import _classify_by_rules

        assert _classify_by_rules("策略,三国") == ("策略经营", "SLG")

    def test_casual_maps_to_casual(self):
        from backend.analyzer.classify import _classify_by_rules

        assert _classify_by_rules("休闲,消除") == ("休闲益智", "消除")

    def test_unknown_returns_none(self):
        from backend.analyzer.classify import _classify_by_rules

        assert _classify_by_rules("未知标签,新品") is None

    def test_empty_returns_none(self):
        from backend.analyzer.classify import _classify_by_rules

        assert _classify_by_rules("") is None


class TestClassifyGamesBatch:
    def test_rule_classified_games_written_to_db(self, tmp_path, monkeypatch):
        db_mod = _setup_db(tmp_path, monkeypatch)
        _insert_game(db_mod, "wx001", "传奇手游", "角色扮演,传奇")
        from backend.analyzer import classify

        result = classify.classify_games_batch()
        assert result["rule_classified"] >= 1
        with db_mod.get_conn() as conn:
            row = conn.execute("SELECT genre_major FROM games WHERE appid='wx001'").fetchone()
        assert row["genre_major"] == "角色扮演"

    def test_already_classified_skipped(self, tmp_path, monkeypatch):
        db_mod = _setup_db(tmp_path, monkeypatch)
        _insert_game(db_mod, "wx002", "已分类游戏", "角色扮演", genre_major="角色扮演")
        from backend.analyzer import classify

        result = classify.classify_games_batch()
        assert result["rule_classified"] == 0
        assert result["ai_classified"] == 0

    def test_unmatched_falls_back_to_other_without_api(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        db_mod = _setup_db(tmp_path, monkeypatch)
        _insert_game(db_mod, "wx003", "奇怪游戏", "未知标签,新品")
        from backend.analyzer import classify

        classify.classify_games_batch()
        with db_mod.get_conn() as conn:
            row = conn.execute("SELECT genre_major FROM games WHERE appid='wx003'").fetchone()
        assert row["genre_major"] == "其他"
