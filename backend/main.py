"""FastAPI app: REST API + optional static frontend."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import date as date_cls
from datetime import timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend import db
from backend import media_cache
from backend.analyzer import trends
from backend.analyzer.classify import classify_games_batch
from backend.ingest_service import apply_chart_payload, map_ingest_chart
from backend.models import IngestBody
from collector.scheduler import collect_yyb_charts, shutdown_scheduler, start_scheduler
from collector.yyb_detail import collect_detail_batch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
FRONT_DIST = ROOT / "frontend" / "dist"


class MinigameApiPrefixMiddleware(BaseHTTPMiddleware):
    """Map /minigame-tracker/api/* → /api/* so SPA (base /minigame-tracker/) hits real routes."""

    async def dispatch(self, request: Request, call_next):
        path = request.scope.get("path", "")
        if path.startswith("/minigame-tracker/api"):
            rest = path[len("/minigame-tracker/api") :]
            if not rest.startswith("/"):
                rest = "/" + rest if rest else ""
            request.scope["path"] = "/api" + rest
            request.scope["raw_path"] = request.scope["path"].encode("utf-8")
        return await call_next(request)


def _charts_for_api(platform: str) -> list[tuple[str, str]]:
    if platform == "wx":
        return [
            ("renqi", "popularity"),
            ("changxiao", "bestseller"),
            ("changwan", "most_played"),
        ]
    if platform == "yyb":
        return [
            ("popular", "popular"),
            ("bestseller", "bestseller"),
            ("new_game", "new_game"),
        ]
    return [
        ("renqi", "popularity"),
        ("changxiao", "bestseller"),
        ("xinyou", "fresh_game"),
    ]


def _latest_date(conn, platform: str | None = None) -> str | None:
    if platform:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM rankings WHERE platform = ?",
            (platform,),
        ).fetchone()
    else:
        row = conn.execute("SELECT MAX(date) AS d FROM rankings").fetchone()
    return row["d"] if row and row["d"] else None


def _parse_tags(raw: str | None) -> list | None:
    if not raw:
        return None
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else [raw]
    except json.JSONDecodeError:
        return [raw]


def _tags_split(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if t]
    except (ValueError, TypeError, json.JSONDecodeError):
        pass
    return [t.strip() for t in raw.split(",") if t.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="Minigame Tracker", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(MinigameApiPrefixMiddleware)


@app.get("/api/dates")
def api_dates(platform: str | None = None):
    with db.get_conn() as conn:
        if platform:
            rows = conn.execute(
                "SELECT DISTINCT date FROM rankings WHERE platform = ? ORDER BY date DESC",
                (platform,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT date FROM rankings ORDER BY date DESC"
            ).fetchall()
    return {"dates": [r["date"] for r in rows]}


@app.get("/api/media/{sha256_hex}")
def api_serve_media(sha256_hex: str):
    h = sha256_hex.lower().strip()
    if not media_cache.SHA256_RE.match(h):
        raise HTTPException(400, "invalid sha256")
    pair = media_cache.ensure_file_and_mime(h)
    if not pair:
        raise HTTPException(404, "not found")
    path, mime = pair
    return FileResponse(
        path,
        media_type=mime or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/rankings")
def api_rankings(
    platform: str = Query("wx", pattern="^(wx|dy|yyb)$"),
    date: str | None = None,
):
    with db.get_conn() as conn:
        d = date or _latest_date(conn, platform)
        if not d:
            charts_empty = {api_key: {"entries": []} for api_key, _ in _charts_for_api(platform)}
            return {"date": None, "platform": platform, "charts": charts_empty}
        charts_out: dict = {}
        for api_key, db_chart in _charts_for_api(platform):
            rows = conn.execute(
                """
                SELECT r.rank, r.appid, g.name, g.icon_url, g.developer, g.tags,
                       g.genre_major, g.genre_minor,
                       COALESCE(ds.is_new, 0) AS is_new,
                       COALESCE(ds.is_dropped, 0) AS is_dropped,
                       ds.rank_delta AS rank_delta
                FROM rankings r
                JOIN games g ON g.appid = r.appid
                LEFT JOIN daily_status ds
                  ON ds.date = r.date AND ds.platform = r.platform
                 AND ds.chart = r.chart AND ds.appid = r.appid
                WHERE r.date = ? AND r.platform = ? AND r.chart = ?
                ORDER BY r.rank
                """,
                (d, platform, db_chart),
            ).fetchall()
            dropped = conn.execute(
                """
                SELECT ds.appid, g.name, g.icon_url, g.developer, g.tags,
                       g.genre_major, g.genre_minor,
                       ds.is_new, ds.is_dropped, ds.rank_delta
                FROM daily_status ds
                JOIN games g ON g.appid = ds.appid
                WHERE ds.date = ? AND ds.platform = ? AND ds.chart = ?
                  AND ds.is_dropped = 1
                ORDER BY g.name
                """,
                (d, platform, db_chart),
            ).fetchall()

            entries = []
            for r in rows:
                entries.append(
                    {
                        "rank": int(r["rank"]),
                        "appid": r["appid"],
                        "name": r["name"],
                        "icon_url": media_cache.rewrite_icon_url(conn, r["icon_url"]),
                        "developer": r["developer"],
                        "tags": _parse_tags(r["tags"]),
                        "genre_major": r["genre_major"],
                        "genre_minor": r["genre_minor"],
                        "is_new": bool(r["is_new"]),
                        "is_dropped": bool(r["is_dropped"]),
                        "rank_delta": r["rank_delta"],
                    }
                )
            for r in dropped:
                entries.append(
                    {
                        "rank": None,
                        "appid": r["appid"],
                        "name": r["name"],
                        "icon_url": media_cache.rewrite_icon_url(conn, r["icon_url"]),
                        "developer": r["developer"],
                        "tags": _parse_tags(r["tags"]),
                        "genre_major": r["genre_major"],
                        "genre_minor": r["genre_minor"],
                        "is_new": bool(r["is_new"]),
                        "is_dropped": True,
                        "rank_delta": r["rank_delta"],
                    }
                )
            charts_out[api_key] = {"entries": entries}
        return {"date": d, "platform": platform, "charts": charts_out}


@app.get("/api/game/{appid}")
def api_game(
    appid: str,
    days: int = Query(30, ge=1, le=90),
    platform: str = Query("wx", pattern="^(wx|dy|yyb)$"),
):
    with db.get_conn() as conn:
        g = conn.execute("SELECT * FROM games WHERE appid = ?", (appid,)).fetchone()
        if not g:
            raise HTTPException(404, "game not found")
        icon_public = media_cache.rewrite_icon_url(conn, g["icon_url"])
    series = trends.all_charts_series_for_platform(appid, platform, days)
    chart_labels = {
        "popularity": "人气榜",
        "most_played": "畅玩榜",
        "bestseller": "畅销榜",
        "fresh_game": "新游榜",
        "popular": "热门榜",
        "new_game": "新游榜",
    }
    return {
        "appid": appid,
        "platform": g["platform"],
        "name": g["name"],
        "description": g["description"],
        "icon_url": icon_public,
        "developer": g["developer"],
        "tags": _parse_tags(g["tags"]),
        "genre_major": g["genre_major"],
        "genre_minor": g["genre_minor"],
        "charts": {
            k: {"label": chart_labels.get(k, k), "series": v}
            for k, v in series.items()
        },
    }


@app.get("/api/game/{appid}/sparkline")
def api_sparkline(
    appid: str,
    chart: str = Query(
        ...,
        description="DB chart: popularity|bestseller|most_played|fresh_game|popular|new_game",
    ),
    platform: str = Query("wx", pattern="^(wx|dy|yyb)$"),
    days: int = Query(7, ge=1, le=30),
    end_date: str | None = None,
):
    with db.get_conn() as conn:
        g = conn.execute("SELECT 1 FROM games WHERE appid = ?", (appid,)).fetchone()
        if not g:
            raise HTTPException(404, "game not found")
    pts = trends.rank_series(appid, platform, chart, days, end_date)
    return {"appid": appid, "platform": platform, "chart": chart, "points": pts}


@app.post("/api/ingest")
def api_ingest(body: IngestBody):
    try:
        db_chart = map_ingest_chart(body.platform, body.chart)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    games = [g.model_dump() for g in body.games]
    apply_chart_payload(
        body.date,
        body.platform,
        db_chart,
        games,
        "ok" if len(games) >= 90 else "partial",
        "manual_ingest",
    )
    return {"ok": True, "count": len(games)}


@app.get("/api/collect/detail")
async def api_collect_detail(
    ai_fallback: bool = Query(True, description="抓取失败时是否调用 DeepSeek 生成描述"),
):
    import asyncio

    result = await asyncio.to_thread(collect_detail_batch, ai_fallback)
    return result


@app.get("/api/collect/yyb")
async def api_collect_yyb(
    date: str | None = Query(None),
    force: bool = Query(False, description="当日已过 11:25 窗口时仍拉取三榜"),
):
    import asyncio
    from datetime import date as date_cls

    collect_date = date or date_cls.today().strftime("%Y-%m-%d")
    await asyncio.to_thread(collect_yyb_charts, collect_date, force=force)

    with db.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT chart, status, game_count, note
            FROM snapshots
            WHERE date = ? AND platform = 'yyb'
            """,
            (collect_date,),
        ).fetchall()

    return {
        "date": collect_date,
        "results": [
            {
                "chart": r["chart"],
                "count": r["game_count"],
                "status": r["status"],
                "note": r["note"],
            }
            for r in rows
        ],
    }


@app.get("/api/yyb/insights")
def api_yyb_insights(
    date: str | None = Query(None),
    chart: str = Query("popular", pattern="^(popular|bestseller|new_game)$"),
):
    with db.get_conn() as conn:
        d = date or _latest_date(conn, "yyb")
        if not d:
            return {
                "date": None,
                "chart": chart,
                "top_tags": [],
                "rising_tags": [],
                "developer_concentration": {},
                "wx_overlap_rate": None,
            }

        tag_rows = conn.execute(
            """
            SELECT tag, game_count, avg_rank, top10_count
            FROM yyb_tag_stats
            WHERE date = ? AND chart = ?
            ORDER BY game_count DESC
            LIMIT 20
            """,
            (d, chart),
        ).fetchall()

        rising = conn.execute(
            """
            SELECT t.tag
            FROM yyb_tag_stats t
            JOIN (
                SELECT tag, AVG(game_count) AS avg7
                FROM yyb_tag_stats
                WHERE chart = ? AND date < ? AND date >= date(?, '-7 days')
                GROUP BY tag
            ) h ON h.tag = t.tag
            WHERE t.date = ? AND t.chart = ?
              AND t.game_count > h.avg7
            ORDER BY (t.game_count - h.avg7) DESC
            LIMIT 5
            """,
            (chart, d, d, d, chart),
        ).fetchall()

        dev_rows = conn.execute(
            """
            SELECT g.developer, COUNT(*) AS cnt
            FROM rankings r
            JOIN games g ON g.appid = r.appid
            WHERE r.date = ? AND r.platform = 'yyb' AND r.chart = ?
              AND g.developer IS NOT NULL AND TRIM(g.developer) != ''
            GROUP BY g.developer
            ORDER BY cnt DESC
            LIMIT 3
            """,
            (d, chart),
        ).fetchall()
        total_in_chart = conn.execute(
            "SELECT COUNT(*) AS c FROM rankings WHERE date=? AND platform='yyb' AND chart=?",
            (d, chart),
        ).fetchone()["c"]
        top3_devs = [r["developer"] for r in dev_rows]
        top3_sum = sum(r["cnt"] for r in dev_rows)
        top3_share = round(top3_sum / total_in_chart, 4) if total_in_chart > 0 else 0.0

        yyb_appids = {
            r["appid"]
            for r in conn.execute(
                "SELECT appid FROM rankings WHERE date=? AND platform='yyb' AND chart=?",
                (d, chart),
            ).fetchall()
        }
        wx_appids = {
            r["appid"]
            for r in conn.execute(
                "SELECT appid FROM rankings WHERE date=? AND platform='wx' AND chart='popularity'",
                (d,),
            ).fetchall()
        }
        overlap = len(yyb_appids & wx_appids)
        overlap_rate = round(overlap / len(yyb_appids), 4) if yyb_appids else None

    return {
        "date": d,
        "chart": chart,
        "top_tags": [
            {
                "tag": r["tag"],
                "count": r["game_count"],
                "avg_rank": r["avg_rank"],
                "top10_count": r["top10_count"],
            }
            for r in tag_rows
        ],
        "rising_tags": [r["tag"] for r in rising],
        "developer_concentration": {
            "top3_developers": top3_devs,
            "top3_share": top3_share,
        },
        "wx_overlap_rate": overlap_rate,
    }


@app.get("/api/status")
def api_status(date: str | None = None):
    with db.get_conn() as conn:
        d = date
        if not d:
            row = conn.execute("SELECT MAX(date) AS d FROM snapshots").fetchone()
            d = row["d"] if row and row["d"] else None
        if not d:
            return {"date": None, "snapshots": []}
        rows = conn.execute(
            """
            SELECT date, platform, chart, fetched_at, status, game_count, note
            FROM snapshots WHERE date = ?
            ORDER BY platform, chart
            """,
            (d,),
        ).fetchall()
    return {
        "date": d,
        "snapshots": [dict(r) for r in rows],
    }


@app.get("/api/classify/run")
async def api_classify_run(force: bool = Query(False)):
    import asyncio

    result = await asyncio.to_thread(classify_games_batch, force)
    return result


@app.get("/api/rankings/aggregate")
def api_rankings_aggregate(
    platform: str = Query(..., pattern="^(wx|dy|yyb)$"),
    time_range: Literal["week", "month"] = Query(..., alias="range"),
    end_date: str | None = None,
):
    days = 7 if time_range == "week" else 30
    with db.get_conn() as conn:
        end = end_date or _latest_date(conn, platform) or date_cls.today().isoformat()
    end_dt = date_cls.fromisoformat(end)
    start_dt = end_dt - timedelta(days=days - 1)
    start = start_dt.isoformat()
    end = end_dt.isoformat()

    with db.get_conn() as conn:
        chart_rows = conn.execute(
            "SELECT DISTINCT chart FROM rankings WHERE platform=? AND date BETWEEN ? AND ?",
            (platform, start, end),
        ).fetchall()
        charts = [r["chart"] for r in chart_rows]

        result_charts: dict = {}
        for chart in charts:
            rows = conn.execute(
                """
                SELECT
                    r.appid,
                    g.name,
                    g.icon_url,
                    g.developer,
                    g.genre_major,
                    g.tags,
                    ROUND(AVG(r.rank), 1) AS avg_rank,
                    COUNT(r.rank) AS appearances
                FROM rankings r
                JOIN games g ON g.appid = r.appid
                WHERE r.platform = ? AND r.chart = ? AND r.date BETWEEN ? AND ?
                GROUP BY r.appid
                ORDER BY avg_rank ASC
                """,
                (platform, chart, start, end),
            ).fetchall()
            result_charts[chart] = []
            for r in rows:
                icon_u = media_cache.rewrite_icon_url(conn, r["icon_url"])
                result_charts[chart].append(
                    {
                        "appid": r["appid"],
                        "name": r["name"],
                        "icon_url": icon_u,
                        "developer": r["developer"],
                        "genre_major": r["genre_major"],
                        "tags": _parse_tags(r["tags"]),
                        "avg_rank": r["avg_rank"],
                        "appearances": r["appearances"],
                    }
                )

    return {
        "platform": platform,
        "range": time_range,
        "start_date": start,
        "end_date": end,
        "charts": result_charts,
    }


@app.get("/api/search")
def api_search(
    q: str,
    platform: str = Query(..., pattern="^(wx|dy|yyb)$"),
    date: str | None = None,
    field: Literal["name", "developer"] = "name",
):
    qstrip = (q or "").strip()
    if not qstrip:
        return {"query": q, "field": field, "platform": platform, "results": []}

    with db.get_conn() as conn:
        query_date = date or _latest_date(conn, platform)
        if not query_date:
            return {
                "query": qstrip,
                "field": field,
                "platform": platform,
                "date": None,
                "results": [],
            }
        like = f"%{qstrip}%"
        col = "name" if field == "name" else "developer"
        games = conn.execute(
            f"SELECT appid, name, developer, icon_url, genre_major, tags "
            f"FROM games WHERE platform = ? AND {col} LIKE ?",
            (platform, like),
        ).fetchall()

        results = []
        for g in games:
            charts_row = conn.execute(
                "SELECT chart, rank FROM rankings WHERE platform=? AND date=? AND appid=?",
                (platform, query_date, g["appid"]),
            ).fetchall()
            charts = {r["chart"]: r["rank"] for r in charts_row}
            results.append(
                {
                    "appid": g["appid"],
                    "name": g["name"],
                    "developer": g["developer"],
                    "icon_url": media_cache.rewrite_icon_url(conn, g["icon_url"]),
                    "genre_major": g["genre_major"],
                    "tags": _parse_tags(g["tags"]),
                    "charts": charts,
                }
            )

    return {
        "query": qstrip,
        "field": field,
        "platform": platform,
        "date": query_date,
        "results": results,
    }


@app.get("/api/genre/snapshot")
def api_genre_snapshot(
    date: str,
    platform: str = Query(..., pattern="^(wx|dy|yyb)$"),
    chart: str = Query(...),
):
    with db.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT g.genre_major, COUNT(*) AS cnt, ROUND(AVG(r.rank), 1) AS avg_rank
            FROM rankings r JOIN games g ON g.appid = r.appid
            WHERE r.date=? AND r.platform=? AND r.chart=? AND g.genre_major IS NOT NULL
            GROUP BY g.genre_major
            ORDER BY cnt DESC
            """,
            (date, platform, chart),
        ).fetchall()
        genre_distribution = [
            {"genre": r["genre_major"], "count": r["cnt"], "avg_rank": r["avg_rank"]}
            for r in rows
        ]

        tag_rows = conn.execute(
            "SELECT g.tags FROM rankings r JOIN games g ON g.appid=r.appid "
            "WHERE r.date=? AND r.platform=? AND r.chart=?",
            (date, platform, chart),
        ).fetchall()
        tag_counts: dict[str, int] = {}
        for row in tag_rows:
            for tag in _tags_split(row["tags"]):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        tag_frequency = sorted(
            [{"tag": k, "count": v} for k, v in tag_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:20]

    return {
        "date": date,
        "platform": platform,
        "chart": chart,
        "genre_distribution": genre_distribution,
        "tag_frequency": tag_frequency,
    }


@app.get("/api/genre/trend")
def api_genre_trend(
    platform: str = Query(..., pattern="^(wx|dy|yyb)$"),
    chart: str = Query(...),
    days: int = Query(30, ge=1, le=365),
):
    end = date_cls.today()
    start = end - timedelta(days=days - 1)
    start_s = start.isoformat()
    end_s = end.isoformat()
    with db.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.date, g.genre_major, COUNT(*) AS cnt
            FROM rankings r JOIN games g ON g.appid=r.appid
            WHERE r.platform=? AND r.chart=? AND r.date BETWEEN ? AND ?
              AND g.genre_major IS NOT NULL
            GROUP BY r.date, g.genre_major
            ORDER BY r.date ASC
            """,
            (platform, chart, start_s, end_s),
        ).fetchall()

    dates_set = sorted({r["date"] for r in rows})
    genres_set = {r["genre_major"] for r in rows}
    series: dict[str, list] = {g: [] for g in genres_set}
    lookup = {(r["date"], r["genre_major"]): r["cnt"] for r in rows}
    for d in dates_set:
        for g in genres_set:
            series[g].append(lookup.get((d, g), 0))

    return {
        "platform": platform,
        "chart": chart,
        "days": days,
        "dates": dates_set,
        "series": series,
    }


# ── Static frontend (production / local without Vite) ─────────────────────
if FRONT_DIST.is_dir():
    app.mount(
        "/minigame-tracker",
        StaticFiles(directory=str(FRONT_DIST), html=True),
        name="static",
    )
