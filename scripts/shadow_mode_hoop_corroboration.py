"""
Architecture C, Experiment 1: trajectory_shot_detector.py's confirmed
candidates, tiered by hoop_corroboration.py. Prints every confirmed
candidate with its hoop tier and distance, plus discarded arms for
reference. Changes nothing in production.

Usage:
    .venv\\Scripts\\python scripts\\shadow_mode_hoop_corroboration.py path\\to\\video.mp4
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.events.hoop_corroboration import corroborate
from app.events.trajectory_shot_detector import detect_shot_attempts
from app.pipeline.orchestrator import _estimate_global_torso_scale_px, build_frame_signals
from scripts.shot_timeline_debug import run_detection_only


def main():
    video_path = Path(sys.argv[1]).resolve()
    print(f"Running detection pass on {video_path}...")
    meta, frames_list, pose_frames, ball_observations, hoop, w, h = run_detection_only(video_path)

    frame_signals = build_frame_signals(frames_list, pose_frames, ball_observations, w, h)
    torso_scale_px = _estimate_global_torso_scale_px(pose_frames, w, h)

    candidates = detect_shot_attempts(frame_signals, torso_scale_px)
    confirmed = [c for c in candidates if c.confirmed]
    discarded = [c for c in candidates if not c.confirmed]

    n_corrob = 0
    n_no_evidence = 0
    print(f"\n=== {len(confirmed)} confirmed trajectory candidates, hoop-tiered ===")
    for c in confirmed:
        r = corroborate(c, frame_signals, hoop)
        if r.tier == "hoop_corroborated":
            n_corrob += 1
        elif r.tier == "no_hoop_evidence":
            n_no_evidence += 1
        print(f"  arm_frame={c.arm_frame} t={c.arm_timestamp_sec:.3f}s path={c.arm_path} "
              f"height_gained={c.height_gained_norm} tier={r.tier} dist_rim_radii={r.min_distance_rim_radii}")

    print(f"\nSummary: {n_corrob} hoop_corroborated, {n_no_evidence} no_hoop_evidence, "
          f"{len(confirmed) - n_corrob - n_no_evidence} no_hoop_location")
    print(f"Discarded (unconfirmed) arms: {len(discarded)}")

    print(f"\nHoop: center=({hoop.rim_center_x:.0f},{hoop.rim_center_y:.0f}) r={hoop.rim_radius_px:.0f} "
          f"conf={hoop.confidence}" if hoop else "\nHoop: not found")
    print(f"torso_scale_px={torso_scale_px:.1f}")


if __name__ == "__main__":
    main()
