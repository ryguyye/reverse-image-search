import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    image_url TEXT,
    image_filename TEXT,
    cadence_minutes INTEGER NOT NULL,
    webhook_url TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_run_at TEXT,
    CHECK (image_url IS NOT NULL OR image_filename IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS seen_matches (
    watch_id INTEGER NOT NULL,
    canonical_url TEXT NOT NULL,
    domain TEXT,
    title TEXT,
    thumbnail_url TEXT,
    sources TEXT,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (watch_id, canonical_url),
    FOREIGN KEY (watch_id) REFERENCES watches(id) ON DELETE CASCADE
);
"""


def init() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
