"""One-shot: fetch six gravity charts (wx+dy) for Shanghai today and write the DB.

Use when the rankings date dropdown is missing «today»: the UI only lists dates that
already exist in ``rankings``. If the backend started after the 11:30 Shanghai cutoff
or collection failed, run from repo root with ``.env`` configured (Gravity JWT, etc.):

    python scripts/seed_today.py

Alternatively POST ``/api/ingest`` with the same payloads. Does not replace the
scheduled collector for tomorrow onward.
"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from datetime import datetime
from zoneinfo import ZoneInfo

from backend import db
from backend.ingest_service import apply_chart_payload
from collector.gravity import fetch_chart, gravity_items_to_games
from collector.scheduler import CHART_JOBS


def main() -> None:
    db.init_db()
    tz = ZoneInfo("Asia/Shanghai")
    day = datetime.now(tz).strftime("%Y-%m-%d")
    with httpx.Client(follow_redirects=True) as c:
        for rank_genre, rank_type, platform, db_chart in CHART_JOBS:
            raw = fetch_chart(c, rank_genre, rank_type, day)
            games = gravity_items_to_games(raw)
            apply_chart_payload(day, platform, db_chart, games, "ok", None)
            print(f"{platform} {db_chart}: {len(games)} games")
            time.sleep(random.uniform(1.0, 2.5))


if __name__ == "__main__":
    main()
