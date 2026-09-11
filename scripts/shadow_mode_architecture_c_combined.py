"""
Architecture C, combined evaluation: trajectory_shot_detector's confirmed
candidates, tiered by BOTH hoop_corroboration and pose_at_arm_corroboration.
Prints a combined confidence bucket per candidate:

  high   = hoop_corroborated AND (pose_corroborated OR no_pose_data)
  medium = hoop_corroborated AND pose says no_pose_evidence
  low    = no_hoop_evidence (regardless of pose)

Neither corroboration layer is ever required for the underlying candidate
to exist -- this script only labels already-confirmed candidates for
evaluation. Changes nothing in production.

Usage:
    .venv\\Scripts\\python scripts\\shadow_mode_architecture_c_combined.py path\\to\\video.mp4
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.events.hoop_corroboration import corroborate as corroborate_hoop
from app.events.pose_at_arm_corroboration import corroborate as corroborate_pose
from app.events.trajectory_shot_detector import detect_shot_attempts
from app.pipeline.orchestrator import _estimate_global_torso_scale_px, build_frame_signals
from scripts.shot_timeline_debug import run_detection_only


def bucket(hoop_tier: str, pose_tier: str) -> str:
    if hoop_tier != "hoop_corroborated":
        return "low"
    if pose_tier == "no_pose_evidence":
        return "medium"
    return "high"  # pose_corroborated or no_pose_data


def main():
    video_path = Path(sys.argv[1]).resolve()
    checkpoint_override = os.environ.get("RFDETR_CHECKPOINT_OVERRIDE")
    checkpoint_path = Path(checkpoint_override) if checkpoint_override else None
    print(f"Running detection pass on {video_path}"
          f"{f' (checkpoint override: {checkpoint_path})' if checkpoint_path else ''}...")
    meta, frames_list, pose_frames, ball_observations, hoop, w, h = run_detection_only(video_path, checkpoint_path)

    frame_signals = build_frame_signals(frames_list, pose_frames, ball_observations, w, h)
    torso_scale_px = _estimate_global_torso_scale_px(pose_frames, w, h)

    candidates = detect_shot_attempts(frame_signals, torso_scale_px)
    confirmed = [c for c in candidates if c.confirmed]
    discarded = [c for c in candidates if not c.confirmed]

    counts = {"high": 0, "medium": 0, "low": 0}
    print(f"\n=== {len(confirmed)} confirmed trajectory candidates, combined-tiered ===")
    for c in confirmed:
        h_res = corroborate_hoop(c, frame_signals, hoop)
        p_res = corroborate_pose(c, frame_signals, torso_scale_px)
        b = bucket(h_res.tier, p_res.tier)
        counts[b] += 1
        print(f"  [{b:6s}] arm_frame={c.arm_frame} t={c.arm_timestamp_sec:.3f}s path={c.arm_path} "
              f"height_gained={c.height_gained_norm} hoop={h_res.tier}({h_res.min_distance_rim_radii}) "
              f"pose={p_res.tier}({p_res.min_distance_norm})")

    print(f"\nSummary: high={counts['high']} medium={counts['medium']} low={counts['low']}")
    print(f"Discarded (unconfirmed) arms: {len(discarded)}")
    for c in discarded:
        print(f"  discarded arm_frame={c.arm_frame} t={c.arm_timestamp_sec:.3f}s reason={c.discard_reason}")

    print(f"\nHoop: center=({hoop.rim_center_x:.0f},{hoop.rim_center_y:.0f}) r={hoop.rim_radius_px:.0f} "
          f"conf={hoop.confidence}" if hoop else "\nHoop: not found")
    print(f"torso_scale_px={torso_scale_px:.1f}")


if __name__ == "__main__":
    main()
