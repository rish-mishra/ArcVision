"""
One-off diagnostic (not part of any pipeline): runs FormAI's existing
FALLBACK ball detectors (YOLOv8 "sports ball" + classical color/circularity
validation, plus YOLO-World open-vocabulary) over a set of frame windows,
independent of RF-DETR, and dumps every candidate found per frame. Meant
to be joined afterward against an existing RF-DETR position CSV (from
diagnose_v2_tracking_artifact.py) by frame_index, to measure cross-detector
spatial agreement.

Usage:
    .venv\\Scripts\\python scripts\\diagnose_fallback_corroboration.py video.mp4 out.csv "lo-hi,lo-hi,..."
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CONFIG
from app.pipeline.orchestrator import YoloMultiDetector
from app.pipeline.video_io import FrameReader, validate_video
from app.vision.detection.ball_detector import validate_ball_candidates
from app.vision.detection.ball_detector_learned import LearnedBallDetector

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def main():
    video_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2])
    windows = [tuple(int(x) for x in pair.split("-")) for pair in sys.argv[3].split(",")]

    def in_window(fi):
        return any(lo <= fi <= hi for lo, hi in windows)

    meta = validate_video(video_path)
    reader = FrameReader(meta)

    yolo = YoloMultiDetector.get()
    yolo.warmup()
    learned_ball = LearnedBallDetector.get()
    learned_ball.warmup()

    rows = []
    frames_list = list(reader)
    total = len(frames_list)
    for i, af in enumerate(frames_list):
        if not in_window(af.frame_index):
            continue
        dets = yolo.detect(af.image, af.frame_index, af.timestamp_sec)
        classical = validate_ball_candidates(af.image, dets["ball_candidate"])
        learned = learned_ball.detect(af.image, af.frame_index, af.timestamp_sec)
        for d in classical:
            rows.append({"frame_index": af.frame_index, "source": "classical_yolov8",
                          "x": round(d.center[0], 1), "y": round(d.center[1], 1), "conf": round(d.confidence, 3)})
        for d in learned:
            rows.append({"frame_index": af.frame_index, "source": "yolo_world",
                          "x": round(d.center[0], 1), "y": round(d.center[1], 1), "conf": round(d.confidence, 3)})
        if not classical and not learned:
            rows.append({"frame_index": af.frame_index, "source": "none", "x": "", "y": "", "conf": ""})
        if i % 300 == 0:
            print(f"...{i}/{total}")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["frame_index", "source", "x", "y", "conf"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
