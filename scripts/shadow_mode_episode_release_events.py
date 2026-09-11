"""
Migration-plan follow-up: runs the PRODUCTION ShotStateMachine, the
TRANSITION-baseline shadow detector (release_event_detector.py), and the
temporal-possession-EPISODE shadow prototype (episode_release_detector.py)
side by side on the same detection/pose pass for one video. Changes nothing
in production -- this script only reads.

Usage:
    .venv\\Scripts\\python scripts\\shadow_mode_episode_release_events.py path\\to\\video.mp4
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.events.episode_release_detector import detect_release_events_episode
from app.events.release_event_detector import detect_release_events
from app.events.shot_state_machine import detect_shots
from app.pipeline.orchestrator import _estimate_global_torso_scale_px, build_frame_signals
from scripts.shot_timeline_debug import run_detection_only


def main():
    video_path = Path(sys.argv[1]).resolve()
    print(f"Running detection pass on {video_path}...")
    meta, frames_list, pose_frames, ball_observations, hoop, w, h = run_detection_only(video_path)

    frame_signals = build_frame_signals(frames_list, pose_frames, ball_observations, w, h)
    torso_scale_px = _estimate_global_torso_scale_px(pose_frames, w, h)

    existing_windows = detect_shots(frame_signals)
    baseline_events = detect_release_events(frame_signals, torso_scale_px)
    episode_events = detect_release_events_episode(frame_signals, torso_scale_px)

    print(f"\n=== EXISTING production ShotStateMachine: {len(existing_windows)} shot window(s) ===")
    for wdw in existing_windows:
        rel = wdw.release_candidate_frame
        rel_t = next((f.timestamp_sec for f in frame_signals if f.frame_index == rel), None) if rel is not None else None
        print(f"  shot {wdw.shot_index}: start={wdw.start_frame} load={wdw.load_start_frame} "
              f"upward={wdw.upward_start_frame} release={rel} (t={rel_t:.3f}s)" if rel_t is not None else
              f"  shot {wdw.shot_index}: start={wdw.start_frame} release=None")
        if wdw.warnings:
            print(f"    warnings: {wdw.warnings}")

    print(f"\n=== TRANSITION baseline (release_event_detector): {len(baseline_events)} candidate(s) ===")
    for e in baseline_events:
        print(f"  frame={e.release_frame} t={e.release_timestamp_sec:.3f}s path={e.path} "
              f"confidence={e.confidence} evidence={e.evidence}")

    print(f"\n=== EPISODE prototype (episode_release_detector): {len(episode_events)} candidate(s) ===")
    for e in episode_events:
        print(f"  frame={e.release_frame} t={e.release_timestamp_sec:.3f}s path={e.path} "
              f"confidence={e.confidence} evidence={e.evidence}")

    print(f"\nHoop: center=({hoop.rim_center_x:.0f},{hoop.rim_center_y:.0f}) r={hoop.rim_radius_px:.0f} "
          f"conf={hoop.confidence}" if hoop else "\nHoop: not found")
    print(f"torso_scale_px={torso_scale_px:.1f}")


if __name__ == "__main__":
    main()
