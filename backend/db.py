"""SQLite (WAL) connection and schema."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

_root = Path(__file__).resolve().parent.parent
load_dotenv(_root / ".env")

_raw_db = os.getenv("DB_PATH", str(_root / "data" / "tracker.db")).strip()
_p = Path(_raw_db).expanduser()
if not _p.is_absolute():
    _p = (_root / _p).resolve()
else:
    _p = _p.resolve()
DB_PATH = str(_p)


def ensure_data_dir() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS games (
              appid         TEXT PRIMARY KEY,
              platform      TEXT NOT NULL,
              name          TEXT NOT NULL,
              description   TEXT,
              icon_url      TEXT,
              tags          TEXT,
              developer     TEXT,
              first_seen    TEXT,
              updated_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS rankings (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              date          TEXT NOT NULL,
              platform      TEXT NOT NULL,
              chart         TEXT NOT NULL,
              rank          INTEGER NOT NULL,
              appid         TEXT NOT NULL REFERENCES games(appid),
              UNIQUE(date, platform, chart, appid)
            );
            CREATE INDEX IF NOT EXISTS idx_rankings_date
              ON rankings(date, platform, chart);
            CREATE INDEX IF NOT EXISTS idx_rankings_appid ON rankings(appid);

            CREATE TABLE IF NOT EXISTS daily_status (
              date          TEXT    NOT NULL,
              platform      TEXT    NOT NULL,
              chart         TEXT    NOT NULL,
              appid         TEXT    NOT NULL REFERENCES games(appid),
              is_new        INTEGER NOT NULL DEFAULT 0,
              is_dropped    INTEGER NOT NULL DEFAULT 0,
              rank_delta    INTEGER,
              PRIMARY KEY (date, platform, chart, appid)
            );

            CREATE TABLE IF NOT EXISTS snapshots (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              date          TEXT NOT NULL,
              platform      TEXT NOT NULL,
              chart         TEXT NOT NULL,
              fetched_at    TEXT NOT NULL,
              status        TEXT NOT NULL,
              game_count    INTEGER,
              note          TEXT,
              UNIQUE(date, platform, chart)
            );

            CREATE TABLE IF NOT EXISTS yyb_tag_stats (
              date         TEXT    NOT NULL,
              chart        TEXT    NOT NULL,
              tag          TEXT    NOT NULL,
              game_count   INTEGER NOT NULL,
              avg_rank     REAL,
              top10_count  INTEGER NOT NULL DEFAULT 0,
              new_entries  INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY (date, chart, tag)
            );

            CREATE TABLE IF NOT EXISTS media_cache (
              source_url   TEXT    NOT NULL UNIQUE,
              sha256       TEXT    NOT NULL,
              mime         TEXT,
              byte_size    INTEGER NOT NULL,
              stored_at    TEXT    NOT NULL,
              expires_at   TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_media_cache_sha ON media_cache(sha256);
            CREATE INDEX IF NOT EXISTS idx_media_cache_expires ON media_cache(expires_at);
            """
        )
        for col, typedef in (
            ("genre_major", "TEXT"),
            ("genre_minor", "TEXT"),
        ):
            try:
                conn.execute(f"ALTER TABLE games ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS gameplay_tags (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              slug          TEXT NOT NULL UNIQUE,
              name          TEXT NOT NULL,
              parent_id     INTEGER REFERENCES gameplay_tags(id),
              description   TEXT,
              created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS game_gameplay_tags (
              appid         TEXT NOT NULL REFERENCES games(appid) ON DELETE CASCADE,
              tag_id        INTEGER NOT NULL REFERENCES gameplay_tags(id) ON DELETE CASCADE,
              role          TEXT,
              evidence      TEXT,
              source        TEXT NOT NULL DEFAULT 'manual',
              updated_by    TEXT,
              updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
              PRIMARY KEY (appid, tag_id)
            );

            CREATE TABLE IF NOT EXISTS game_monetization (
              appid                 TEXT PRIMARY KEY REFERENCES games(appid) ON DELETE CASCADE,
              monetization_model    TEXT NOT NULL DEFAULT 'unknown',
              mix_note              TEXT,
              confidence            REAL,
              evidence_summary      TEXT,
              ad_placement_notes    TEXT,
              source                TEXT NOT NULL DEFAULT 'manual',
              updated_by            TEXT,
              updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS virality_assumptions (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              appid         TEXT NOT NULL REFERENCES games(appid) ON DELETE CASCADE,
              channels      TEXT,
              hypothesis    TEXT NOT NULL,
              evidence      TEXT,
              confidence    REAL,
              source        TEXT NOT NULL DEFAULT 'manual',
              updated_by    TEXT,
              updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_ggt_appid ON game_gameplay_tags(appid);
            CREATE INDEX IF NOT EXISTS idx_virality_appid ON virality_assumptions(appid);
            """
        )
