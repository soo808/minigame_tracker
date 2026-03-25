"""Daily Gravity collection: random 11:00–11:20, hard stop 11:30 (Asia/Shanghai)."""
from __future__ import annotations

import logging
import random
import time
from datetime import date, datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from collector.gravity import fetch_chart, gravity_items_to_games
from backend.ingest_service import apply_chart_payload

logger = logging.getLogger(__name__)
TZ = ZoneInfo("Asia/Shanghai")

CHART_JOBS: list[tuple[str, str, str, str]] = [
    ("wx_minigame", "popularity", "wx", "popularity"),
    ("wx_minigame", "bestseller", "wx", "bestseller"),
    ("wx_minigame", "most_played", "wx", "most_played"),
    ("dy_minigame", "popularity", "dy", "popularity"),
    ("dy_minigame", "bestseller", "dy", "bestseller"),
    ("dy_minigame", "fresh_game", "dy", "fresh_game"),
]


def _today_str() -> str:
    return datetime.now(TZ).date().strftime("%Y-%m-%d")


def _deadline_today() -> datetime:
    d = datetime.now(TZ).date()
    return datetime.combine(d, dtime(11, 30), tzinfo=TZ)


def _window_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, dtime(11, 0), tzinfo=TZ)
    end = datetime.combine(d, dtime(11, 20), tzinfo=TZ)
    return start, end


def _sleep_between_charts() -> None:
    now = datetime.now(TZ)
    remaining = max(0.0, (_deadline_today() - now).total_seconds())
    if remaining < 90:
        time.sleep(random.uniform(1.0, 2.5))
    else:
        time.sleep(random.uniform(2.0, 8.0))


def collect_all_charts() -> None:
    day = _today_str()
    order = CHART_JOBS[:]
    random.shuffle(order)

    with httpx.Client(follow_redirects=True) as client:
        for rank_genre, rank_type, platform, db_chart in order:
            now = datetime.now(TZ)
            if now >= _deadline_today():
                logger.error(
                    "collection deadline 11:30 reached; skipping %s %s (%s)",
                    platform,
                    db_chart,
                    day,
                )
                try:
                    apply_chart_payload(
                        day,
                        platform,
                        db_chart,
                        [],
                        "failed",
                        "deadline_1130",
                    )
                except Exception:
                    logger.exception("failed to write deadline snapshot")
                continue

            try:
                raw = fetch_chart(client, rank_genre, rank_type, day)
                games = gravity_items_to_games(raw)
                status = "ok" if len(games) >= 90 else "partial"
                apply_chart_payload(day, platform, db_chart, games, status, None)
                logger.info(
                    "collected %s %s count=%s status=%s",
                    platform,
                    db_chart,
                    len(games),
                    status,
                )
            except httpx.HTTPStatusError as e:
                logger.error(
                    "HTTP %s collecting %s %s — JWT may be expired",
                    e.response.status_code,
                    platform,
                    db_chart,
                )
                try:
                    apply_chart_payload(
                        day,
                        platform,
                        db_chart,
                        [],
                        "failed",
                        f"http_{e.response.status_code}",
                    )
                except Exception:
                    logger.exception("snapshot after HTTP error")
            except Exception as e:
                logger.exception("collect failed %s %s: %s", platform, db_chart, e)
                try:
                    apply_chart_payload(
                        day,
                        platform,
                        db_chart,
                        [],
                        "failed",
                        str(e)[:200],
                    )
                except Exception:
                    logger.exception("snapshot after error")

            _sleep_between_charts()


def _random_fire_in_window(target_day: date) -> datetime:
    ws, we = _window_bounds(target_day)
    delta_sec = random.randint(0, int((we - ws).total_seconds()))
    return ws + timedelta(seconds=delta_sec)


def _first_scheduled_run() -> datetime:
    now = datetime.now(TZ)
    d = now.date()
    ws, we = _window_bounds(d)
    deadline = datetime.combine(d, dtime(11, 30), tzinfo=TZ)

    if now > deadline:
        tmr = d + timedelta(days=1)
        return _random_fire_in_window(tmr)

    if now < ws:
        return _random_fire_in_window(d)

    if now <= we:
        latest = max(ws, now)
        span = max(0, int((we - latest).total_seconds()))
        delta_sec = random.randint(0, span) if span > 0 else 0
        return latest + timedelta(seconds=max(delta_sec, 3))

    if now < deadline:
        return now + timedelta(seconds=5)

    tmr = d + timedelta(days=1)
    return _random_fire_in_window(tmr)


def _tomorrow_random_collect() -> datetime:
    tmr = datetime.now(TZ).date() + timedelta(days=1)
    return _random_fire_in_window(tmr)


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    sched = BackgroundScheduler(timezone=str(TZ))

    def collect_then_reschedule() -> None:
        collect_all_charts()
        nxt = _tomorrow_random_collect()
        sched.add_job(
            collect_then_reschedule,
            DateTrigger(run_date=nxt),
            id="daily_collect",
            replace_existing=True,
        )
        logger.info("next collection scheduled at %s", nxt)

    first = _first_scheduled_run()
    sched.add_job(
        collect_then_reschedule,
        DateTrigger(run_date=first),
        id="daily_collect",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    logger.info("scheduler started; first collect at %s", first)
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
