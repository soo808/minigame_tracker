"""Gravity first-run scheduling: same-day catch-up after 11:30 when rankings incomplete."""
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

SH = ZoneInfo("Asia/Shanghai")


@pytest.fixture
def noon_shanghai_mar30():
    return datetime(2026, 3, 30, 12, 0, 0, tzinfo=SH)


class TestFirstScheduledRun:
    def test_after_deadline_incomplete_returns_catchup(
        self, monkeypatch, noon_shanghai_mar30
    ):
        from collector import scheduler

        class _DT:
            combine = datetime.combine

            @staticmethod
            def now(tz=None):
                return noon_shanghai_mar30

        monkeypatch.setattr(scheduler, "datetime", _DT)
        monkeypatch.setattr(scheduler, "_gravity_charts_complete_for_day", lambda _d: False)

        first_at, catchup = scheduler._first_scheduled_run()
        assert catchup is True
        assert first_at == noon_shanghai_mar30 + timedelta(seconds=15)

    def test_after_deadline_complete_returns_tomorrow_window(
        self, monkeypatch, noon_shanghai_mar30
    ):
        from collector import scheduler

        class _DT:
            combine = datetime.combine

            @staticmethod
            def now(tz=None):
                return noon_shanghai_mar30

        monkeypatch.setattr(scheduler, "datetime", _DT)
        monkeypatch.setattr(scheduler, "_gravity_charts_complete_for_day", lambda _d: True)

        with patch.object(scheduler.random, "randint", return_value=0):
            first_at, catchup = scheduler._first_scheduled_run()
        assert catchup is False
        assert first_at.date() == noon_shanghai_mar30.date() + timedelta(days=1)
        assert first_at.hour == 11
        assert first_at.minute == 0


def test_collect_all_charts_respects_deadline_by_default(monkeypatch):
    from collector import scheduler

    noon = datetime(2026, 3, 30, 12, 0, 0, tzinfo=SH)

    class _DT:
        combine = datetime.combine

        @staticmethod
        def now(tz=None):
            return noon

    monkeypatch.setattr(scheduler, "datetime", _DT)
    monkeypatch.setattr(scheduler, "_today_str", lambda: "2026-03-30")
    monkeypatch.setattr(scheduler, "_post_collect_enrichment", lambda: None)
    monkeypatch.setattr(scheduler, "_sleep_between_charts", lambda: None)

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(scheduler.httpx, "Client", lambda **kw: _Client())

    applied = []

    def fake_apply(*args, **kwargs):
        applied.append(args)

    monkeypatch.setattr(scheduler, "apply_chart_payload", fake_apply)

    scheduler.collect_all_charts()

    assert len(applied) == 6
    for a in applied:
        assert a[3] == []
        assert a[4] == "failed"
        assert a[5] == "deadline_1130"


def test_collect_all_charts_ignore_deadline_fetches(monkeypatch):
    from collector import scheduler

    noon = datetime(2026, 3, 30, 12, 0, 0, tzinfo=SH)

    class _DT:
        combine = datetime.combine

        @staticmethod
        def now(tz=None):
            return noon

    monkeypatch.setattr(scheduler, "datetime", _DT)
    monkeypatch.setattr(scheduler, "_today_str", lambda: "2026-03-30")
    monkeypatch.setattr(scheduler, "_sleep_between_charts", lambda: None)

    calls = []

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_client(**kwargs):
        return _Client()

    def fake_fetch(client, rank_genre, rank_type, day):
        calls.append((rank_genre, rank_type))
        return []

    def fake_to_games(raw):
        return [{"rank": 1, "appid": "t1", "name": "N"}] * 95

    monkeypatch.setattr(scheduler.httpx, "Client", fake_client)
    monkeypatch.setattr(scheduler, "fetch_chart", fake_fetch)
    monkeypatch.setattr(scheduler, "gravity_items_to_games", fake_to_games)

    applied = []

    def fake_apply(*args, **kwargs):
        applied.append(args)

    monkeypatch.setattr(scheduler, "apply_chart_payload", fake_apply)
    monkeypatch.setattr(scheduler, "_post_collect_enrichment", lambda: None)

    scheduler.collect_all_charts(ignore_collection_deadline=True)

    assert len(calls) == 6
    assert len(applied) == 6
    assert all(a[4] in ("ok", "partial") for a in applied)
