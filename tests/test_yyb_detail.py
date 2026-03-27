import json
from unittest.mock import MagicMock, patch

import pytest

from backend import db


def _make_next_data(desc: str) -> str:
    payload = {
        "props": {
            "pageProps": {
                "appDetail": {"introText": desc},
            }
        }
    }
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'


def test_parse_description_extracts_intro_text():
    from collector.yyb_detail import _parse_description

    html = _make_next_data("这是一款经典传奇类手游，玩法简单刺激。")
    assert _parse_description(html) == "这是一款经典传奇类手游，玩法简单刺激。"


def test_parse_description_returns_none_on_missing():
    from collector.yyb_detail import _parse_description

    assert _parse_description("<html>no next data here</html>") is None


def test_parse_description_truncates_to_500():
    from collector.yyb_detail import _parse_description

    html = _make_next_data("X" * 600)
    result = _parse_description(html)
    assert result is not None and len(result) == 500


def test_fetch_detail_returns_none_on_http_error():
    from collector.yyb_detail import fetch_detail

    with patch("httpx.Client") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
        result = fetch_detail("wxabc123")
    assert result is None


def test_collect_detail_batch_updates_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO games (appid, platform, name, first_seen, updated_at) "
            "VALUES ('wx001', 'yyb', '测试游戏', '2026-03-26', '2026-03-26')"
        )
    from collector import yyb_detail

    with (
        patch.object(yyb_detail, "fetch_detail", return_value="好玩的传奇游戏"),
        patch("collector.yyb_detail.time.sleep", lambda *_: None),
    ):
        result = yyb_detail.collect_detail_batch(ai_fallback=False)
    assert result["updated"] == 1
    with db.get_conn() as conn:
        row = conn.execute("SELECT description FROM games WHERE appid='wx001'").fetchone()
    assert row["description"] == "好玩的传奇游戏"
