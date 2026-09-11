"""Thin data-access layer over SQLite for sessions and shots."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from app.storage.db import db_session, init_db
from app.storage.serializers import serialize_session_result

init_db()


def create_pending_session(session_id: str, original_filename: str) -> None:
    with db_session() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, created_at, original_filename, status) VALUES (?, ?, ?, ?)",
            (session_id, datetime.now(timezone.utc).isoformat(), original_filename, "processing"),
        )


def mark_session_failed(session_id: str, error_message: str) -> None:
    with db_session() as conn:
        conn.execute(
            "UPDATE sessions SET status = 'failed', error_message = ? WHERE session_id = ?",
            (error_message, session_id),
        )


_ORPHANED_SESSION_MESSAGE = (
    "Analysis was interrupted before it finished -- the analysis service restarted or stopped "
    "unexpectedly while this session was processing. Please try uploading this video again."
)


def reconcile_orphaned_processing_sessions() -> int:
    """
    Called exactly once, at process startup, before this process's JobManager
    accepts any submissions (see JobManager.__init__). A session is only ever
    processed by a plain in-process worker thread with no persistence
    mechanism across a process boundary -- there is no queue, no external
    worker, nothing that could still be "actively running" a session from a
    process that no longer exists. So if a row is already 'processing' at
    the exact moment a fresh process starts (before that process has
    submitted anything of its own), the process that WAS running it is
    gone -- crashed, killed, or the machine restarted -- before it ever
    reached 'completed' or 'failed'. Marks those rows 'interrupted' (not
    'failed', which would incorrectly imply a real pipeline exception was
    caught) so History can distinguish "this session's process vanished"
    from both "still running" and "a real error occurred while processing."
    Returns the number of sessions reconciled, for startup logging.
    """
    with db_session() as conn:
        cur = conn.execute(
            "UPDATE sessions SET status = 'interrupted', error_message = ? WHERE status = 'processing'",
            (_ORPHANED_SESSION_MESSAGE,),
        )
        return cur.rowcount


def save_session_result(session_id: str, result, annotated_video_path: Optional[str],
                          diagnostic_video_path: Optional[str]) -> None:
    payload = serialize_session_result(result)
    with db_session() as conn:
        conn.execute(
            """UPDATE sessions SET status='completed', video_duration_sec=?, analysis_json=?,
               annotated_video_path=?, diagnostic_video_path=? WHERE session_id=?""",
            (result.video_meta.duration_sec, json.dumps(payload), annotated_video_path,
             diagnostic_video_path, session_id),
        )
        for shot in result.shots:
            conn.execute(
                """INSERT INTO shots (session_id, shot_index, outcome, outcome_confidence,
                   start_time_sec, release_time_sec, end_time_sec, shot_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, shot.shot_index, shot.outcome.value, shot.outcome_confidence,
                 shot.start_time_sec, shot.release_time_sec, shot.end_time_sec,
                 json.dumps(payload["shots"][shot.shot_index - 1])),
            )


def get_session(session_id: str) -> Optional[dict]:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(row) if row else None


def list_sessions() -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT session_id, created_at, original_filename, status, video_duration_sec, error_message "
            "FROM sessions ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def delete_session(session_id: str) -> None:
    with db_session() as conn:
        conn.execute("DELETE FROM shots WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
