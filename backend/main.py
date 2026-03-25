"""FastAPI app: REST API + optional static frontend."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend import db
from backend.analyzer import trends
from backend.ingest_service import apply_chart_payload, map_ingest_chart
from backend.models import IngestBody
from collector.scheduler import shutdown_scheduler, start_scheduler

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


@app.get("/api/rankings")
def api_rankings(
    platform: str = Query("wx", pattern="^(wx|dy)$"),
    date: str | None = None,
):
    with db.get_conn() as conn:
        d = date or _latest_date(conn, platform)
        if not d:
            return {"date": None, "platform": platform, "charts": {}}
        charts_out: dict = {}
        for api_key, db_chart in _charts_for_api(platform):
            rows = conn.execute(
                """
                SELECT r.rank, r.appid, g.name, g.icon_url, g.developer, g.tags,
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
                        "icon_url": r["icon_url"],
                        "developer": r["developer"],
                        "tags": _parse_tags(r["tags"]),
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
                        "icon_url": r["icon_url"],
                        "developer": r["developer"],
                        "tags": _parse_tags(r["tags"]),
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
    platform: str = Query("wx", pattern="^(wx|dy)$"),
):
    with db.get_conn() as conn:
        g = conn.execute("SELECT * FROM games WHERE appid = ?", (appid,)).fetchone()
        if not g:
            raise HTTPException(404, "game not found")
    series = trends.all_charts_series_for_platform(appid, platform, days)
    chart_labels = {
        "popularity": "人气榜",
        "most_played": "畅玩榜",
        "bestseller": "畅销榜",
        "fresh_game": "新游榜",
    }
    return {
        "appid": appid,
        "platform": g["platform"],
        "name": g["name"],
        "description": g["description"],
        "icon_url": g["icon_url"],
        "developer": g["developer"],
        "tags": _parse_tags(g["tags"]),
        "charts": {
            k: {"label": chart_labels.get(k, k), "series": v}
            for k, v in series.items()
        },
    }


@app.get("/api/game/{appid}/sparkline")
def api_sparkline(
    appid: str,
    chart: str = Query(..., description="DB chart: popularity|bestseller|most_played|fresh_game"),
    platform: str = Query("wx", pattern="^(wx|dy)$"),
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


# ── Static frontend (production / local without Vite) ─────────────────────
if FRONT_DIST.is_dir():
    app.mount(
        "/minigame-tracker",
        StaticFiles(directory=str(FRONT_DIST), html=True),
        name="static",
    )
