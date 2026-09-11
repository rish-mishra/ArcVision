"""
In-process background job runner for video analysis. A session is
processed on a worker thread (video analysis is CPU/GPU-bound, not
I/O-bound, and this is a single-user local app, so a simple thread pool is
the right amount of infrastructure -- no external queue/broker needed).
"""
from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from app.annotation.diagnostic_renderer import render_diagnostic_video
from app.annotation.renderer import render_annotated_video
from app.config import OUTPUTS_DIR
from app.logging_config import get_logger
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.video_io import VideoValidationError
from app.storage import repository

log = get_logger("pipeline.job_manager")

_STAGE_LABELS = {
    "validating_video": "Validating video",
    "analyzing_player_and_ball": "Tracking player and basketball",
    "locating_hoop": "Locating hoop",
    "detecting_shots": "Detecting shot attempts",
    "locating_ball_near_hoop": "Refining ball position near hoop",
    "analyzing_mechanics": "Analyzing shooting mechanics",
    "comparing_attempts": "Comparing makes vs. misses",
    "finalizing": "Finalizing results",
    "rendering_replay": "Generating annotated replay",
}


@dataclass
class JobState:
    session_id: str
    status: str = "queued"  # queued | processing | completed | failed | interrupted
    stage: str = "queued"
    stage_label: str = "Queued"
    progress: float = 0.0
    error: Optional[str] = None
    error_code: Optional[str] = None
    # ISO8601 UTC timestamp captured once at submit() time -- lets the
    # frontend show real elapsed processing time (never a fabricated ETA)
    # and survives a page refresh, since it's re-derived from the server on
    # every status poll rather than a client-side clock that would reset.
    created_at: str = ""


class JobManager:
    def __init__(self, max_workers: int = 1):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: Dict[str, JobState] = {}
        self._lock = threading.Lock()
        # Must run before this instance accepts any submit() call -- see
        # repository.reconcile_orphaned_processing_sessions's docstring for
        # why that ordering is what makes this safe (nothing this process
        # submits can possibly be in the database as 'processing' yet).
        reconciled = repository.reconcile_orphaned_processing_sessions()
        if reconciled:
            log.warning("Reconciled %d session(s) left stuck in 'processing' from a previous run "
                         "(marked 'interrupted').", reconciled)

    def submit(self, video_path: Path, original_filename: str) -> str:
        session_id = uuid.uuid4().hex[:16]
        repository.create_pending_session(session_id, original_filename)
        with self._lock:
            self._jobs[session_id] = JobState(
                session_id=session_id,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        self._executor.submit(self._run, session_id, video_path)
        return session_id

    def get(self, session_id: str) -> Optional[JobState]:
        with self._lock:
            return self._jobs.get(session_id)

    def _progress(self, session_id: str, stage: str, pct: float) -> None:
        with self._lock:
            job = self._jobs.get(session_id)
            if job:
                job.stage = stage
                job.stage_label = _STAGE_LABELS.get(stage, stage)
                job.progress = pct
                job.status = "processing"

    def _run(self, session_id: str, video_path: Path) -> None:
        try:
            result = run_pipeline(video_path, lambda stage, pct: self._progress(session_id, stage, pct))

            self._progress(session_id, "rendering_replay", 0.97)
            annotated_path = OUTPUTS_DIR / session_id / "annotated.mp4"
            diagnostic_path = OUTPUTS_DIR / session_id / "diagnostic.mp4"
            annotated_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                render_annotated_video(video_path, result.video_meta, result.shots, result.hoop,
                                         result.pose_frames, result.ball_observations, annotated_path)
                render_diagnostic_video(video_path, result.video_meta, result.shots, result.hoop,
                                          result.pose_frames, result.ball_observations, diagnostic_path)
            except Exception:
                log.exception("Annotated/diagnostic video rendering failed for session %s", session_id)
                annotated_path, diagnostic_path = None, None

            repository.save_session_result(
                session_id, result,
                str(annotated_path) if annotated_path and annotated_path.exists() else None,
                str(diagnostic_path) if diagnostic_path and diagnostic_path.exists() else None,
            )
            with self._lock:
                job = self._jobs[session_id]
                job.status = "completed"
                job.stage = "completed"
                job.stage_label = "Complete"
                job.progress = 1.0

        except VideoValidationError as e:
            log.warning("Video validation failed for session %s: %s", session_id, e)
            repository.mark_session_failed(session_id, str(e))
            with self._lock:
                job = self._jobs[session_id]
                job.status, job.error, job.error_code = "failed", str(e), e.code

        except Exception as e:
            log.exception("Pipeline failed for session %s", session_id)
            repository.mark_session_failed(session_id, str(e))
            with self._lock:
                job = self._jobs[session_id]
                job.status, job.error, job.error_code = "failed", str(e), "internal_error"


job_manager = JobManager(max_workers=1)
