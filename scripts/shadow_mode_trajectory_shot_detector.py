"""
Migration-plan Architecture C evaluation: runs the trajectory-primary shot
attempt detector (trajectory_shot_detector.py) on one video and prints
every candidate (arm), confirmed or discarded, alongside the same
detection/pose pass's TRANSITION baseline for reference. Changes nothing
in production -- this script only reads.

Usage:
    .venv\\Scripts\\python scripts\\shadow_mode_trajectory_shot_detector.py path\\to\\video.mp4
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.events.release_event_detector import detect_release_events
from app.events.trajectory_shot_detector import detect_shot_attempts
from app.pipeline.orchestrator import _estimate_global_torso_scale_px, build_frame_signals
from scripts.shot_timeline_debug import run_detection_only


def main():
    video_path = Path(sys.argv[1]).resolve()
    print(f"Running detection pass on {video_path}...")
    meta, frames_list, pose_frames, ball_observations, hoop, w, h = run_detection_only(video_path)

    frame_signals = build_frame_signals(frames_list, pose_frames, ball_observations, w, h)
    torso_scale_px = _estimate_global_torso_scale_px(pose_frames, w, h)

    baseline_events = detect_release_events(frame_signals, torso_scale_px)
    trajectory_candidates = detect_shot_attempts(frame_signals, torso_scale_px)
    confirmed = [c for c in trajectory_candidates if c.confirmed]
    discarded = [c for c in trajectory_candidates if not c.confirmed]

    print(f"\n=== TRANSITION baseline (release_event_detector): {len(baseline_events)} candidate(s) ===")
    for e in baseline_events:
        print(f"  frame={e.release_frame} t={e.release_timestamp_sec:.3f}s path={e.path}")

    print(f"\n=== TRAJECTORY (Architecture C): {len(trajectory_candidates)} arm(s), "
          f"{len(confirmed)} confirmed, {len(discarded)} discarded ===")
    for c in confirmed:
        print(f"  CONFIRMED arm_frame={c.arm_frame} t={c.arm_timestamp_sec:.3f}s path={c.arm_path} "
              f"apex_frame={c.apex_frame} apex_t={c.apex_timestamp_sec:.3f}s "
              f"rise_steps={c.rise_steps} height_gained_norm={c.height_gained_norm} "
              f"descent_frame={c.descent_confirmed_frame}")
    for c in discarded:
        print(f"  discarded  arm_frame={c.arm_frame} t={c.arm_timestamp_sec:.3f}s path={c.arm_path} "
              f"reason={c.discard_reason} rise_steps={c.rise_steps} apex_frame={c.apex_frame}")

    print(f"\nHoop: center=({hoop.rim_center_x:.0f},{hoop.rim_center_y:.0f}) r={hoop.rim_radius_px:.0f} "
          f"conf={hoop.confidence}" if hoop else "\nHoop: not found")
    print(f"torso_scale_px={torso_scale_px:.1f}")


if __name__ == "__main__":
    main()
