"""Insert demo gameplay tags + sample monetization/virality for first game in DB.

**仅本地开发**：生产环境勿用；同事环境应使用 POST /api/insight/infer-batch 或手动 upsert。

Run from repo root:
  set MINIGAME_ALLOW_DEMO_SEED=1   # PowerShell: $env:MINIGAME_ALLOW_DEMO_SEED="1"
  python scripts/seed_insight_demo.py

误灌清理：python scripts/cleanup_seed_insight_demo.py
Requires existing games rows (e.g. after daily collect).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend import db

DEMO_SEED_MARKER = "seed_insight_demo"


def main() -> None:
    if os.environ.get("MINIGAME_ALLOW_DEMO_SEED") != "1":
        print(
            "Refused: demo seed is disabled. For local dev only, set MINIGAME_ALLOW_DEMO_SEED=1 "
            "then re-run. Production: use POST /api/insight/infer-batch or API upsert."
        )
        sys.exit(1)

    db.init_db()
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT appid, name FROM games ORDER BY appid LIMIT 1"
        ).fetchone()
        if not row:
            print("No games in DB; run collector or ingest first.")
            return
        appid = row["appid"]
        print(f"Using appid={appid} ({row['name']})")

        tags = [
            ("loot_box", "开箱类"),
            ("target_like", "靶心类"),
            ("merge", "合成合合"),
        ]
        for slug, name in tags:
            conn.execute(
                "INSERT OR IGNORE INTO gameplay_tags (slug, name) VALUES (?, ?)",
                (slug, name),
            )
        tid = conn.execute(
            "SELECT id FROM gameplay_tags WHERE slug = ?",
            ("loot_box",),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO game_gameplay_tags (appid, tag_id, role, source, updated_by)
            VALUES (?, ?, 'primary', 'manual', ?)
            ON CONFLICT(appid, tag_id) DO NOTHING
            """,
            (appid, tid, DEMO_SEED_MARKER),
        )

        conn.execute(
            """
            INSERT INTO game_monetization
              (appid, monetization_model, mix_note, confidence, evidence_summary, source, updated_by)
            VALUES (?, 'hybrid', '示例：激励视频+内购礼包', 0.6, ?, 'manual', ?)
            ON CONFLICT(appid) DO UPDATE SET
              monetization_model = excluded.monetization_model,
              mix_note = excluded.mix_note,
              confidence = excluded.confidence,
              evidence_summary = excluded.evidence_summary,
              source = excluded.source,
              updated_by = excluded.updated_by,
              updated_at = datetime('now')
            """,
            (
                appid,
                json.dumps(["畅销+畅玩双榜靠前"], ensure_ascii=False),
                DEMO_SEED_MARKER,
            ),
        )

        conn.execute(
            """
            INSERT INTO virality_assumptions
              (appid, channels, hypothesis, evidence, source, updated_by)
            VALUES (?, ?, ?, ?, 'manual', ?)
            """,
            (
                appid,
                json.dumps(["wechat_share", "group_play"], ensure_ascii=False),
                "示例：分享得体力 / 群排行刺激传播",
                "来自 seed 脚本占位，可删除后通过 API 维护",
                DEMO_SEED_MARKER,
            ),
        )

    print("Done. Open a game detail (or this appid) to see gameplay/monetization/virality blocks.")


if __name__ == "__main__":
    main()
