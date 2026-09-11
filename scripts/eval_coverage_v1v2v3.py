"""
A/B evaluation, item 2+3 of the v2-hardneg report: RF-DETR ball AND rim
frame coverage + mean confidence across V1/V2/V3, for whichever checkpoint
RFDETR_CHECKPOINT_OVERRIDE points at (env var; omit for the production v1
checkpoint). Independent of the tracker/state machine -- raw per-frame
detection quality only. Not a full re-run of benchmark_ball_rim_detectors.py
(that script stays as the "existing detector benchmark" A/B item, run
separately with the same env var); this is the simpler, 3-video coverage
check requested alongside it.

Usage:
    RFDETR_CHECKPOINT_OVERRIDE=path\\to\\ckpt.pth .venv\\Scripts\\python scripts\\eval_coverage_v1v2v3.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CONFIG, MODELS_DIR
from app.pipeline.video_io import FrameReader, validate_video
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector

ROOT = Path(__file__).resolve().parent.parent
VIDEOS = {
    "V1": ROOT / "real_test_01.mp4.mov",
    "V2": ROOT / "real_test_02.mp4.mov",
    "V3": ROOT / "real_test_03.mov",
}


def main():
    override = os.environ.get("RFDETR_CHECKPOINT_OVERRIDE")
    checkpoint = Path(override) if override else (MODELS_DIR / CONFIG.ball_rim_rfdetr.checkpoint_name)
    print(f"Checkpoint: {checkpoint}")
    rf = RFDETRBallRimDetector(str(checkpoint), CONFIG.ball_rim_rfdetr.confidence_floor)
    rf.warmup()

    for name, video_path in VIDEOS.items():
        meta = validate_video(video_path)
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

        print(f"{name} ({total} frames): "
              f"ball coverage={ball_frames/total*100:.1f}% mean_conf={ball_conf_sum/max(1,ball_frames):.3f} | "
              f"rim coverage={rim_frames/total*100:.1f}% mean_conf={rim_conf_sum/max(1,rim_frames):.3f}")


if __name__ == "__main__":
    main()
