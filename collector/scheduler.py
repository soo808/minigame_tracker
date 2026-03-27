"""Gravity: random 11:00–11:20, stop 11:30. YYB: separate job, random 11:00–11:25 (Asia/Shanghai)."""
from __future__ import annotations

import logging
import random
import time
from datetime import date, datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from collector import config
from collector.gravity import fetch_chart, gravity_items_to_games
from collector.yyb import fetch_yyb_chart
from backend.ingest_service import apply_chart_payload
from backend.wx_yyb_fallback import backfill_wx_from_yyb

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


def _yyb_window_bounds(d: date) -> tuple[datetime, datetime]:
    """YYB job trigger: random time in [11:00, 11:25] inclusive."""
    start = datetime.combine(d, dtime(11, 0), tzinfo=TZ)
    end = datetime.combine(d, dtime(11, 25), tzinfo=TZ)
    return start, end


def _yyb_wall_clock_cutoff() -> datetime:
    """For today's date only: stop new YYB fetches when clock >= 11:26 (after 11:25 window)."""
    d = datetime.now(TZ).date()
    return datetime.combine(d, dtime(11, 26), tzinfo=TZ)


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

    _post_collect_enrichment()


def _post_collect_enrichment() -> None:
    try:
        from collector.yyb_detail import collect_detail_batch

        logger.info("Post-collect: detail enrichment...")
        collect_detail_batch(ai_fallback=True)
    except Exception:
        logger.exception("post-collect detail enrichment failed")
    try:
        from backend.analyzer.classify import classify_games_batch

        logger.info("Post-collect: genre classification...")
        classify_games_batch(force=False)
    except Exception:
        logger.exception("post-collect classify failed")


def collect_yyb_charts(date: str, *, force: bool = False) -> None:
    """
    YYB 三榜；榜间 3~10s。
    仅当 date 为上海「当日」且未 force 时应用 11:25 窗口：时钟 >= 11:26 则跳过（与引力任务无关）。
    调度器始终 force=False；手动 /api/collect/yyb?force=1 可越过窗口补采当日。
    历史日期补采不受窗口限制。
    """
    order = config.YYB_CHARTS[:]
    random.shuffle(order)
    enforce_window = date == _today_str() and not force

    for chart_cfg in order:
        if enforce_window and datetime.now(TZ) >= _yyb_wall_clock_cutoff():
            logger.error(
                "yyb past 11:25 window; skipping chart=%s date=%s",
                chart_cfg["chart_id"],
                date,
            )
            try:
                apply_chart_payload(
                    date, "yyb", chart_cfg["chart_id"], [], "failed", "deadline_yyb_1125"
                )
            except Exception:
                logger.exception("failed to write yyb deadline snapshot")
            continue

        try:
            games = fetch_yyb_chart(chart_cfg, date, config.YYB_GUID)
            status = "ok" if len(games) >= 180 else "partial"
            apply_chart_payload(date, "yyb", chart_cfg["chart_id"], games, status, None)
            logger.info(
                "yyb collected chart=%s count=%d status=%s",
                chart_cfg["chart_id"],
                len(games),
                status,
            )
        except RuntimeError as e:
            logger.error("yyb blocked/failed chart=%s: %s", chart_cfg["chart_id"], e)
            apply_chart_payload(
                date, "yyb", chart_cfg["chart_id"], [], "failed", str(e)[:200]
            )
        except Exception as e:
            logger.exception("yyb collect error chart=%s: %s", chart_cfg["chart_id"], e)
            apply_chart_payload(
                date, "yyb", chart_cfg["chart_id"], [], "failed", str(e)[:200]
            )

        time.sleep(random.uniform(3.0, 10.0))


def _random_fire_in_window(target_day: date) -> datetime:
    ws, we = _window_bounds(target_day)
    delta_sec = random.randint(0, int((we - ws).total_seconds()))
    return ws + timedelta(seconds=delta_sec)


def _random_yyb_fire_in_window(target_day: date) -> datetime:
    ws, we = _yyb_window_bounds(target_day)
    span = int((we - ws).total_seconds())
    delta_sec = random.randint(0, max(0, span))
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


def _first_scheduled_yyb_run() -> datetime:
    now = datetime.now(TZ)
    d = now.date()
    ws, we = _yyb_window_bounds(d)

    if now > we:
        tmr = d + timedelta(days=1)
        return _random_yyb_fire_in_window(tmr)

    if now < ws:
        return _random_yyb_fire_in_window(d)

    if now <= we:
        latest = max(ws, now)
        span = max(0, int((we - latest).total_seconds()))
        delta_sec = random.randint(0, span) if span > 0 else 0
        return latest + timedelta(seconds=max(delta_sec, 3))

    tmr = d + timedelta(days=1)
    return _random_yyb_fire_in_window(tmr)


def _tomorrow_random_collect() -> datetime:
    tmr = datetime.now(TZ).date() + timedelta(days=1)
    return _random_fire_in_window(tmr)


def _tomorrow_random_yyb_collect() -> datetime:
    tmr = datetime.now(TZ).date() + timedelta(days=1)
    return _random_yyb_fire_in_window(tmr)


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    sched = BackgroundScheduler(timezone=str(TZ))

    def gravity_collect_then_reschedule() -> None:
        collect_all_charts()
        nxt = _tomorrow_random_collect()
        sched.add_job(
            gravity_collect_then_reschedule,
            DateTrigger(run_date=nxt),
            id="daily_collect_gravity",
            replace_existing=True,
        )
        logger.info("next gravity collection scheduled at %s", nxt)

    def yyb_collect_then_reschedule() -> None:
        day = _today_str()
        try:
            collect_yyb_charts(day)
        except Exception:
            logger.exception("YYB collect_yyb_charts failed date=%s", day)
        try:
            backfill_wx_from_yyb(day)
        except Exception:
            logger.exception("wx YYB backfill failed date=%s", day)
        _post_collect_enrichment()
        nxt = _tomorrow_random_yyb_collect()
        sched.add_job(
            yyb_collect_then_reschedule,
            DateTrigger(run_date=nxt),
            id="daily_collect_yyb",
            replace_existing=True,
        )
        logger.info("next yyb collection scheduled at %s", nxt)

    first_g = _first_scheduled_run()
    first_y = _first_scheduled_yyb_run()
    sched.add_job(
        gravity_collect_then_reschedule,
        DateTrigger(run_date=first_g),
        id="daily_collect_gravity",
        replace_existing=True,
    )
    sched.add_job(
        yyb_collect_then_reschedule,
        DateTrigger(run_date=first_y),
        id="daily_collect_yyb",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    logger.info(
        "scheduler started; first gravity at %s, first yyb at %s (Asia/Shanghai)",
        first_g,
        first_y,
    )
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
