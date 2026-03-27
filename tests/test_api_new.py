from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    with patch("collector.scheduler.start_scheduler"), patch("collector.scheduler.shutdown_scheduler"):
        from backend.main import app

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


@pytest.fixture
def client_with_rank_data(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO games (appid, platform, name, developer, tags, genre_major, first_seen, updated_at) "
            "VALUES ('wx001', 'wx', '传奇归来', '龙图游戏', '角色扮演,传奇', '角色扮演', '2026-03-20', '2026-03-27')"
        )
        conn.execute(
            "INSERT INTO games (appid, platform, name, developer, tags, genre_major, first_seen, updated_at) "
            "VALUES ('wx002', 'wx', '开心消消乐', '乐元素', '休闲,消除', '休闲益智', '2026-03-20', '2026-03-27')"
        )
        for d in range(7):
            date = f"2026-03-{21 + d:02d}"
            conn.execute(
                "INSERT INTO rankings (date, platform, chart, appid, rank) VALUES (?,?,?,?,?)",
                (date, "wx", "popularity", "wx001", 3 + d),
            )
            conn.execute(
                "INSERT INTO rankings (date, platform, chart, appid, rank) VALUES (?,?,?,?,?)",
                (date, "wx", "bestseller", "wx001", 5),
            )
    with patch("collector.scheduler.start_scheduler"), patch("collector.scheduler.shutdown_scheduler"):
        from backend.main import app

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_aggregate_week_returns_avg_rank(client_with_rank_data):
    resp = client_with_rank_data.get(
        "/api/rankings/aggregate?platform=wx&range=week&end_date=2026-03-27"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "charts" in data
    popularity = data["charts"].get("popularity", [])
    assert len(popularity) >= 1
    wx001 = next((g for g in popularity if g["appid"] == "wx001"), None)
    assert wx001 is not None
    assert "avg_rank" in wx001
    assert wx001["appearances"] == 7


def test_search_by_game_name(client_with_rank_data):
    resp = client_with_rank_data.get(
        "/api/search?q=传奇&platform=wx&date=2026-03-27&field=name"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) >= 1
    assert any("传奇" in r["name"] for r in data["results"])
    assert all("传奇" in r["name"] for r in data["results"])


def test_search_by_developer_name(client_with_rank_data):
    resp = client_with_rank_data.get(
        "/api/search?q=龙图&platform=wx&date=2026-03-27&field=developer"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) >= 1
    assert data["results"][0]["developer"] == "龙图游戏"
    assert all("龙图" in (r["developer"] or "") for r in data["results"])


def test_search_empty_query_returns_empty(client):
    resp = client.get("/api/search?q=&platform=wx&date=2026-03-27")
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_aggregate_invalid_range_returns_422(client):
    resp = client.get("/api/rankings/aggregate?platform=wx&range=year&end_date=2026-03-27")
    assert resp.status_code == 422
