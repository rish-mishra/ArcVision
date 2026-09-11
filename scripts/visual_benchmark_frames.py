"""
Phase 7 visual benchmark: existing detector stack vs. RF-DETR ball/rim, on
identical hand-picked frames covering the hard cases that matter most for
outcome detection -- hand-occluded ball, just-released ball, small ball
against bright sky near apex, ball approaching/overlapping the rim, ball
inside the net, ball below the rim, and an idle moment (false-positive
check).

Usage:
    .venv\\Scripts\\python scripts\\visual_benchmark_frames.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from app.vision.detection.ball_detector import validate_ball_candidates
from app.vision.detection.ball_detector_learned import LearnedBallDetector
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector
from app.vision.detection.hoop_detector import detect_hoop_candidates
from app.vision.detection.hoop_detector_learned import LearnedHoopDetector
from app.vision.detection.yolo_detector import YoloMultiDetector

ROOT = Path(__file__).resolve().parent.parent
VIDEO_PATH = ROOT / "real_test_01.mp4.mov"
CHECKPOINT_PATH = ROOT / "data" / "training_runs" / "rfdetr_ball_rim_v1" / "checkpoint_best_ema.pth"
OUT_DIR = ROOT / "data" / "diagnostics" / "detector_benchmark" / "visual"

# (label, frame_index) -- native-resolution frame indices; several reused
# from the earlier Shot 7 root-cause investigation where the ball's actual
# position at each was already visually confirmed against the raw video.
CASES = [
    ("hand_occluded_ball", 52),        # shot 1 release -- ball still gripped
    ("just_released", 1402),            # shot 7, ~0.17s after release
    ("small_ball_vs_sky", 1408),        # shot 7 ascent, small + bright sky background
    ("approaching_rim", 1428),          # shot 7 -- confirmed visually at the rim
    ("overlapping_rim", 1434),          # shot 7 -- confirmed visually inside the net, below rim
    ("inside_net", 1440),               # shot 7 -- confirmed visually deeper in net
    ("below_rim_falling", 1446),        # shot 7 -- confirmed visually falling below hoop
    ("idle_no_ball_near_hoop", 200),    # between shots -- false-positive check
]


def _draw(frame, ball_dets, rim_cands, color, label):
    vis = frame.copy()
    for d in ball_dets:
        cv2.rectangle(vis, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), color, 2)
        cv2.putText(vis, f"ball {d.confidence:.2f}", (int(d.x1), max(15, int(d.y1) - 5)),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    for (cx, cy, r, conf) in rim_cands:
        cv2.rectangle(vis, (int(cx - r), int(cy - r)), (int(cx + r), int(cy + r)), color, 2)
        cv2.putText(vis, f"rim {conf:.2f}", (int(cx - r), max(15, int(cy - r) - 5)),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    cv2.putText(vis, label, (10, vis.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    return vis


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading existing stack...")
    yolo = YoloMultiDetector.get(); yolo.warmup()
    learned_ball = LearnedBallDetector.get(); learned_ball.warmup()
    learned_hoop = LearnedHoopDetector.get(); learned_hoop.warmup()

    print("Loading RF-DETR...")
    rfdetr = RFDETRBallRimDetector(str(CHECKPOINT_PATH)); rfdetr.warmup()

    cap = cv2.VideoCapture(str(VIDEO_PATH))
    native_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    analysis_w = 960  # matches this session's analysis resolution
    scale = analysis_w / native_w

    for label, native_frame_idx in CASES:
        cap.set(cv2.CAP_PROP_POS_FRAMES, native_frame_idx)
        ok, native_frame = cap.read()
        if not ok:
            print(f"{label}: FAILED to read frame {native_frame_idx}")
            continue
        h, w = native_frame.shape[:2]
        analysis_frame = cv2.resize(native_frame, (int(w * scale), int(h * scale)))

        # Existing stack
        dets = yolo.detect(analysis_frame, native_frame_idx, 0.0)
        existing_balls = validate_ball_candidates(analysis_frame, dets["ball_candidate"])
        existing_balls = existing_balls + learned_ball.detect(analysis_frame, native_frame_idx, 0.0)
        existing_hoop = detect_hoop_candidates(analysis_frame) + learned_hoop.detect(analysis_frame)
        existing_hoop = [(x, y, r, c) for (x, y, r, c) in existing_hoop]

        # RF-DETR
        raw = rfdetr.predict_raw(analysis_frame)
        rf_balls = rfdetr.extract_ball_detections(raw, native_frame_idx, 0.0)
        rf_hoop = rfdetr.extract_rim_candidates(raw)

        left = _draw(analysis_frame, existing_balls, existing_hoop, (0, 165, 255), "EXISTING STACK")
        right = _draw(analysis_frame, rf_balls, rf_hoop, (0, 255, 0), "RF-DETR")
        combined = np.hstack([left, right])
        out_path = OUT_DIR / f"{label}_f{native_frame_idx}.png"
        cv2.imwrite(str(out_path), combined)
        print(f"{label}: existing={len(existing_balls)} ball / {len(existing_hoop)} rim candidates | "
               f"rfdetr={len(rf_balls)} ball / {len(rf_hoop)} rim candidates -> saved {out_path.name}")

    cap.release()


if __name__ == "__main__":
    main()
