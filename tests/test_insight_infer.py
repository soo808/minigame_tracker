"""Tests for batch insight LLM apply path (mocked LLM)."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from backend import db


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    return db


def _insert_game(db_mod, appid: str, name: str = "Test", tags: str = "休闲"):
    with db_mod.get_conn() as conn:
        conn.execute(
            "INSERT INTO games (appid, platform, name, tags, first_seen, updated_at) "
            "VALUES (?, 'wx', ?, ?, '2026-03-26', '2026-03-27')",
            (appid, name, tags),
        )


def test_run_insight_infer_batch_writes_ai_rows(tmp_path, monkeypatch):
    db_mod = _setup_db(tmp_path, monkeypatch)
    _insert_game(db_mod, "wx_infer_1", "消消乐", "休闲,消除")

    fake_items = [
        {
            "index": 1,
            "monetization_model": "iaa",
            "mix_note": "偏广告",
            "evidence_summary": ["休闲榜", "消除"],
            "gameplay_slugs": ["merge"],
            "virality_hypothesis": "分享关卡",
            "virality_channels": ["wechat_share"],
        }
    ]

    with patch(
        "backend.analyzer.insight_infer._ai_insight_batch",
        return_value=(fake_items, None),
    ):
        from backend.analyzer.insight_infer import run_insight_infer_batch

        out = run_insight_infer_batch(limit=5, batch_size=10, only_missing=True, force=False)

    assert out["candidates"] >= 1
    assert out["batches"] >= 1
    assert out["monetization_updated"] >= 1

    with db_mod.get_conn() as conn:
        m = conn.execute(
            "SELECT monetization_model, source, updated_by FROM game_monetization WHERE appid = ?",
            ("wx_infer_1",),
        ).fetchone()
    assert m["monetization_model"] == "iaa"
    assert m["source"] == "ai"
    assert m["updated_by"] == "llm_batch"


def test_manual_monetization_excluded_from_candidates(tmp_path, monkeypatch):
    db_mod = _setup_db(tmp_path, monkeypatch)
    _insert_game(db_mod, "wx_manual", "手动游戏", "策略")
    with db_mod.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO game_monetization
              (appid, monetization_model, mix_note, confidence, source, updated_by, updated_at)
            VALUES (?, 'iap', '人工', 0.9, 'manual', 'ops', datetime('now'))
            """,
            ("wx_manual",),
        )

    with patch(
        "backend.analyzer.insight_infer._ai_insight_batch",
        return_value=([], None),
    ) as mock_llm:
        from backend.analyzer.insight_infer import run_insight_infer_batch

        out = run_insight_infer_batch(limit=10, batch_size=5, only_missing=True, force=False)

    mock_llm.assert_not_called()
    assert out["candidates"] == 0
    assert out["batches"] == 0


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    _insert_game(db, appid="wx_api", name="API 测", tags="休闲")
    with patch("collector.scheduler.start_scheduler"), patch(
        "collector.scheduler.shutdown_scheduler"
    ):
        from backend.main import app
        from fastapi.testclient import TestClient

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_api_config_show_top50_bulk_default(api_client, monkeypatch):
    monkeypatch.delenv("SHOW_TOP50_BULK_BUTTON", raising=False)
    r = api_client.get("/api/config")
    assert r.status_code == 200
    assert r.json()["show_top50_bulk_button"] is True


def test_api_config_hide_top50_bulk(api_client, monkeypatch):
    monkeypatch.setenv("SHOW_TOP50_BULK_BUTTON", "0")
    r = api_client.get("/api/config")
    assert r.status_code == 200
    assert r.json()["show_top50_bulk_button"] is False


def test_insight_infer_batch_endpoint(api_client, monkeypatch):
    fake_items = [
        {
            "index": 1,
            "monetization_model": "hybrid",
            "mix_note": "混合",
            "evidence_summary": ["a"],
            "gameplay_slugs": [],
            "virality_hypothesis": "",
            "virality_channels": [],
        }
    ]
    monkeypatch.setattr(
        "backend.analyzer.insight_infer._ai_insight_batch",
        lambda games: (fake_items, None),
    )
    r = api_client.post("/api/insight/infer-batch", json={"limit": 5, "batch_size": 5})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data.get("candidates", 0) >= 1


def test_monetization_run_default_body(api_client, monkeypatch):
    fake_items = [
        {
            "index": 1,
            "monetization_model": "unknown",
            "mix_note": "",
            "evidence_summary": [],
            "gameplay_slugs": [],
            "virality_hypothesis": "",
            "virality_channels": [],
        }
    ]
    monkeypatch.setattr(
        "backend.analyzer.insight_infer._ai_insight_batch",
        lambda games: (fake_items, None),
    )
    r = api_client.post("/api/monetization/run")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_candidates_ordered_by_best_rank(tmp_path, monkeypatch):
    """Higher rank (lower number) on chart comes first in batch."""
    db_mod = _setup_db(tmp_path, monkeypatch)
    for aid, name in [("wx_slow", "慢"), ("wx_fast", "快")]:
        _insert_game(db_mod, aid, name, "休闲")
    with db_mod.get_conn() as conn:
        conn.execute(
            "INSERT INTO rankings (date, platform, chart, appid, rank) VALUES (?,?,?,?,?)",
            ("2026-03-30", "wx", "popularity", "wx_slow", 99),
        )
        conn.execute(
            "INSERT INTO rankings (date, platform, chart, appid, rank) VALUES (?,?,?,?,?)",
            ("2026-03-30", "wx", "popularity", "wx_fast", 1),
        )
    from backend.analyzer import insight_infer

    with db_mod.get_conn() as conn:
        insight_infer.ensure_canonical_gameplay_tags(conn)
        rows, resolved = insight_infer._fetch_candidates(
            conn,
            1,
            True,
            False,
            platform="wx",
            ranking_date="2026-03-30",
        )
    assert resolved == "2026-03-30"
    assert len(rows) == 1
    assert rows[0]["appid"] == "wx_fast"


def test_infer_single_appid_only(tmp_path, monkeypatch):
    db_mod = _setup_db(tmp_path, monkeypatch)
    _insert_game(db_mod, "wx_one", "单机", "益智")
    fake_items = [
        {
            "index": 1,
            "monetization_model": "iaa",
            "mix_note": "广告",
            "evidence_summary": ["益智"],
            "gameplay_slugs": [],
            "virality_hypothesis": "",
            "virality_channels": [],
        }
    ]
    with patch(
        "backend.analyzer.insight_infer._ai_insight_batch",
        return_value=(fake_items, None),
    ) as mock_llm:
        from backend.analyzer.insight_infer import run_insight_infer_batch

        out = run_insight_infer_batch(
            appid="wx_one",
            limit=999,
            batch_size=12,
            only_missing=False,
            force=True,
        )
    mock_llm.assert_called_once()
    called_games = mock_llm.call_args[0][0]
    assert len(called_games) == 1
    assert called_games[0]["appid"] == "wx_one"
    assert out["appid"] == "wx_one"
    assert out["batches"] == 1
    assert out["monetization_updated"] >= 1


def test_validate_parsed_items_empty_array():
    from backend.analyzer.insight_infer import _validate_parsed_items

    err = _validate_parsed_items([], [{"appid": "a"}])
    assert err is not None
    assert "空 JSON 数组" in err


def test_validate_parsed_items_single_game_wrong_count():
    from backend.analyzer.insight_infer import _validate_parsed_items

    err2 = _validate_parsed_items([{"x": 1}, {"y": 2}], [{"appid": "a"}])
    assert err2 and "1 条" in err2


def test_validate_parsed_items_batch_count_mismatch():
    from backend.analyzer.insight_infer import _validate_parsed_items

    err = _validate_parsed_items([{"i": 1}], [{"a": 1}, {"b": 2}])
    assert err and "数量不一致" in err


def test_message_content_to_str_list():
    from backend.analyzer.insight_infer import _message_content_to_str

    s = _message_content_to_str(
        [{"type": "text", "text": "hello"}, {"type": "text", "text": {"value": " world"}}]
    )
    assert "hello" in s and "world" in s


def _install_fake_openai(monkeypatch, resp_obj):
    """Avoid patch('openai.OpenAI') when openai is not installed for test collection."""

    class _OpenAI:
        def __init__(self, *a, **k):
            self.chat = MagicMock()
            self.chat.completions.create = MagicMock(return_value=resp_obj)

    mod = types.ModuleType("openai")
    mod.OpenAI = _OpenAI
    monkeypatch.setitem(sys.modules, "openai", mod)


def test_infer_single_appid_llm_returns_empty_array(tmp_path, monkeypatch):
    """[] from model must surface explicit error, not generic empty LLM response."""
    db_mod = _setup_db(tmp_path, monkeypatch)
    _insert_game(db_mod, "wx_empty", "测", "休闲")

    class _Msg:
        content = "[]"

    class _Choice:
        finish_reason = "stop"
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    _install_fake_openai(monkeypatch, _Resp())

    def _fake_create(**kwargs):
        return _Resp()

    monkeypatch.setattr(
        "backend.analyzer.insight_infer.chat_completions_create",
        _fake_create,
    )
    from backend.analyzer.insight_infer import run_insight_infer_batch

    out = run_insight_infer_batch(
        appid="wx_empty",
        batch_size=1,
        only_missing=False,
        force=True,
    )
    assert out["batches"] == 0
    assert out["errors"]
    assert any("空 JSON 数组" in e for e in out["errors"])


def test_resolve_gameplay_slug_chinese_case_alias(tmp_path, monkeypatch):
    db_mod = _setup_db(tmp_path, monkeypatch)
    from backend.analyzer import insight_infer

    with db_mod.get_conn() as conn:
        insight_infer.ensure_canonical_gameplay_tags(conn)
        slug_to_id: dict[str, int] = {}
        for slug, _ in insight_infer.CANONICAL_GAMEPLAY_TAGS:
            r = conn.execute(
                "SELECT id FROM gameplay_tags WHERE slug = ?", (slug,)
            ).fetchone()
            if r:
                slug_to_id[slug] = int(r["id"])
        name_to_slug = insight_infer._build_name_to_slug()

    assert insight_infer._resolve_gameplay_slug("塔防策略", slug_to_id, name_to_slug) == "td"
    assert insight_infer._resolve_gameplay_slug("TD", slug_to_id, name_to_slug) == "td"
    assert insight_infer._resolve_gameplay_slug("塔防", slug_to_id, name_to_slug) == "td"
    assert insight_infer._resolve_gameplay_slug("tower-defense", slug_to_id, name_to_slug) is None
    assert insight_infer._resolve_gameplay_slug("pvp_arena", slug_to_id, name_to_slug) == "pvp_arena"


def test_apply_batch_resolves_mixed_gameplay_slugs(tmp_path, monkeypatch):
    """Chinese canonical name + case slug + alias + duplicate raw -> deduped inserts."""
    db_mod = _setup_db(tmp_path, monkeypatch)
    _insert_game(db_mod, "wx_gp_mix", "混测", "休闲")
    fake_items = [
        {
            "index": 1,
            "monetization_model": "iaa",
            "mix_note": "x",
            "evidence_summary": ["a"],
            "gameplay_slugs": ["塔防策略", "TD", "塔防", "merge", "not_a_real_slug"],
            "virality_hypothesis": "",
            "virality_channels": [],
        }
    ]
    with patch(
        "backend.analyzer.insight_infer._ai_insight_batch",
        return_value=(fake_items, None),
    ):
        from backend.analyzer.insight_infer import run_insight_infer_batch

        out = run_insight_infer_batch(
            appid="wx_gp_mix",
            batch_size=1,
            only_missing=False,
            force=True,
        )
    assert out["gameplay_links_added"] == 2
    with db_mod.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT gt.slug FROM game_gameplay_tags ggt
            JOIN gameplay_tags gt ON gt.id = ggt.tag_id
            WHERE ggt.appid = ? ORDER BY gt.slug
            """,
            ("wx_gp_mix",),
        ).fetchall()
    slugs = {r["slug"] for r in rows}
    assert slugs == {"merge", "td"}


def test_infer_single_appid_llm_returns_single_object_not_array(tmp_path, monkeypatch):
    """Model returns one JSON object; we wrap as list of one."""
    db_mod = _setup_db(tmp_path, monkeypatch)
    _insert_game(db_mod, "wx_obj", "测", "休闲")

    payload = (
        '{"index":1,"monetization_model":"iaa","mix_note":"x",'
        '"evidence_summary":["a"],"gameplay_slugs":[],"virality_hypothesis":"",'
        '"virality_channels":[]}'
    )

    class _Msg:
        content = payload

    class _Choice:
        finish_reason = "stop"
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    _install_fake_openai(monkeypatch, _Resp())

    def _fake_create(**kwargs):
        return _Resp()

    monkeypatch.setattr(
        "backend.analyzer.insight_infer.chat_completions_create",
        _fake_create,
    )
    from backend.analyzer.insight_infer import run_insight_infer_batch

    out = run_insight_infer_batch(
        appid="wx_obj",
        batch_size=1,
        only_missing=False,
        force=True,
    )
    assert out["batches"] == 1
    assert out["monetization_updated"] >= 1


def test_top50_union_excludes_rank_gt50(tmp_path, monkeypatch):
    db_mod = _setup_db(tmp_path, monkeypatch)
    _insert_game(db_mod, "wx_in", "in", "x")
    _insert_game(db_mod, "wx_out", "out", "x")
    from backend.analyzer import insight_infer

    with db_mod.get_conn() as conn:
        for chart in insight_infer.db_charts_for_platform("wx"):
            conn.execute(
                """
                INSERT INTO rankings (date, platform, chart, rank, appid)
                VALUES ('2026-04-01', 'wx', ?, 5, 'wx_in')
                """,
                (chart,),
            )
            conn.execute(
                """
                INSERT INTO rankings (date, platform, chart, rank, appid)
                VALUES ('2026-04-01', 'wx', ?, 51, 'wx_out')
                """,
                (chart,),
            )
        rows = insight_infer._fetch_top50_union_candidates(
            conn, "wx", "2026-04-01", insight_gap_only=False, limit=200
        )
    appids = {r["appid"] for r in rows}
    assert "wx_in" in appids
    assert "wx_out" not in appids


def test_top50_insight_gap_filters_complete(tmp_path, monkeypatch):
    db_mod = _setup_db(tmp_path, monkeypatch)
    _insert_game(db_mod, "wx_gap", "g", "x")
    _insert_game(db_mod, "wx_full", "f", "x")
    from backend.analyzer import insight_infer

    with db_mod.get_conn() as conn:
        insight_infer.ensure_canonical_gameplay_tags(conn)
        tid = conn.execute(
            "SELECT id FROM gameplay_tags WHERE slug = ?",
            ("td",),
        ).fetchone()[0]
        for chart in insight_infer.db_charts_for_platform("wx"):
            for aid, rk in [("wx_gap", 8), ("wx_full", 9)]:
                conn.execute(
                    """
                    INSERT INTO rankings (date, platform, chart, rank, appid)
                    VALUES ('2026-04-02', 'wx', ?, ?, ?)
                    """,
                    (chart, rk, aid),
                )
        conn.execute(
            """
            INSERT INTO game_monetization
              (appid, monetization_model, mix_note, confidence, source, updated_by, updated_at)
            VALUES ('wx_full', 'iaa', 'n', 0.5, 'ai', 't', datetime('now'))
            """,
        )
        conn.execute(
            """
            INSERT INTO game_gameplay_tags (appid, tag_id, role, source, updated_by, updated_at)
            VALUES ('wx_full', ?, 'primary', 'ai', 't', datetime('now'))
            """,
            (tid,),
        )
        conn.execute(
            """
            INSERT INTO virality_assumptions
              (appid, channels, hypothesis, evidence, confidence, source, updated_by, updated_at)
            VALUES ('wx_full', '[]', 'h', NULL, 0.5, 'ai', 't', datetime('now'))
            """,
        )
        rows = insight_infer._fetch_top50_union_candidates(
            conn, "wx", "2026-04-02", insight_gap_only=True, limit=200
        )
    assert [r["appid"] for r in rows] == ["wx_gap"]


def test_run_insight_infer_top50_mode(tmp_path, monkeypatch):
    db_mod = _setup_db(tmp_path, monkeypatch)
    _insert_game(db_mod, "wx_t50", "t", "x")
    from backend.analyzer import insight_infer

    with db_mod.get_conn() as conn:
        for chart in insight_infer.db_charts_for_platform("wx"):
            conn.execute(
                """
                INSERT INTO rankings (date, platform, chart, rank, appid)
                VALUES ('2026-04-03', 'wx', ?, 3, 'wx_t50')
                """,
                (chart,),
            )
    fake_items = [
        {
            "index": 1,
            "monetization_model": "iaa",
            "mix_note": "x",
            "evidence_summary": ["a"],
            "gameplay_slugs": ["td"],
            "virality_hypothesis": "share",
            "virality_channels": ["wechat_share"],
        }
    ]
    with patch(
        "backend.analyzer.insight_infer._ai_insight_batch",
        return_value=(fake_items, None),
    ):
        out = insight_infer.run_insight_infer_batch(
            limit=200,
            batch_size=1,
            only_missing=True,
            force=False,
            platform="wx",
            ranking_date="2026-04-03",
            top50_charts=True,
            insight_gap_only=True,
        )
    assert out["top50_charts"] is True
    assert out["candidates"] == 1
    assert out["batches"] == 1


def test_api_game_insight_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "gflags.db"))
    db.init_db()
    _insert_game(db, "wx_tail", "tail", "x")
    _insert_game(db, "wx_top_ok", "top", "x")
    from backend.analyzer import insight_infer

    with db.get_conn() as conn:
        insight_infer.ensure_canonical_gameplay_tags(conn)
        tid = conn.execute(
            "SELECT id FROM gameplay_tags WHERE slug = ?",
            ("merge",),
        ).fetchone()[0]
        for aid, rk in [("wx_tail", 60), ("wx_top_ok", 4)]:
            conn.execute(
                """
                INSERT INTO rankings (date, platform, chart, rank, appid)
                VALUES ('2026-04-04', 'wx', 'popularity', ?, ?)
                """,
                (rk, aid),
            )
        conn.execute(
            """
            INSERT INTO game_monetization
              (appid, monetization_model, mix_note, confidence, source, updated_by, updated_at)
            VALUES ('wx_top_ok', 'iaa', 'n', 0.5, 'ai', 't', datetime('now'))
            """,
        )
        conn.execute(
            """
            INSERT INTO game_gameplay_tags (appid, tag_id, role, source, updated_by, updated_at)
            VALUES ('wx_top_ok', ?, 'primary', 'ai', 't', datetime('now'))
            """,
            (tid,),
        )
        conn.execute(
            """
            INSERT INTO virality_assumptions
              (appid, channels, hypothesis, evidence, confidence, source, updated_by, updated_at)
            VALUES ('wx_top_ok', '[]', 'h', NULL, 0.5, 'ai', 't', datetime('now'))
            """,
        )

    with patch("collector.scheduler.start_scheduler"), patch(
        "collector.scheduler.shutdown_scheduler"
    ):
        from backend.main import app
        from fastapi.testclient import TestClient

        with TestClient(app, raise_server_exceptions=True) as c:
            r_tail = c.get(
                "/api/game/wx_tail?platform=wx&date=2026-04-04"
                "&include=gameplay,monetization,virality"
            )
            jt = r_tail.json()
            assert jt["in_snapshot_top50_union"] is False
            assert jt["show_ai_insight_button"] is True

            r_top = c.get(
                "/api/game/wx_top_ok?platform=wx&date=2026-04-04"
                "&include=gameplay,monetization,virality"
            )
            jp = r_top.json()
            assert jp["in_snapshot_top50_union"] is True
            assert jp["insight_surfaces_complete"] is True
            assert jp["show_ai_insight_button"] is False
