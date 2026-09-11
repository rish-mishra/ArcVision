"""
Video 4 one-shot evaluation: RF-DETR ball AND rim frame coverage + mean
confidence, same methodology as eval_coverage_v1v2v3.py (that script is
left untouched -- this is a new, separate file, not an edit, since V1-V3
are pre-committed reference videos and V4 is a fresh one-shot eval).
Uses the production checkpoint/config exactly as configured -- no
overrides, no threshold changes.

Usage:
    .venv\\Scripts\\python scripts\\eval_coverage_v4.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CONFIG, MODELS_DIR
from app.pipeline.video_io import FrameReader, validate_video
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector

ROOT = Path(__file__).resolve().parent.parent
VIDEO_PATH = ROOT / "real_test_04.mov"


def main():
    checkpoint = MODELS_DIR / CONFIG.ball_rim_rfdetr.checkpoint_name
    print(f"Checkpoint (production, unmodified): {checkpoint}")
    rf = RFDETRBallRimDetector(str(checkpoint), CONFIG.ball_rim_rfdetr.confidence_floor)
    rf.warmup()

    meta = validate_video(VIDEO_PATH)
    reader = FrameReader(meta)
    frames = list(reader)
    total = len(frames)

    ball_frames = 0
    ball_conf_sum = 0.0
    rim_frames = 0
    rim_conf_sum = 0.0
    for af in frames:
        raw = rf.predict_raw(af.image)
        balls = rf.extract_ball_detections(raw, af.frame_index, af.timestamp_sec)
        rims = rf.extract_rim_candidates(raw)
        if balls:
            ball_frames += 1
            ball_conf_sum += max(d.confidence for d in balls)
        if rims:
            rim_frames += 1
            rim_conf_sum += max(c[3] for c in rims)

    print(f"V4 ({total} frames): "
          f"ball coverage={ball_frames/total*100:.1f}% mean_conf={ball_conf_sum/max(1,ball_frames):.3f} | "
          f"rim coverage={rim_frames/total*100:.1f}% mean_conf={rim_conf_sum/max(1,rim_frames):.3f}")


if __name__ == "__main__":
    main()
