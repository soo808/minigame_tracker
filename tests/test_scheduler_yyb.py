from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture(autouse=True)
def _no_yyb_sleep(monkeypatch):
    monkeypatch.setattr("collector.scheduler.time.sleep", lambda *_a, **_k: None)


class TestCollectYybCharts:
    def test_collect_yyb_charts_calls_all_three(self, monkeypatch):
        from collector import config
        from collector import scheduler

        called = []

        def fake_fetch(chart_cfg, date, guid):
            called.append(chart_cfg["chart_id"])
            return [{"rank": 1, "appid": "wx001", "name": "G"}] * 200

        def fake_apply(date, platform, db_chart, games, status, note):
            pass

        monkeypatch.setattr(scheduler, "fetch_yyb_chart", fake_fetch)
        monkeypatch.setattr(scheduler, "apply_chart_payload", fake_apply)
        monkeypatch.setattr(config, "YYB_GUID", "test-guid")

        scheduler.collect_yyb_charts("2026-03-25")
        assert set(called) == {"popular", "bestseller", "new_game"}

    def test_collect_yyb_charts_writes_ok_status(self, monkeypatch):
        from collector import config
        from collector import scheduler

        statuses = []

        def fake_fetch(chart_cfg, date, guid):
            return [{"rank": i + 1, "appid": f"wx{i:04d}", "name": f"G{i}"} for i in range(200)]

        def fake_apply(date, platform, db_chart, games, status, note):
            statuses.append(status)

        monkeypatch.setattr(scheduler, "fetch_yyb_chart", fake_fetch)
        monkeypatch.setattr(scheduler, "apply_chart_payload", fake_apply)
        monkeypatch.setattr(config, "YYB_GUID", "test-guid")

        scheduler.collect_yyb_charts("2026-03-25")
        assert all(s == "ok" for s in statuses)

    def test_collect_yyb_charts_partial_when_fewer_than_180(self, monkeypatch):
        from collector import config
        from collector import scheduler

        statuses = []

        def fake_fetch(chart_cfg, date, guid):
            return [{"rank": i + 1, "appid": f"wx{i:04d}", "name": f"G{i}"} for i in range(100)]

        def fake_apply(date, platform, db_chart, games, status, note):
            statuses.append(status)

        monkeypatch.setattr(scheduler, "fetch_yyb_chart", fake_fetch)
        monkeypatch.setattr(scheduler, "apply_chart_payload", fake_apply)
        monkeypatch.setattr(config, "YYB_GUID", "test-guid")

        scheduler.collect_yyb_charts("2026-03-25")
        assert all(s == "partial" for s in statuses)

    def test_past_yyb_window_skips_when_collecting_today(self, monkeypatch):
        """当日采集且已过 11:25 窗口时：不写 fetch，只记 deadline_yyb_1125。"""
        from collector import config
        from collector import scheduler

        called_fetch = []
        applied = []

        def fake_fetch(chart_cfg, date, guid):
            called_fetch.append(chart_cfg["chart_id"])
            return []

        def fake_apply(date, platform, db_chart, games, status, note):
            applied.append((db_chart, status, note))

        monkeypatch.setattr(scheduler, "fetch_yyb_chart", fake_fetch)
        monkeypatch.setattr(scheduler, "apply_chart_payload", fake_apply)
        monkeypatch.setattr(config, "YYB_GUID", "test-guid")
        monkeypatch.setattr(scheduler, "_today_str", lambda: "2026-03-25")
        monkeypatch.setattr(
            scheduler,
            "_yyb_wall_clock_cutoff",
            lambda: datetime(2000, 1, 1, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        scheduler.collect_yyb_charts("2026-03-25")
        assert called_fetch == []
        assert all(status == "failed" for _, status, _ in applied)
        assert all(note == "deadline_yyb_1125" for _, _, note in applied)

    def test_force_bypasses_yyb_window_for_today(self, monkeypatch):
        """force=True 时当日已过窗口仍拉取三榜。"""
        from collector import config
        from collector import scheduler

        called_fetch = []

        def fake_fetch(chart_cfg, date, guid):
            called_fetch.append(chart_cfg["chart_id"])
            return [{"rank": 1, "appid": "wx001", "name": "G"}] * 200

        def fake_apply(date, platform, db_chart, games, status, note):
            pass

        monkeypatch.setattr(scheduler, "fetch_yyb_chart", fake_fetch)
        monkeypatch.setattr(scheduler, "apply_chart_payload", fake_apply)
        monkeypatch.setattr(config, "YYB_GUID", "test-guid")
        monkeypatch.setattr(scheduler, "_today_str", lambda: "2026-03-25")
        monkeypatch.setattr(
            scheduler,
            "_yyb_wall_clock_cutoff",
            lambda: datetime(2000, 1, 1, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        scheduler.collect_yyb_charts("2026-03-25", force=True)
        assert set(called_fetch) == {"popular", "bestseller", "new_game"}

    def test_today_with_window_open_still_fetches(self, monkeypatch):
        """当日但截止未到时仍请求三榜。"""
        from collector import config
        from collector import scheduler

        called_fetch = []

        def fake_fetch(chart_cfg, date, guid):
            called_fetch.append(chart_cfg["chart_id"])
            return [{"rank": 1, "appid": "wx001", "name": "G"}]

        def fake_apply(date, platform, db_chart, games, status, note):
            pass

        monkeypatch.setattr(scheduler, "fetch_yyb_chart", fake_fetch)
        monkeypatch.setattr(scheduler, "apply_chart_payload", fake_apply)
        monkeypatch.setattr(config, "YYB_GUID", "test-guid")
        monkeypatch.setattr(scheduler, "_today_str", lambda: "2026-03-25")
        monkeypatch.setattr(
            scheduler,
            "_yyb_wall_clock_cutoff",
            lambda: datetime(2099, 12, 31, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        scheduler.collect_yyb_charts("2026-03-25")
        assert set(called_fetch) == {"popular", "bestseller", "new_game"}
