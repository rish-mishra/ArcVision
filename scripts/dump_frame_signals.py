"""
Diagnostic dump: full per-frame ball+wrist signal stream (as seen by
release_event_detector.py) for one video, to a CSV. Used for the A/B
architectural investigation -- not part of the pipeline.

Usage:
    .venv\\Scripts\\python scripts\\dump_frame_signals.py path\\to\\video.mp4 out.csv
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.orchestrator import _estimate_global_torso_scale_px, build_frame_signals
from scripts.shot_timeline_debug import run_detection_only


def main():
    video_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2]).resolve()
    print(f"Running detection pass on {video_path}...")
    meta, frames_list, pose_frames, ball_observations, hoop, w, h = run_detection_only(video_path)
    frame_signals = build_frame_signals(frames_list, pose_frames, ball_observations, w, h)
    torso_scale_px = _estimate_global_torso_scale_px(pose_frames, w, h)
    radius_by_frame = {o.frame_index: o.radius_px for o in ball_observations}

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["frame_index", "timestamp_sec", "ball_x", "ball_y", "ball_radius_px", "ball_source",
                          "left_wrist_x", "left_wrist_y", "right_wrist_x", "right_wrist_y",
                          "torso_scale_px"])
        for fs in frame_signals:
            writer.writerow([
                fs.frame_index, round(fs.timestamp_sec, 4),
                fs.ball_x, fs.ball_y, radius_by_frame.get(fs.frame_index),
                getattr(fs.ball_source, "value", fs.ball_source),
                fs.left_wrist_xy[0] if fs.left_wrist_xy else None,
                fs.left_wrist_xy[1] if fs.left_wrist_xy else None,
                fs.right_wrist_xy[0] if fs.right_wrist_xy else None,
                fs.right_wrist_xy[1] if fs.right_wrist_xy else None,
                round(torso_scale_px, 2),
            ])
    print(f"Wrote {len(frame_signals)} rows to {out_path}")


if __name__ == "__main__":
    main()
