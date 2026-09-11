"""
Overnight full-production regression run for V1/V2/V3/V4 under the current
FROZEN production pipeline (post enrichment-clamp fix, post apex_height_norm
fix, outcome_detector.py untouched throughout). Runs detection + analytics +
annotated/diagnostic video rendering exactly as the real upload path would,
via run_pipeline() + the same renderer functions job_manager.py calls --
does not touch the database (no repository.save_session_result call), does
not modify any production file. Read-only regression check.

Usage:
    .venv\\Scripts\\python scripts\\overnight_v1v2v3v4_regression.py
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.annotation.diagnostic_renderer import render_diagnostic_video
from app.annotation.renderer import render_annotated_video
from app.pipeline.orchestrator import run_pipeline

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "diagnostics" / "overnight_regression"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIDEOS = {
    "V1": ROOT / "real_test_01.mp4.mov",
    "V2": ROOT / "real_test_02.mp4.mov",
    "V3": ROOT / "real_test_03.mov",
    "V4": ROOT / "real_test_04.mov",
}


def main():
    summary = {}
    for name, video_path in VIDEOS.items():
        print(f"\n{'=' * 70}\n{name}: {video_path.name}\n{'=' * 70}", flush=True)
        try:
            result = run_pipeline(video_path)
        except Exception as e:
            print(f"{name}: PIPELINE FAILED: {e}")
            traceback.print_exc()
            summary[name] = {"error": str(e)}
            continue

        video_out_dir = OUT_DIR / name
        video_out_dir.mkdir(parents=True, exist_ok=True)
        annotated_path = video_out_dir / "annotated.mp4"
        diagnostic_path = video_out_dir / "diagnostic.mp4"
        annotated_ok = diagnostic_ok = False
        try:
            render_annotated_video(video_path, result.video_meta, result.shots, result.hoop,
                                     result.pose_frames, result.ball_observations, annotated_path)
            annotated_ok = annotated_path.exists() and annotated_path.stat().st_size > 0
        except Exception as e:
            print(f"{name}: annotated render FAILED: {e}")
        try:
            render_diagnostic_video(video_path, result.video_meta, result.shots, result.hoop,
                                      result.pose_frames, result.ball_observations, diagnostic_path)
            diagnostic_ok = diagnostic_path.exists() and diagnostic_path.stat().st_size > 0
        except Exception as e:
            print(f"{name}: diagnostic render FAILED: {e}")

        shots_summary = [{
            "shot_index": s.shot_index, "outcome": s.outcome.value, "confidence": s.outcome_confidence,
            "reason": s.outcome_reason, "release_time_sec": s.release_time_sec,
            "apex_height_norm": s.trajectory.apex_height_norm,
        } for s in result.shots]

        coaching = result.coaching
        entry = {
            "n_shots": len(result.shots),
            "outcomes": [s.outcome.value for s in result.shots],
            "shots_detail": shots_summary,
            "session_summary": {
                "total_shots_detected": result.session_summary.total_shots_detected,
                "made": result.session_summary.made, "missed": result.session_summary.missed,
                "unknown": result.session_summary.unknown, "excluded": result.session_summary.excluded,
                "shooting_percentage": result.session_summary.shooting_percentage,
                "warnings": result.session_summary.warnings,
            },
            "hoop": {"rim_center_x": result.hoop.rim_center_x, "rim_center_y": result.hoop.rim_center_y,
                      "rim_radius_px": result.hoop.rim_radius_px, "confidence": result.hoop.confidence,
                      "votes": result.hoop.votes} if result.hoop else None,
            "pipeline_warnings": result.warnings,
            "coaching": {
                "eligible": coaching.eligible if coaching else None,
                "confidence": coaching.confidence if coaching else None,
                "strength": coaching.strength.metric_key if coaching and coaching.strength else None,
                "priority": coaching.priority.metric_key if coaching and coaching.priority else None,
            } if coaching else None,
            "annotated_rendered": annotated_ok,
            "diagnostic_rendered": diagnostic_ok,
            "analysis_fps": result.analysis_fps,
            "analysis_size": result.analysis_size,
        }
        summary[name] = entry
        print(json.dumps(entry, indent=2))
        (OUT_DIR / f"{name}_result.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")

    (OUT_DIR / "ALL_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n\nAll done. Summary saved to {OUT_DIR}/ALL_SUMMARY.json")


if __name__ == "__main__":
    main()
