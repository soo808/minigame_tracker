from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import backend.db as db_mod

    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "test.db"))
    db_mod.init_db()

    with patch("collector.scheduler.start_scheduler"), patch("collector.scheduler.shutdown_scheduler"):
        from backend.main import app

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


class TestRankingsYyb:
    def test_yyb_platform_accepted(self, client):
        resp = client.get("/api/rankings?platform=yyb")
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "yyb"
        assert "popular" in data["charts"]
        assert "bestseller" in data["charts"]
        assert "new_game" in data["charts"]

    def test_invalid_platform_rejected(self, client):
        resp = client.get("/api/rankings?platform=tiktok")
        assert resp.status_code == 422


class TestCollectYybEndpoint:
    def test_collect_yyb_triggers_collection(self, client, monkeypatch):
        import backend.main as main_mod

        called = {}

        def fake_collect(d, *, force=False):
            called["date"] = d
            called["force"] = force

        monkeypatch.setattr(main_mod, "collect_yyb_charts", fake_collect)

        resp = client.get("/api/collect/yyb?date=2026-03-25")
        assert resp.status_code == 200
        assert called["date"] == "2026-03-25"
        assert called["force"] is False

    def test_collect_yyb_force_query(self, client, monkeypatch):
        import backend.main as main_mod

        called = {}

        def fake_collect(d, *, force=False):
            called["date"] = d
            called["force"] = force

        monkeypatch.setattr(main_mod, "collect_yyb_charts", fake_collect)

        resp = client.get("/api/collect/yyb?date=2026-03-25&force=1")
        assert resp.status_code == 200
        assert called["force"] is True

    def test_collect_yyb_uses_today_if_no_date(self, client, monkeypatch):
        import backend.main as main_mod

        called = {}

        def fake_collect(d, *, force=False):
            called["date"] = d

        monkeypatch.setattr(main_mod, "collect_yyb_charts", fake_collect)

        resp = client.get("/api/collect/yyb")
        assert resp.status_code == 200
        assert called["date"] == date.today().strftime("%Y-%m-%d")


class TestYybInsightsEndpoint:
    def test_insights_returns_structure(self, client, tmp_path, monkeypatch):
        import backend.db as db_mod

        monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "test.db"))
        db_mod.init_db()

        d = "2026-03-25"
        with db_mod.get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO games (appid, platform, name, first_seen, updated_at) "
                "VALUES ('wx001', 'yyb', 'Game A', ?, ?)",
                (d, d),
            )
            conn.execute(
                "INSERT OR IGNORE INTO rankings (date, platform, chart, rank, appid) "
                "VALUES (?, 'yyb', 'popular', 1, 'wx001')",
                (d,),
            )
            conn.execute(
                "INSERT OR IGNORE INTO yyb_tag_stats (date, chart, tag, game_count, avg_rank, top10_count, new_entries) "
                "VALUES (?, 'popular', '休闲', 1, 1.0, 1, 0)",
                (d,),
            )

        resp = client.get(f"/api/yyb/insights?date={d}&chart=popular")
        assert resp.status_code == 200
        data = resp.json()
        assert "date" in data
        assert "chart" in data
        assert "top_tags" in data
        assert "rising_tags" in data
        assert "developer_concentration" in data
        assert "wx_overlap_rate" in data
