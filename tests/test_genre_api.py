from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO games (appid, platform, name, tags, genre_major, first_seen, updated_at) "
            "VALUES ('wx001', 'wx', '传奇手游', '角色扮演', '角色扮演', '2026-03-26', '2026-03-27')"
        )
        conn.execute(
            "INSERT INTO games (appid, platform, name, tags, genre_major, first_seen, updated_at) "
            "VALUES ('wx002', 'wx', '消消乐', '休闲,消除', '休闲益智', '2026-03-26', '2026-03-27')"
        )
        conn.execute(
            "INSERT INTO rankings (date, platform, chart, appid, rank) VALUES ('2026-03-27','wx','popularity','wx001',1)"
        )
        conn.execute(
            "INSERT INTO rankings (date, platform, chart, appid, rank) VALUES ('2026-03-27','wx','popularity','wx002',2)"
        )
    with patch("collector.scheduler.start_scheduler"), patch("collector.scheduler.shutdown_scheduler"):
        from backend.main import app

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_genre_snapshot_returns_distribution(client):
    resp = client.get("/api/genre/snapshot?date=2026-03-27&platform=wx&chart=popularity")
    assert resp.status_code == 200
    data = resp.json()
    assert "genre_distribution" in data
    assert len(data["genre_distribution"]) >= 1
    assert "tag_frequency" in data


def test_genre_trend_returns_series(client):
    resp = client.get("/api/genre/trend?platform=wx&chart=popularity&days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert "dates" in data
    assert "series" in data
