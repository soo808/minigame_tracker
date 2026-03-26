"""Media cache: whitelist, rewrite, CAS paths."""
from __future__ import annotations

from datetime import timedelta, timezone
from datetime import datetime

import pytest

from backend import db


@pytest.fixture
def media_env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("MEDIA_CACHE_DIR", str(tmp_path / "media"))
    db.init_db()
    yield tmp_path


def test_is_allowed_gtimg_cn():
    from backend import media_cache

    assert media_cache.is_allowed_icon_url("https://vfiles.gtimg.cn/wupload/xy/test.png")
    assert not media_cache.is_allowed_icon_url("https://evil.com/x.png")


def test_rewrite_returns_api_path_when_cached(media_env):
    from backend import media_cache

    url = "https://vfiles.gtimg.cn/wupload/xy/icon.png"
    h = "a" * 64
    p = media_cache.path_for_hash(h)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    exp = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0).isoformat()
    with db.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO media_cache (source_url, sha256, mime, byte_size, stored_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (url, h, "image/png", 4, now, exp),
        )
    with db.get_conn() as conn:
        out = media_cache.rewrite_icon_url(conn, url)
    assert out == f"/api/media/{h}"


def test_rewrite_passthrough_unknown_host(media_env):
    from backend import media_cache

    u = "https://unknown-cdn.example.com/i.png"
    with db.get_conn() as conn:
        assert media_cache.rewrite_icon_url(conn, u) is u


def test_store_url_writes_file_and_row(media_env, monkeypatch):
    from backend import media_cache

    url = "https://vfiles.gtimg.cn/wupload/xy/z.png"
    body = b"\x89PNG\r\n\x1a\n"

    class FakeResp:
        status_code = 200
        content = body
        headers = {"content-type": "image/png"}

        def raise_for_status(self):
            pass

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, u):
            assert u == url
            return FakeResp()

    monkeypatch.setattr(
        "backend.media_cache.httpx.Client",
        lambda **kw: FakeClient(),
    )
    h = media_cache.store_url(url)
    assert h is not None
    assert len(h) == 64
    assert media_cache.path_for_hash(h).exists()
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT sha256, source_url FROM media_cache WHERE source_url = ?",
            (url,),
        ).fetchone()
    assert row["sha256"] == h
