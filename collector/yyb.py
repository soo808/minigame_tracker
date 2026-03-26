"""腾讯应用宝微信小游戏榜单采集器（直连 POST API，代理降级）。

分页与 sj.qq.com 一致：`body.offset` 恒为 0，靠 `listI.offset.repInt`（batch）与
`exposed_appids` 翻页。先直连；连续 403/429 且配置了 `YYB_PROXY_URL` 时切换代理。

工程顺序：先完成计划 Task 1～10；Task 7b 回填依赖 `platform=yyb` 数据。
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

import httpx

from collector import config

logger = logging.getLogger(__name__)

PAGE_SIZE = 10
MAX_PAGES = 30
# 与浏览器一致：body.offset 不参与翻页，始终为 0（翻页靠 listI.offset + exposed_appids）
FIXED_BODY_OFFSET = 0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
    "Content-Type": "text/plain;charset=UTF-8",
    "Origin": "https://sj.qq.com",
    "Referer": "https://sj.qq.com/",
}


def build_request_body(
    layout: str,
    exp_scene_ids: str,
    guid: str,
    offset: int,
    size: int,
    exposed_app_ids: list[str],
    batch_num: int,
) -> dict:
    return {
        "head": {
            "cmd": "dc_pcyyb_official",
            "authInfo": {"businessId": "AuthName"},
            "deviceInfo": {"platformType": 1},
            "userInfo": {"guid": guid},
            "expSceneIds": exp_scene_ids,
            "hostAppInfo": {"scene": "game_list"},
        },
        "body": {
            "bid": "yybhome",
            "offset": offset,
            "size": size,
            "preview": False,
            "listS": {"region": {"repStr": ["CN"]}},
            "layout": layout,
            "listI": {
                "exposed_appids": {"repInt": [exposed_app_ids]},
                "offset": {"repInt": [batch_num]},
            },
        },
    }


def parse_yyb_items(items: list) -> list[dict]:
    """从 API 响应的 items 数组中提取游戏信息。"""
    result = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        pkg_name = item.get("pkg_name", "")
        if not pkg_name:
            continue
        name = item.get("name", "").strip()
        if not name:
            continue

        try:
            rank = int(item.get("report_info", {}).get("screenorder") or idx)
        except (TypeError, ValueError):
            rank = idx

        raw_tags = item.get("tags", "") or ""
        if raw_tags.strip():
            tag_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
            tags = json.dumps(tag_list, ensure_ascii=False) if tag_list else None
        else:
            tags = None

        result.append(
            {
                "rank": rank,
                "appid": str(pkg_name),
                "yyb_app_id": str(item.get("app_id", "")),
                "name": name,
                "icon_url": item.get("icon") or None,
                "developer": item.get("developer") or None,
                "tags": tags,
            }
        )
    return result


def _make_client(use_proxy: bool = False) -> httpx.Client:
    proxy_url = config.YYB_PROXY_URL
    if use_proxy and proxy_url:
        return httpx.Client(proxy=proxy_url, timeout=30)
    return httpx.Client(timeout=30)


def _is_blocked(resp: httpx.Response | None, items: list | None) -> bool:
    """HTTP 403/429。空 items 表示分页结束，不算 block。"""
    if resp is not None and resp.status_code in (403, 429):
        return True
    return False


def _extract_items(data: dict) -> list:
    try:
        comps = data.get("data", {}).get("components", [])
        if comps:
            return comps[0].get("data", {}).get("itemData", []) or []
    except (AttributeError, IndexError, TypeError):
        pass
    return data.get("items", []) or []


def _post_with_retry(
    client: httpx.Client, body: dict
) -> tuple[httpx.Response | None, list | None]:
    delays = [2, 4, 8]
    last_exc: Exception | None = None
    for attempt, delay in enumerate(delays, start=1):
        try:
            resp = client.post(config.YYB_API_URL, headers=HEADERS, content=json.dumps(body))
            if resp.status_code in (403, 429):
                logger.warning("yyb blocked HTTP %s (attempt %d)", resp.status_code, attempt)
                return resp, None
            resp.raise_for_status()
            data = resp.json()
            items = _extract_items(data)
            return None, items
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            logger.warning("yyb request error (attempt %d): %s", attempt, exc)
            if attempt < len(delays):
                time.sleep(delay)
    raise RuntimeError(f"yyb API failed after {len(delays)} attempts: {last_exc}")


def fetch_yyb_chart(
    chart_cfg: dict,
    date: str,
    guid: str,
) -> list[dict]:
    """分页采集单个 yyb 榜单，最多 200 条。date 用于日志上下文。"""
    _ = date
    layout = chart_cfg["layout"]
    exp_scene_ids = chart_cfg["exp_scene_ids"]

    collected: list[dict] = []
    exposed_ids: list[str] = []
    batch_num = 1
    consecutive_block = 0
    use_proxy = False

    for _ in range(MAX_PAGES):
        body = build_request_body(
            layout=layout,
            exp_scene_ids=exp_scene_ids,
            guid=guid,
            offset=FIXED_BODY_OFFSET,
            size=PAGE_SIZE,
            exposed_app_ids=exposed_ids,
            batch_num=batch_num,
        )

        client = _make_client(use_proxy)
        try:
            err_resp, items = _post_with_retry(client, body)
        finally:
            if client is not None:
                client.close()

        if _is_blocked(err_resp, items):
            consecutive_block += 1
            logger.warning(
                "yyb blocked (consecutive=%d, chart=%s, proxy=%s)",
                consecutive_block,
                chart_cfg["chart_id"],
                use_proxy,
            )
            if consecutive_block >= 3:
                if not use_proxy and config.YYB_PROXY_URL:
                    logger.info("switching to proxy for yyb chart=%s", chart_cfg["chart_id"])
                    use_proxy = True
                    consecutive_block = 0
                    continue
                raise RuntimeError(
                    f"yyb chart={chart_cfg['chart_id']} blocked after 3 consecutive failures"
                    + (
                        " (no proxy configured)"
                        if not config.YYB_PROXY_URL
                        else " (proxy also failed)"
                    )
                )
            time.sleep(random.uniform(2, 5))
            continue

        consecutive_block = 0
        assert items is not None

        if len(items) == 0:
            break

        all_parsed = parse_yyb_items(items)
        # screenorder 多为页内序号，不是全榜名次；直接入库会导致 rank 重复，
        # 前端按 rank 建 Map 只显示约 20 格。按已采长度顺序编号全局名次。
        remaining = 200 - len(collected)
        chunk = all_parsed[:remaining]
        base_rank = len(collected)
        for i, g in enumerate(chunk):
            g["rank"] = base_rank + i + 1

        for g in all_parsed:
            aid = (g.get("yyb_app_id") or "").strip()
            if aid:
                exposed_ids.append(aid)

        collected.extend(chunk)

        logger.info(
            "yyb page chart=%s batch=%d body.offset=%s len_items=%d collected=%d",
            chart_cfg["chart_id"],
            batch_num,
            FIXED_BODY_OFFSET,
            len(items),
            len(collected),
        )

        if len(collected) >= 200:
            break

        # 接口常一次返回多于 body.size（如 size=10 返 20）；仅当本页明显短于请求 size 时视为到底
        if len(items) < PAGE_SIZE:
            break

        batch_num += 1
        time.sleep(random.uniform(1, 3))

    logger.info(
        "yyb fetch_yyb_chart done: chart=%s count=%d",
        chart_cfg["chart_id"],
        len(collected),
    )
    return collected
