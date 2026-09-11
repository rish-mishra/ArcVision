"""
Creates a fresh, real, DB-backed session for arcvision_demo_final.mov under
the CURRENT production code (post-segmentation-fix: 11/11 shots, 0 FP, 0 FN
-- see docs/SHOWCASE_SEGMENTATION_FIX.md), for scripts/export_demo.py to
export.

The existing stored session (29c7e751775e4f20) predates this session's
segmentation fix and still reflects the old 13-window (2 false-positive)
behavior -- confirmed by export_demo.py's own shot-count safety check
refusing to proceed. This script does NOT take a shortcut: it calls the
exact same functions app/pipeline/job_manager.py's JobManager._run() calls
for a real upload (run_pipeline, render_annotated_video,
render_diagnostic_video, repository.create_pending_session/save_session_result)
directly, in-process, instead of through the async HTTP job queue -- the
only difference from a real upload is not going through the web server.

Usage:
    .venv\\Scripts\\python scripts\\create_final_demo_session.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.annotation.diagnostic_renderer import render_diagnostic_video
from app.annotation.renderer import render_annotated_video
from app.config import OUTPUTS_DIR
from app.pipeline.orchestrator import run_pipeline
from app.storage import repository

VIDEO_PATH = Path("arcvision_demo_final.mov").resolve()


def main():
    session_id = uuid.uuid4().hex[:16]
    print(f"Creating session {session_id} for {VIDEO_PATH.name}...")
    repository.create_pending_session(session_id, VIDEO_PATH.name)

    def progress(stage, pct):
        print(f"  [{pct*100:5.1f}%] {stage}", flush=True)

    result = run_pipeline(VIDEO_PATH, progress)
    print(f"Detected {len(result.shots)} shots.")
    for s in result.shots:
        print(f"  shot {s.shot_index}: release_t={s.release_time_sec:.2f} outcome={s.outcome.value}({s.outcome_confidence:.2f})")

    annotated_path = OUTPUTS_DIR / session_id / "annotated.mp4"
    diagnostic_path = OUTPUTS_DIR / session_id / "diagnostic.mp4"
    annotated_path.parent.mkdir(parents=True, exist_ok=True)
    print("Rendering annotated video...")
    render_annotated_video(VIDEO_PATH, result.video_meta, result.shots, result.hoop,
                             result.pose_frames, result.ball_observations, annotated_path)
    print("Rendering diagnostic video...")
    render_diagnostic_video(VIDEO_PATH, result.video_meta, result.shots, result.hoop,
                              result.pose_frames, result.ball_observations, diagnostic_path)

    repository.save_session_result(
        session_id, result,
        str(annotated_path) if annotated_path.exists() else None,
        str(diagnostic_path) if diagnostic_path.exists() else None,
    )
    print(f"\nSaved session {session_id} (status=completed) with {len(result.shots)} shots.")
    print(f"NEXT STEP: update DEMO_SESSION_ID in scripts/export_demo.py to \"{session_id}\" and re-run it.")


if __name__ == "__main__":
    main()
