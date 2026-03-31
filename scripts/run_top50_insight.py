"""Manual top-50 insight run for wx, dy, yyb (same as AUTO_TOP50_INSIGHT_AFTER_COLLECT).

Run from repo root with .env / OPENAI_* configured:

    python scripts/run_top50_insight.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend import db
from backend.analyzer.insight_infer import TOP50_CHARTS_MAX_LIMIT, run_insight_infer_batch


def main() -> None:
    db.init_db()
    for plat in ("wx", "dy", "yyb"):
        out = run_insight_infer_batch(
            limit=TOP50_CHARTS_MAX_LIMIT,
            batch_size=12,
            only_missing=True,
            force=False,
            platform=plat,
            ranking_date=None,
            top50_charts=True,
            insight_gap_only=True,
        )
        print(
            f"{plat}: candidates={out.get('candidates')} batches={out.get('batches')} "
            f"mon={out.get('monetization_updated')} gp={out.get('gameplay_links_added')} "
            f"vir={out.get('virality_inserted')} errors={out.get('errors')}"
        )


if __name__ == "__main__":
    main()
