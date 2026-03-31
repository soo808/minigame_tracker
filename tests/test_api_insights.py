"""GET /api/insights — five dashboard blocks."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend import db


@pytest.fixture
def client_with_data(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    date = "2026-03-26"
    prev = "2026-03-25"
    with db.get_conn() as conn:
        for appid, name, tags, genre in [
            ("wx001", "传奇手游", "角色扮演,传奇", "角色扮演"),
            ("wx002", "消除小游戏", "休闲,消除", "休闲益智"),
            ("wx003", "策略战争", "策略,SLG", "策略经营"),
        ]:
            conn.execute(
                "INSERT INTO games (appid, platform, name, tags, genre_major, first_seen, updated_at) "
                "VALUES (?, 'wx', ?, ?, ?, ?, ?)",
                (appid, name, tags, genre, date, date),
            )
        for i, appid in enumerate(["wx001", "wx002", "wx003"], 1):
            conn.execute(
                "INSERT INTO rankings (date, platform, chart, rank, appid) VALUES (?, 'wx', 'popularity', ?, ?)",
                (date, i, appid),
            )
        conn.execute(
            "INSERT INTO rankings (date, platform, chart, rank, appid) VALUES (?, 'wx', 'popularity', 5, 'wx001')",
            (prev,),
        )
        conn.execute(
            "INSERT INTO daily_status (date, platform, chart, appid, is_new, is_dropped, rank_delta) "
            "VALUES (?, 'wx', 'popularity', 'wx002', 1, 0, NULL)",
            (date,),
        )
        conn.execute(
            "INSERT INTO daily_status (date, platform, chart, appid, is_new, is_dropped, rank_delta) "
            "VALUES (?, 'wx', 'popularity', 'wx001', 0, 0, -4)",
            (date,),
        )
    with patch("collector.scheduler.start_scheduler"), patch(
        "collector.scheduler.shutdown_scheduler"
    ):
        from backend.main import app

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_insights_returns_five_blocks(client_with_data):
    resp = client_with_data.get("/api/insights?platform=wx&date=2026-03-26")
    assert resp.status_code == 200
    data = resp.json()
    assert "new_entries" in data
    assert "dropped" in data
    assert "genre_distribution" in data
    assert "rank_movers" in data
    assert "tag_heat" in data


def test_insights_new_entries(client_with_data):
    resp = client_with_data.get("/api/insights?platform=wx&date=2026-03-26")
    data = resp.json()
    appids = [e["appid"] for e in data["new_entries"]]
    assert "wx002" in appids


def test_insights_rank_movers_top10(client_with_data):
    resp = client_with_data.get("/api/insights?platform=wx&date=2026-03-26")
    data = resp.json()
    movers = data["rank_movers"]
    assert len(movers) <= 10
    appids = [m["appid"] for m in movers]
    assert "wx001" in appids
    mover = next(m for m in movers if m["appid"] == "wx001")
    assert mover["delta"] == 4
    assert mover["today_rank"] == 1
    assert mover["prev_rank"] == 5


def test_insights_no_data_returns_empty_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "empty.db"))
    db.init_db()
    with patch("collector.scheduler.start_scheduler"), patch(
        "collector.scheduler.shutdown_scheduler"
    ):
        from backend.main import app

        c = TestClient(app, raise_server_exceptions=True)
    resp = c.get("/api/insights?platform=wx")
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_entries"] == []
    assert data["date"] is None


@pytest.fixture
def client_genre_double_chart(tmp_path, monkeypatch):
    """Same appid on two charts same day — genre counts once."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    date = "2026-03-26"
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO games (appid, platform, name, tags, genre_major, first_seen, updated_at) "
            "VALUES ('wx001', 'wx', 'A', 't', '角色扮演', ?, ?)",
            (date, date),
        )
        conn.execute(
            "INSERT INTO rankings (date, platform, chart, rank, appid) VALUES (?, 'wx', 'popularity', 1, 'wx001')",
            (date,),
        )
        conn.execute(
            "INSERT INTO rankings (date, platform, chart, rank, appid) VALUES (?, 'wx', 'bestseller', 1, 'wx001')",
            (date,),
        )
    with patch("collector.scheduler.start_scheduler"), patch(
        "collector.scheduler.shutdown_scheduler"
    ):
        from backend.main import app

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_insights_genre_distinct_appid(client_genre_double_chart):
    resp = client_genre_double_chart.get(f"/api/insights?platform=wx&date=2026-03-26")
    assert resp.status_code == 200
    genres = {g["genre"]: g["count"] for g in resp.json()["genre_distribution"]}
    assert genres.get("角色扮演") == 1


@pytest.fixture
def client_tag_double_chart(tmp_path, monkeypatch):
    """Same appid two charts — tag counts once per tag."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    date = "2026-03-26"
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO games (appid, platform, name, tags, genre_major, first_seen, updated_at) "
            "VALUES ('wx001', 'wx', 'A', '休闲,消除', '休闲益智', ?, ?)",
            (date, date),
        )
        for chart in ("popularity", "bestseller"):
            conn.execute(
                "INSERT INTO rankings (date, platform, chart, rank, appid) VALUES (?, 'wx', ?, 1, 'wx001')",
                (date, chart),
            )
    with patch("collector.scheduler.start_scheduler"), patch(
        "collector.scheduler.shutdown_scheduler"
    ):
        from backend.main import app

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_insights_tag_heat_distinct_appid(client_tag_double_chart):
    resp = client_tag_double_chart.get(f"/api/insights?platform=wx&date=2026-03-26")
    assert resp.status_code == 200
    heat = {t["tag"]: t["count"] for t in resp.json()["tag_heat"]}
    assert heat.get("休闲") == 1
    assert heat.get("消除") == 1
