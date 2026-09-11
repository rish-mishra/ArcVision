"""SQLite connection management and schema creation."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    video_duration_sec REAL,
    analysis_json TEXT,
    annotated_video_path TEXT,
    diagnostic_video_path TEXT
);

CREATE TABLE IF NOT EXISTS shots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    shot_index INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    outcome_confidence REAL,
    start_time_sec REAL,
    release_time_sec REAL,
    end_time_sec REAL,
    shot_json TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_shots_session ON shots(session_id);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
