"""GET /api/game/{appid} same_genre_peers and include= flags."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend import db, main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    with db.get_conn() as conn:
        for aid, name, gm in [
            ("wxa", "Game A", "休闲益智"),
            ("wxb", "Game B", "休闲益智"),
            ("wxc", "Game C", "角色扮演"),
        ]:
            conn.execute(
                "INSERT INTO games (appid, platform, name, genre_major, first_seen, updated_at) "
                "VALUES (?, 'wx', ?, ?, '2026-03-01', '2026-03-01')",
                (aid, name, gm),
            )
        for appid, rank in [("wxa", 1), ("wxb", 2), ("wxc", 5)]:
            conn.execute(
                "INSERT INTO rankings (date, platform, chart, appid, rank) VALUES (?,?,?,?,?)",
                ("2026-03-10", "wx", "popularity", appid, rank),
            )
    return TestClient(main.app)


def test_same_genre_peers_excludes_self_and_same_major(client):
    r = client.get(
        "/api/game/wxa?platform=wx&date=2026-03-10",
    )
    assert r.status_code == 200
    data = r.json()
    assert data["snapshot_date"] == "2026-03-10"
    peers = data["same_genre_peers"]["renqi"]
    assert len(peers) == 1
    assert peers[0]["appid"] == "wxb"
    assert peers[0]["rank"] == 2


def test_same_genre_peers_empty_when_unclassified(client):
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO games (appid, platform, name, first_seen, updated_at) "
            "VALUES ('wxu', 'wx', 'Unk', '2026-03-01', '2026-03-01')"
        )
        conn.execute(
            "INSERT INTO rankings (date, platform, chart, appid, rank) VALUES (?,?,?,?,?)",
            ("2026-03-10", "wx", "popularity", "wxu", 99),
        )
    r = client.get("/api/game/wxu?platform=wx&date=2026-03-10")
    assert r.status_code == 200
    assert r.json()["same_genre_peers"]["renqi"] == []


def test_include_gameplay_monetization_virality(client):
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO gameplay_tags (slug, name) VALUES ('loot', '开箱类')"
        )
        tid = conn.execute(
            "SELECT id FROM gameplay_tags WHERE slug='loot'"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO game_gameplay_tags (appid, tag_id, source) VALUES ('wxa', ?, 'manual')",
            (tid,),
        )
        conn.execute(
            """
            INSERT INTO game_monetization
              (appid, monetization_model, mix_note, source)
            VALUES ('wxa', 'hybrid', 'IAA+IAP', 'manual')
            """
        )
        conn.execute(
            """
            INSERT INTO virality_assumptions
              (appid, channels, hypothesis, source)
            VALUES ('wxa', '["wechat_share"]', '分享得奖励', 'manual')
            """
        )
    r = client.get(
        "/api/game/wxa?platform=wx&date=2026-03-10"
        "&include=gameplay,monetization,virality",
    )
    assert r.status_code == 200
    d = r.json()
    assert len(d["gameplay_tags"]) == 1
    assert d["gameplay_tags"][0]["slug"] == "loot"
    assert d["monetization"]["monetization_model"] == "hybrid"
    assert len(d["virality_assumptions"]) == 1
    assert "分享" in d["virality_assumptions"][0]["hypothesis"]


def test_gameplay_assign_and_list_tags(client):
    with db.get_conn() as conn:
        conn.execute("INSERT INTO gameplay_tags (slug, name) VALUES ('t1', 'T1')")
        tid = conn.execute("SELECT id FROM gameplay_tags WHERE slug='t1'").fetchone()[
            "id"
        ]
    r = client.post(
        "/api/gameplay/assign",
        json={
            "appid": "wxa",
            "tag_id": tid,
            "role": "primary",
            "source": "manual",
            "updated_by": "tester",
        },
    )
    assert r.status_code == 200
    lr = client.get("/api/gameplay/tags")
    assert lr.status_code == 200
    assert any(t["slug"] == "t1" for t in lr.json()["tags"])


@patch.object(main, "start_scheduler")
@patch.object(main, "shutdown_scheduler")
def test_monetization_upsert(_sh, _st, tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t2.db"))
    db.init_db()
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO games (appid, platform, name, first_seen, updated_at) "
            "VALUES ('z1', 'wx', 'Z', '2026-03-01', '2026-03-01')"
        )
    c = TestClient(main.app)
    r = c.post(
        "/api/monetization/upsert",
        json={"appid": "z1", "monetization_model": "iaa", "source": "manual"},
    )
    assert r.status_code == 200
    g = c.get("/api/game/z1?platform=wx&include=monetization")
    assert g.json()["monetization"]["monetization_model"] == "iaa"
