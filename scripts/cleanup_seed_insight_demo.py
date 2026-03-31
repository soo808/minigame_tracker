"""Remove rows written by scripts/seed_insight_demo.py (updated_by = seed_insight_demo).

Run from repo root:  python scripts/cleanup_seed_insight_demo.py
Optional: --dry-run to print counts only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend import db

MARKER = "seed_insight_demo"


def main() -> None:
    p = argparse.ArgumentParser(description="Delete demo seed rows by updated_by marker.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print how many rows would be deleted",
    )
    args = p.parse_args()

    db.init_db()
    with db.get_conn() as conn:
        counts = {}
        for table, clause in (
            ("game_gameplay_tags", "updated_by = ?"),
            ("game_monetization", "updated_by = ?"),
            ("virality_assumptions", "updated_by = ?"),
        ):
            n = conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE {clause}", (MARKER,)
            ).fetchone()["c"]
            counts[table] = n

        print(f"Marker: {MARKER!r}")
        for t, n in counts.items():
            print(f"  {t}: {n}")

        if args.dry_run:
            print("Dry run — no changes.")
            return

        for table, clause in (
            ("game_gameplay_tags", "updated_by = ?"),
            ("virality_assumptions", "updated_by = ?"),
            ("game_monetization", "updated_by = ?"),
        ):
            conn.execute(f"DELETE FROM {table} WHERE {clause}", (MARKER,))

    print("Done.")


if __name__ == "__main__":
    main()
