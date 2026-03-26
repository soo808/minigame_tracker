"""Load Gravity API credentials from environment."""
import os
from pathlib import Path

from dotenv import load_dotenv

_root = Path(__file__).resolve().parent.parent
load_dotenv(_root / ".env")

GRAVITY_JWT: str = os.getenv("GRAVITY_JWT", "").strip()
GRAVITY_ID: str = os.getenv("GRAVITY_ID", "").strip()
GRAVITY_CID: str = os.getenv("GRAVITY_CID", "").strip()
GRAVITY_EMAIL: str = os.getenv("GRAVITY_EMAIL", "").strip()

API_URL = "https://api-insight.gravity-engine.com/apprank/api/v1/rank/list/"

# (rank_genre, rank_type, label) — 与引力枚举一致
GRAVITY_CHARTS: list[tuple[str, str, str]] = [
    ("wx_minigame", "popularity", "微信人气榜"),
    ("wx_minigame", "bestseller", "微信畅销榜"),
    ("wx_minigame", "most_played", "微信畅玩榜"),
    ("dy_minigame", "popularity", "抖音人气榜"),
    ("dy_minigame", "bestseller", "抖音畅销榜"),
    ("dy_minigame", "fresh_game", "抖音新游榜"),
]


def gravity_genre_to_platform(rank_genre: str) -> str:
    if rank_genre == "wx_minigame":
        return "wx"
    if rank_genre == "dy_minigame":
        return "dy"
    raise ValueError(f"unknown rank_genre: {rank_genre}")


def rank_type_to_db_chart(platform: str, rank_type: str) -> str:
    return rank_type  # DB 直接使用 popularity / bestseller / most_played / fresh_game


# ── YYB 腾讯应用宝 ─────────────────────────────────────────────────────────
YYB_GUID: str = os.getenv("YYB_GUID", "91b8f8b5-de10-46a4-b128-81f31fc100ae").strip()
YYB_PROXY_URL: str | None = os.getenv("YYB_PROXY_URL", None) or None

YYB_API_URL = "https://yybadaccess.3g.qq.com/v2/dc_pcyyb_official"

YYB_CHARTS: list[dict] = [
    {
        "chart_id": "popular",
        "layout": "wechat-popularrank-game-list",
        "exp_scene_ids": "",
    },
    {
        "chart_id": "bestseller",
        "layout": "wechat-bestsellrank-game-list",
        "exp_scene_ids": "92250",
    },
    {
        "chart_id": "new_game",
        "layout": "wechat-newrank-game-list",
        "exp_scene_ids": "",
    },
]
