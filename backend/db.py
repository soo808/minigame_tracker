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
            """
        )
