"""Icon disk cache (CAS by sha256) + URL whitelist; TTL refresh on read."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from backend import db

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
TTL_DAYS = int(os.getenv("MEDIA_CACHE_TTL_DAYS", "7"))
MAX_BYTES = int(os.getenv("MEDIA_CACHE_MAX_BYTES", str(5 * 1024 * 1024)))

DEFAULT_SUFFIXES = (
    ".qq.com",
    ".gtimg.com",
    ".gtimg.cn",
    ".qlogo.cn",
    ".qpic.cn",
    ".myqcloud.com",
)

SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _allowed_suffixes() -> tuple[str, ...]:
    raw = os.getenv("MEDIA_ALLOWED_HOST_SUFFIXES", "").strip()
    if not raw:
        return DEFAULT_SUFFIXES
    return tuple(x.strip().lower() for x in raw.split(",") if x.strip())


def is_allowed_icon_url(url: str) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    if not host:
        return False
    for suf in _allowed_suffixes():
        s = suf.strip().lower()
        if not s.startswith("."):
            s = f".{s}"
        root = s[1:]
        if host == root or host.endswith(s):
            return True
    return False


def media_root() -> Path:
    raw = os.getenv("MEDIA_CACHE_DIR", "data/media").strip()
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def path_for_hash(sha256_hex: str) -> Path:
    h = sha256_hex.lower()
    root = media_root()
    if len(h) < 3:
        return root / h
    return root / h[:2] / h[2:]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _expires_at() -> str:
    return _iso(_utc_now() + timedelta(days=TTL_DAYS))


def is_expired(expires_at_iso: str) -> bool:
    try:
        s = expires_at_iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return _utc_now() >= dt
    except Exception:
        return True


def store_url(source_url: str) -> str | None:
    """Download URL (if allowed), write CAS file, upsert media_cache. Returns sha256 hex or None."""
    if not is_allowed_icon_url(source_url):
        return None
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(source_url)
            resp.raise_for_status()
            body = resp.content
            ctype = resp.headers.get("content-type", "").split(";")[0].strip() or None
    except Exception as e:
        logger.warning("media fetch failed %s: %s", source_url[:96], e)
        return None

    if len(body) > MAX_BYTES:
        logger.warning("media too large: %d bytes", len(body))
        return None

    h = hashlib.sha256(body).hexdigest()
    path = path_for_hash(h)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    now = _iso(_utc_now())
    exp = _expires_at()
    with db.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO media_cache (source_url, sha256, mime, byte_size, stored_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_url) DO UPDATE SET
              sha256 = excluded.sha256,
              mime = excluded.mime,
              byte_size = excluded.byte_size,
              stored_at = excluded.stored_at,
              expires_at = excluded.expires_at
            """,
            (source_url, h, ctype, len(body), now, exp),
        )
    return h


def rewrite_icon_url(conn, raw_url: str | None) -> str | None:
    """Return /api/media/{sha} when cached and valid; else original URL (or None)."""
    if not raw_url:
        return None
    if not is_allowed_icon_url(raw_url):
        return raw_url
    row = conn.execute(
        "SELECT sha256, expires_at FROM media_cache WHERE source_url = ?",
        (raw_url,),
    ).fetchone()
    if (
        row
        and not is_expired(row["expires_at"])
        and path_for_hash(row["sha256"]).exists()
    ):
        return f"/api/media/{row['sha256']}"
    return raw_url


def ensure_file_and_mime(sha_hex: str) -> tuple[Path, str | None] | None:
    """Resolve path + mime; refresh from DB source_url if missing or expired."""
    sha = sha_hex.lower().strip()
    if not SHA256_RE.match(sha):
        return None
    with db.get_conn() as conn:
        row = conn.execute(
            """
            SELECT source_url, mime, expires_at FROM media_cache
            WHERE sha256 = ? LIMIT 1
            """,
            (sha,),
        ).fetchone()
    if not row:
        return None
    path = path_for_hash(sha)
    mime = row["mime"]
    if path.exists() and not is_expired(row["expires_at"]):
        return path, mime
    new_h = store_url(row["source_url"])
    if not new_h:
        return (path, mime) if path.exists() else None
    np = path_for_hash(new_h)
    if not np.exists():
        return None
    with db.get_conn() as conn:
        r2 = conn.execute(
            "SELECT mime FROM media_cache WHERE sha256 = ? LIMIT 1",
            (new_h,),
        ).fetchone()
    return np, (r2["mime"] if r2 else mime)


def prefetch_icon_urls(urls: list[str | None]) -> None:
    uniq: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if not u or u in seen:
            continue
        seen.add(u)
        if is_allowed_icon_url(u):
            uniq.append(u)
    for u in uniq:
        try:
            store_url(u)
        except Exception:
            logger.exception("prefetch icon failed: %s", u[:80])


def schedule_prefetch_icons(urls: list[str | None]) -> None:
    t = threading.Thread(target=prefetch_icon_urls, args=(urls,), daemon=True)
    t.start()
