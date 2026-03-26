import json

import httpx
import pytest


@pytest.fixture(autouse=True)
def _yyb_no_sleep(monkeypatch):
    monkeypatch.setattr("collector.yyb.time.sleep", lambda *_a, **_k: None)


class TestBuildRequestBody:
    def test_structure(self):
        from collector.yyb import build_request_body

        body = build_request_body(
            layout="wechat-popularrank-game-list",
            exp_scene_ids="",
            guid="test-guid",
            offset=0,
            size=10,
            exposed_app_ids=[],
            batch_num=1,
        )
        assert body["head"]["cmd"] == "dc_pcyyb_official"
        assert body["head"]["authInfo"]["businessId"] == "AuthName"
        assert body["head"]["userInfo"]["guid"] == "test-guid"
        assert body["body"]["layout"] == "wechat-popularrank-game-list"
        assert body["body"]["offset"] == 0
        assert body["body"]["size"] == 10
        assert body["body"]["listI"]["offset"]["repInt"] == [1]

    def test_bestseller_exp_scene_ids(self):
        from collector.yyb import build_request_body

        body = build_request_body(
            layout="wechat-bestsellrank-game-list",
            exp_scene_ids="92250",
            guid="g",
            offset=10,
            size=10,
            exposed_app_ids=["111", "222"],
            batch_num=2,
        )
        assert body["head"]["expSceneIds"] == "92250"
        assert body["body"]["listI"]["exposed_appids"]["repInt"] == [["111", "222"]]
        assert body["body"]["listI"]["offset"]["repInt"] == [2]

    def test_empty_exp_scene_ids(self):
        from collector.yyb import build_request_body

        body = build_request_body("layout", "", "g", 0, 10, [], 1)
        assert body["head"]["expSceneIds"] == ""


class TestParseYybItems:
    def _make_item(self, pkg_name, app_id, name, screenorder, **kwargs):
        return {
            "pkg_name": pkg_name,
            "app_id": app_id,
            "name": name,
            "report_info": {"screenorder": screenorder},
            "icon": kwargs.get("icon"),
            "developer": kwargs.get("developer"),
            "tags": kwargs.get("tags"),
        }

    def test_basic_parse(self):
        from collector.yyb import parse_yyb_items

        items = [
            self._make_item("wx123", "111", "Game A", 1, icon="http://x.png", developer="Dev", tags="休闲,策略"),
            self._make_item("wx456", "222", "Game B", 2),
        ]
        result = parse_yyb_items(items)
        assert len(result) == 2
        assert result[0]["rank"] == 1
        assert result[0]["appid"] == "wx123"
        assert result[0]["yyb_app_id"] == "111"
        assert result[0]["name"] == "Game A"
        assert result[0]["icon_url"] == "http://x.png"
        assert result[0]["developer"] == "Dev"
        tags = json.loads(result[0]["tags"])
        assert tags == ["休闲", "策略"]

    def test_missing_pkg_name_skipped(self):
        from collector.yyb import parse_yyb_items

        items = [{"app_id": "111", "name": "X", "report_info": {"screenorder": 1}}]
        assert parse_yyb_items(items) == []

    def test_missing_name_skipped(self):
        from collector.yyb import parse_yyb_items

        items = [{"pkg_name": "wx999", "app_id": "111", "report_info": {"screenorder": 1}}]
        assert parse_yyb_items(items) == []

    def test_fallback_rank_on_missing_screenorder(self):
        from collector.yyb import parse_yyb_items

        items = [
            {"pkg_name": "wx1", "app_id": "1", "name": "G1", "report_info": {}},
            {"pkg_name": "wx2", "app_id": "2", "name": "G2", "report_info": {}},
        ]
        result = parse_yyb_items(items)
        assert result[0]["rank"] == 1
        assert result[1]["rank"] == 2

    def test_tags_none_when_empty(self):
        from collector.yyb import parse_yyb_items

        items = [
            {"pkg_name": "wx1", "app_id": "1", "name": "G", "report_info": {"screenorder": 5}, "tags": ""}
        ]
        result = parse_yyb_items(items)
        assert result[0]["tags"] is None


class TestIsBlocked:
    def test_403_is_blocked(self):
        from collector.yyb import _is_blocked

        resp = httpx.Response(status_code=403, text="{}")
        assert _is_blocked(resp, None) is True

    def test_429_is_blocked(self):
        from collector.yyb import _is_blocked

        resp = httpx.Response(status_code=429, text="{}")
        assert _is_blocked(resp, None) is True

    def test_200_with_items_not_blocked(self):
        from collector.yyb import _is_blocked

        assert _is_blocked(None, [{"name": "G"}]) is False

    def test_empty_items_not_http_blocked(self):
        from collector.yyb import _is_blocked

        assert _is_blocked(None, []) is False


class TestFetchYybChart:
    def _chart_cfg(self):
        return {"chart_id": "popular", "layout": "wechat-popularrank-game-list", "exp_scene_ids": ""}

    def _make_items(self, count, start_rank=1):
        return [
            {
                "pkg_name": f"wx{start_rank + i:04d}",
                "app_id": str(start_rank + i),
                "name": f"Game {start_rank + i}",
                "report_info": {"screenorder": start_rank + i},
            }
            for i in range(count)
        ]

    def test_single_page_full(self, monkeypatch):
        from collector import yyb as yyb_mod

        calls = {"n": 0}

        def fake_post(client, body):
            calls["n"] += 1
            if calls["n"] == 1:
                return None, self._make_items(10)
            return None, []

        monkeypatch.setattr(yyb_mod, "_post_with_retry", fake_post)
        monkeypatch.setattr(yyb_mod, "_make_client", lambda use_proxy=False: None)

        result = yyb_mod.fetch_yyb_chart(self._chart_cfg(), "2026-03-25", "test-guid")
        assert len(result) == 10

    def test_multi_page_stops_at_200(self, monkeypatch):
        from collector import yyb as yyb_mod

        calls = {"n": 0}

        def fake_post(client, body):
            calls["n"] += 1
            if calls["n"] > 20:
                return None, []
            return None, self._make_items(10, start_rank=(calls["n"] - 1) * 10 + 1)

        monkeypatch.setattr(yyb_mod, "_post_with_retry", fake_post)
        monkeypatch.setattr(yyb_mod, "_make_client", lambda use_proxy=False: None)

        result = yyb_mod.fetch_yyb_chart(self._chart_cfg(), "2026-03-25", "test-guid")
        assert len(result) == 200

    def test_short_page_breaks(self, monkeypatch):
        from collector import yyb as yyb_mod

        calls = {"n": 0}

        def fake_post(client, body):
            calls["n"] += 1
            if calls["n"] == 1:
                return None, self._make_items(10)
            return None, self._make_items(5, start_rank=11)

        monkeypatch.setattr(yyb_mod, "_post_with_retry", fake_post)
        monkeypatch.setattr(yyb_mod, "_make_client", lambda use_proxy=False: None)

        result = yyb_mod.fetch_yyb_chart(self._chart_cfg(), "2026-03-25", "test-guid")
        assert len(result) == 15

    def test_blocked_3_times_no_proxy_raises(self, monkeypatch):
        from collector import yyb as yyb_mod

        monkeypatch.setattr(yyb_mod.config, "YYB_PROXY_URL", None)
        calls = {"n": 0}

        def fake_post(client, body):
            calls["n"] += 1
            return httpx.Response(status_code=403, text="{}"), None

        monkeypatch.setattr(yyb_mod, "_post_with_retry", fake_post)
        monkeypatch.setattr(yyb_mod, "_make_client", lambda use_proxy=False: None)

        with pytest.raises(RuntimeError, match="blocked"):
            yyb_mod.fetch_yyb_chart(self._chart_cfg(), "2026-03-25", "test-guid")

    def test_blocked_3_times_switches_to_proxy(self, monkeypatch):
        from collector import yyb as yyb_mod

        monkeypatch.setattr(yyb_mod.config, "YYB_PROXY_URL", "http://127.0.0.1:7890")
        proxy_used = {"v": False}
        ok_calls = {"n": 0}

        def fake_make_client(use_proxy=False):
            proxy_used["v"] = use_proxy
            return None

        def fake_post(client, body):
            if not proxy_used["v"]:
                return httpx.Response(status_code=403, text="{}"), None
            ok_calls["n"] += 1
            if ok_calls["n"] == 1:
                return None, self._make_items(10)
            return None, []

        monkeypatch.setattr(yyb_mod, "_post_with_retry", fake_post)
        monkeypatch.setattr(yyb_mod, "_make_client", fake_make_client)

        result = yyb_mod.fetch_yyb_chart(self._chart_cfg(), "2026-03-25", "test-guid")
        assert len(result) == 10
        assert proxy_used["v"] is True

    def test_exposed_ids_accumulate_before_truncation(self, monkeypatch):
        from collector import yyb as yyb_mod

        page_data = {}
        calls = {"n": 0}

        def fake_post(client, body):
            calls["n"] += 1
            page_data[calls["n"]] = body["body"]["listI"]["exposed_appids"]["repInt"][0][:]
            if calls["n"] <= 20:
                return None, self._make_items(10, start_rank=(calls["n"] - 1) * 10 + 1)
            return None, []

        monkeypatch.setattr(yyb_mod, "_post_with_retry", fake_post)
        monkeypatch.setattr(yyb_mod, "_make_client", lambda use_proxy=False: None)

        result = yyb_mod.fetch_yyb_chart(self._chart_cfg(), "2026-03-25", "test-guid")
        assert len(result) == 200
        # 采满 200 后不再发第 21 次请求；第 20 次请求体携带已累计的 190 个 exposed id
        assert len(page_data[20]) == 190
        assert calls["n"] == 20

    def test_global_rank_when_api_repeats_page_local_screenorder(self, monkeypatch):
        """每页 screenorder 均为 1..10 时，仍应得到全局 rank 1..20。"""
        from collector import yyb as yyb_mod

        def item(pkg_suffix, screenorder):
            return {
                "pkg_name": f"wx{pkg_suffix}",
                "app_id": str(pkg_suffix),
                "name": f"G{pkg_suffix}",
                "report_info": {"screenorder": screenorder},
            }

        calls = {"n": 0}

        def fake_post(client, body):
            calls["n"] += 1
            if calls["n"] == 1:
                return None, [item(i, i) for i in range(1, 11)]
            if calls["n"] == 2:
                return None, [item(10 + i, i) for i in range(1, 11)]
            return None, []

        monkeypatch.setattr(yyb_mod, "_post_with_retry", fake_post)
        monkeypatch.setattr(yyb_mod, "_make_client", lambda use_proxy=False: None)

        result = yyb_mod.fetch_yyb_chart(self._chart_cfg(), "2026-03-25", "test-guid")
        assert [g["rank"] for g in result] == list(range(1, 21))

    def test_body_offset_stays_zero_multi_page(self, monkeypatch):
        """与 sj.qq.com 一致：各页 body.offset 恒为 0，仅靠 batch_num 翻页。"""
        from collector import yyb as yyb_mod

        offsets = []
        batches = []

        def fake_post(client, body):
            offsets.append(body["body"]["offset"])
            batches.append(body["body"]["listI"]["offset"]["repInt"][0])
            n = len(offsets)
            if n == 1:
                return None, self._make_items(20, start_rank=1)
            if n == 2:
                # 短页 (< PAGE_SIZE) 触发到底，避免与「整页 10 条」再拉第三页
                return None, self._make_items(5, start_rank=21)
            return None, []

        monkeypatch.setattr(yyb_mod, "_post_with_retry", fake_post)
        monkeypatch.setattr(yyb_mod, "_make_client", lambda use_proxy=False: None)

        result = yyb_mod.fetch_yyb_chart(self._chart_cfg(), "2026-03-25", "test-guid")
        assert offsets == [0, 0]
        assert batches == [1, 2]
        assert len(result) == 25
