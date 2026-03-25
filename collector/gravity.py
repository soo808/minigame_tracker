"""引力引擎榜单 API：签名、AES-ECB 解密、拉取单榜。"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import time
from typing import Any

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from collector import config


def make_v() -> str:
    return "etg" + "".join(random.choices("0123456789abcdef", k=5))


def make_signature(timestamp_ms: int, session_b64: str, body: dict) -> str:
    ts_slice = str(timestamp_ms)[3:8]
    body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    raw = ts_slice + "11" + session_b64 + body_json
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_headers(timestamp_ms: int, v: str, body: dict) -> dict:
    g = base64.b64encode(v.encode()).decode()
    jwt = config.GRAVITY_JWT
    if not jwt:
        raise RuntimeError("GRAVITY_JWT is not set in environment")
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/json",
        "Authorization": jwt if jwt.startswith("Bearer ") else jwt,
        "Gravity_Id": config.GRAVITY_ID,
        "gravity_Cid": config.GRAVITY_CID,
        "gravity_Super": "true",
        "gravity_Email": config.GRAVITY_EMAIL,
        "gravity-timestamp": str(timestamp_ms),
        "gravity-session": g,
        "gravity-signature": make_signature(timestamp_ms, g, body),
        "Origin": "https://rank.gravity-engine.com",
        "Referer": "https://rank.gravity-engine.com/",
    }


def derive_key(v: str, timestamp_ms: int) -> bytes:
    key_str = v + "gv" + str(timestamp_ms)[7:11] + "00"
    if len(key_str) != 16:
        raise ValueError(f"AES key length != 16: {len(key_str)}")
    return key_str.encode("utf-8")


def decrypt_response(encrypted_text: str, v: str, timestamp_ms: int) -> list:
    key = derive_key(v, timestamp_ms)
    cipher = AES.new(key, AES.MODE_ECB)
    raw = cipher.decrypt(base64.b64decode(encrypted_text))
    plain = unpad(raw, AES.block_size)
    result = json.loads(plain.decode("utf-8"))
    return result.get("list", result) if isinstance(result, dict) else result


def build_rank_body(rank_genre: str, rank_type: str, date: str) -> dict:
    return {
        "page": 1,
        "page_size": 100,
        "extra_fields": {"change_label": True, "app_genre_ranking": True},
        "filters": [
            {"field": "rank_type", "operator": 1, "values": [rank_type]},
            {"field": "rank_genre", "operator": 1, "values": [rank_genre]},
            {"field": "stat_datetime", "operator": 1, "values": [date]},
        ],
    }


def fetch_chart(
    client: httpx.Client,
    rank_genre: str,
    rank_type: str,
    date: str,
) -> list:
    body = build_rank_body(rank_genre, rank_type, date)
    ts = int(time.time() * 1000)
    v = make_v()
    headers = build_headers(ts, v, body)
    resp = client.post(config.API_URL, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    r = resp.json()
    if r.get("code") != 0:
        raise ValueError(f"API error {r.get('code')}: {r.get('msg')}")
    text = r.get("data", {}).get("text")
    if not text:
        raise ValueError("missing data.text in response")
    return decrypt_response(text, v, ts)


def _readable_genre_main(name: Any) -> str | None:
    """引力抖音侧可能返回数字占位主类名，跳过以免出现「1:1名」。"""
    if name is None:
        return None
    s = str(name).strip()
    if not s or s.isdigit():
        return None
    return s


def _tag_append_unique(tags: list[str], seen: set[str], label: str) -> None:
    t = label.strip()
    if not t or t in seen:
        return
    seen.add(t)
    tags.append(t)


def build_category_tags(item: dict, info: dict) -> str | None:
    """
    与引力榜单页一致：app_genre_ranking →「主类:名次名」、子类、tag_list。
    不使用 change_label 等 dict，避免污染展示。
    """
    tags: list[str] = []
    seen: set[str] = set()

    agr = item.get("app_genre_ranking")
    if isinstance(agr, dict):
        main = _readable_genre_main(agr.get("game_type_main_name"))
        rk = agr.get("ranking")
        if main is not None and rk is not None:
            try:
                _tag_append_unique(tags, seen, f"{main}:{int(rk)}名")
            except (TypeError, ValueError):
                pass

    sub = info.get("game_type_sub_name")
    if sub is not None:
        _tag_append_unique(tags, seen, str(sub))

    for raw in item.get("tag_list") or []:
        if raw is not None:
            _tag_append_unique(tags, seen, str(raw))

    if not tags:
        return None
    return json.dumps(tags, ensure_ascii=False)


def parse_list_item_to_game(item: Any, list_index_one_based: int) -> dict | None:
    """Return dict for ingest: rank, appid, name, icon_url, tags, developer."""
    if not isinstance(item, dict):
        return None
    info = item.get("app_info") if isinstance(item.get("app_info"), dict) else {}
    appid = None
    for raw in (info.get("mini_app_id"), info.get("dy_app_id"), item.get("mini_app_id")):
        if raw is not None and str(raw).strip():
            appid = str(raw).strip()
            break
    if not appid:
        for key in (
            "wx_app_id",
            "wx_appid",
            "app_id",
            "appid",
            "game_id",
            "id",
        ):
            raw = info.get(key)
            if raw is not None and str(raw).strip():
                appid = str(raw).strip()
                break
            raw = item.get(key)
            if raw is not None and str(raw).strip():
                appid = str(raw).strip()
                break
    name = (info.get("app_name") or info.get("name") or item.get("name") or "").strip()
    rank = item.get("ranking")
    if rank is None:
        rank = list_index_one_based
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        rank = list_index_one_based
    if not appid or not name:
        return None
    icon = info.get("icon_url") or info.get("icon") or info.get("logo") or item.get("icon_url")
    dev = info.get("publisher_name") or info.get("developer") or info.get("company_name")
    return {
        "rank": rank,
        "appid": appid,
        "name": name,
        "icon_url": str(icon) if icon else None,
        "tags": build_category_tags(item, info),
        "developer": str(dev) if dev else None,
    }


def gravity_items_to_games(items: list) -> list[dict]:
    out: list[dict] = []
    for i, item in enumerate(items, start=1):
        g = parse_list_item_to_game(item, i)
        if g:
            out.append(g)
    return out
