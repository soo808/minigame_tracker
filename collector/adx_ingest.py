"""ADX 素材同步：从同事站点 API 拉取素材 → 写入 adx_creatives / adx_creative_game_map。"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

import httpx

from backend import db
from collector import config

logger = logging.getLogger(__name__)


def colleague_adx_configured() -> bool:
    """True when COLLEAGUE_ADX_URL is set."""
    return bool(config.COLLEAGUE_ADX_URL)


def _upsert_creative(conn, item: dict[str, Any]) -> str:
    """Upsert one creative row, return creative_id."""
    cid = str(item["id"])
    conn.execute(
        """
        INSERT INTO adx_creatives (
            creative_id, title, body_text,
            product_id, product_name, product_icon, platform, material_type,
            grade, composite_score, days_on_chart,
            rising_speed, accel_3d,
            material_num, creative_num, exposure_num, exposure_per_creative,
            media_spread, sustain_rate_7d, freshness,
            pic_list_json, video_list_json,
            raw_json, fetched_at
        ) VALUES (
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, datetime('now')
        )
        ON CONFLICT(creative_id) DO UPDATE SET
            title              = excluded.title,
            body_text          = excluded.body_text,
            product_id         = excluded.product_id,
            product_name       = excluded.product_name,
            product_icon       = excluded.product_icon,
            platform           = excluded.platform,
            material_type      = excluded.material_type,
            grade              = excluded.grade,
            composite_score    = excluded.composite_score,
            days_on_chart      = excluded.days_on_chart,
            rising_speed       = excluded.rising_speed,
            accel_3d           = excluded.accel_3d,
            material_num       = excluded.material_num,
            creative_num       = excluded.creative_num,
            exposure_num       = excluded.exposure_num,
            exposure_per_creative = excluded.exposure_per_creative,
            media_spread       = excluded.media_spread,
            sustain_rate_7d    = excluded.sustain_rate_7d,
            freshness          = excluded.freshness,
            pic_list_json      = excluded.pic_list_json,
            video_list_json    = excluded.video_list_json,
            raw_json           = excluded.raw_json,
            fetched_at         = datetime('now')
        """,
        (
            cid,
            item.get("title"),
            item.get("material_text"),
            item.get("product_id"),
            item.get("product_name"),
            item.get("product_icon"),
            item.get("platform"),
            item.get("material_type"),
            item.get("grade"),
            item.get("composite_score"),
            item.get("days"),
            item.get("rising_speed"),
            item.get("accel_3d"),
            item.get("material_num"),
            item.get("creative_num"),
            item.get("exposure_num"),
            item.get("exposure_per_creative"),
            item.get("media_spread"),
            item.get("sustain_rate_7d"),
            item.get("freshness"),
            json.dumps(item.get("pic_list") or [], ensure_ascii=False),
            json.dumps(item.get("video_list") or [], ensure_ascii=False),
            json.dumps(item, ensure_ascii=False),
        ),
    )
    return cid


def _match_game(conn, item: dict[str, Any]) -> str | None:
    """Try to match the creative's product to a game in the games table.

    Returns the matched appid or None.
    """
    product_id = str(item.get("product_id") or "").strip()
    product_name = str(item.get("product_name") or "").strip()

    if product_id:
        row = conn.execute(
            "SELECT appid FROM games WHERE appid = ?", (product_id,)
        ).fetchone()
        if row:
            return row["appid"]

    if not product_name:
        return None

    row = conn.execute(
        "SELECT appid FROM games WHERE name = ?", (product_name,)
    ).fetchone()
    if row:
        return row["appid"]

    row = conn.execute(
        "SELECT appid FROM games WHERE name LIKE ? LIMIT 1",
        (f"%{product_name}%",),
    ).fetchone()
    if row:
        return row["appid"]

    return None


def sync_from_colleague(
    *, dry_run: bool = False, page_size: int = 50
) -> dict[str, Any]:
    """Fetch all creatives from colleague API → upsert to DB → match games.

    Returns summary dict.
    """
    base_url = config.COLLEAGUE_ADX_URL
    if not base_url:
        return {"status": "skipped", "reason": "COLLEAGUE_ADX_URL not set"}

    total_fetched = 0
    upserted = 0
    mapped = 0
    errors: list[str] = []

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        page = 1
        total_pages = 1

        while page <= total_pages:
            sep = "&" if "?" in base_url else "?"
            url = f"{base_url}{sep}page={page}&page_size={page_size}"
            try:
                resp = client.get(url)
                resp.raise_for_status()
                body = resp.json()
            except httpx.HTTPStatusError as e:
                errors.append(f"page {page}: HTTP {e.response.status_code}")
                break
            except Exception as e:
                errors.append(f"page {page}: {e}")
                break

            if not body.get("success"):
                errors.append(f"page {page}: API returned success=false")
                break

            items = body.get("data") or []
            pagination = body.get("pagination") or {}
            total_pages = pagination.get("total_pages", 1)
            total_fetched += len(items)

            if dry_run:
                return {
                    "status": "dry_run",
                    "page": page,
                    "items_on_page": len(items),
                    "total": pagination.get("total"),
                    "total_pages": total_pages,
                    "sample": items[:3],
                }

            with db.get_conn() as conn:
                for item in items:
                    if not item.get("id"):
                        continue
                    _upsert_creative(conn, item)
                    upserted += 1

                    appid = _match_game(conn, item)
                    if appid:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO adx_creative_game_map
                              (creative_id, appid)
                            VALUES (?, ?)
                            """,
                            (str(item["id"]), appid),
                        )
                        mapped += 1

            logger.info(
                "ADX sync page %d/%d: %d items, %d mapped",
                page, total_pages, len(items), mapped,
            )

            page += 1
            if page <= total_pages:
                time.sleep(random.uniform(0.3, 0.8))

    result: dict[str, Any] = {
        "status": "ok",
        "total_fetched": total_fetched,
        "upserted": upserted,
        "mapped": mapped,
    }
    if errors:
        result["errors"] = errors
        result["status"] = "partial" if upserted else "failed"
    return result
