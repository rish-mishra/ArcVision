"""
Job-lifecycle / orphan-recovery tests: a session must never stay stuck at
'processing' forever after the backend that was processing it disappears
(crash, kill, restart). These exercise app/storage/repository.py's
reconciliation function directly, JobManager's use of it at construction
time, and the API surface (created_at exposure, 'interrupted' handled like
'failed' for /results). Uses the real configured DB, same convention as
tests/test_api.py -- each test creates its own uniquely-named session(s)
and cleans up via delete_session in a finally block.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.pipeline.job_manager import JobManager
from app.storage import repository
from app.storage.db import db_session

client = TestClient(app)


def _sid() -> str:
    return f"test_lifecycle_{uuid.uuid4().hex[:10]}"


def test_reconcile_marks_stale_processing_as_interrupted():
    session_id = _sid()
    repository.create_pending_session(session_id, "stale.mp4")
    try:
        reconciled = repository.reconcile_orphaned_processing_sessions()
        assert reconciled >= 1
        row = repository.get_session(session_id)
        assert row["status"] == "interrupted"
        assert row["error_message"]  # a real, non-empty explanation, not silently blank
    finally:
        repository.delete_session(session_id)


def test_reconcile_does_not_touch_completed_or_failed_sessions():
    completed_id, failed_id = _sid(), _sid()
    repository.create_pending_session(completed_id, "done.mp4")
    repository.create_pending_session(failed_id, "broken.mp4")
    try:
        with db_session() as conn:
            conn.execute("UPDATE sessions SET status='completed' WHERE session_id=?", (completed_id,))
        repository.mark_session_failed(failed_id, "a real pipeline exception message")

        repository.reconcile_orphaned_processing_sessions()

        assert repository.get_session(completed_id)["status"] == "completed"
        failed_row = repository.get_session(failed_id)
        assert failed_row["status"] == "failed"  # not overwritten to 'interrupted'
        assert failed_row["error_message"] == "a real pipeline exception message"
    finally:
        repository.delete_session(completed_id)
        repository.delete_session(failed_id)


def test_job_manager_reconciles_orphaned_sessions_on_construction():
    """A fresh JobManager (simulating a freshly-started process) must
    reconcile any pre-existing 'processing' row before it could possibly
    have submitted anything of its own -- see the docstring on
    reconcile_orphaned_processing_sessions for why that ordering is what
    makes this provably safe against misclassifying a real active job."""
    session_id = _sid()
    repository.create_pending_session(session_id, "orphan.mp4")
    manager = None
    try:
        manager = JobManager(max_workers=1)
        row = repository.get_session(session_id)
        assert row["status"] == "interrupted"
    finally:
        if manager is not None:
            manager._executor.shutdown(wait=False)
        repository.delete_session(session_id)


def test_list_sessions_includes_error_message():
    session_id = _sid()
    repository.create_pending_session(session_id, "err.mp4")
    try:
        repository.mark_session_failed(session_id, "boom")
        sessions = repository.list_sessions()
        match = next(s for s in sessions if s["session_id"] == session_id)
        assert match["status"] == "failed"
        assert match["error_message"] == "boom"
    finally:
        repository.delete_session(session_id)


def test_status_endpoint_includes_created_at():
    session_id = _sid()
    repository.create_pending_session(session_id, "fallback.mp4")
    try:
        resp = client.get(f"/api/sessions/{session_id}/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_at"]
        assert body["status"] == "processing"
    finally:
        repository.delete_session(session_id)


def test_results_endpoint_treats_interrupted_like_failed_not_still_processing():
    session_id = _sid()
    repository.create_pending_session(session_id, "interrupted.mp4")
    try:
        repository.reconcile_orphaned_processing_sessions()
        assert repository.get_session(session_id)["status"] == "interrupted"

        resp = client.get(f"/api/sessions/{session_id}/results")
        # Must be a clear "this failed" response (422), never the misleading
        # "still processing" 409 an 'interrupted' session used to fall into.
        assert resp.status_code == 422
        assert "message" in resp.json()["detail"]
    finally:
        repository.delete_session(session_id)
