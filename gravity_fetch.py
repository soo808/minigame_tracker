"""
CLI：拉取六榜并写入 gravity_response.txt / decrypt_sample.json。
配置见项目根目录 .env（或环境变量 GRAVITY_*）。核心逻辑在 collector.gravity。
"""
from __future__ import annotations

import json
import os
import random
import sys
import time

import httpx

from collector.config import GRAVITY_CHARTS
from collector.gravity import fetch_chart, gravity_items_to_games


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(os.getenv("TZ", "Asia/Shanghai"))
    today = datetime.now(tz).strftime("%Y-%m-%d")
    print(f"采集日期：{today}\n")

    all_results: dict[str, list] = {}
    with httpx.Client(follow_redirects=True) as client:
        for rank_genre, rank_type, label in GRAVITY_CHARTS:
            key = f"{rank_genre}_{rank_type}"
            print(f"── {label} ({key}) ──")
            try:
                raw = fetch_chart(client, rank_genre, rank_type, today)
                games = gravity_items_to_games(raw)
                print(f"  解密成功：{len(games)} 条游戏")
                for g in games[:3]:
                    print(f"    #{g['rank']}  {g['name']}")
                all_results[key] = raw
            except httpx.HTTPStatusError as e:
                print(f"  [FAIL] HTTP {e.response.status_code} - Token 可能已过期")
                all_results[key] = []
            except Exception as e:
                print(f"  [FAIL] {e}")
                all_results[key] = []

            time.sleep(random.uniform(2, 4))

    base = os.path.dirname(__file__)
    with open(os.path.join(base, "gravity_response.txt"), "w", encoding="utf-8") as f:
        summary = {k: len(v) for k, v in all_results.items()}
        json.dump(summary, f, ensure_ascii=False, indent=2)

    sample = {k: v[:3] if isinstance(v, list) else [] for k, v in all_results.items() if v}
    with open(os.path.join(base, "decrypt_sample.json"), "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)

    print("\n汇总写入 gravity_response.txt，字段样本写入 decrypt_sample.json")


if __name__ == "__main__":
    main()
