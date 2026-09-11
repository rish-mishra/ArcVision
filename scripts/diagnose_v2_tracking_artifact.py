"""
One-off diagnostic (not part of any pipeline): reproduces run_detection_only's
loop but dumps, for a set of frame windows, every raw RF-DETR ball
detection, the nearest raw rim detection, the tracker's picked point
(source/confidence), and the tracker's internal miss-streak / Kalman
prediction BEFORE that frame's update -- everything needed to see exactly
where a fabricated position enters the pipeline.

Usage:
    .venv\\Scripts\\python scripts\\diagnose_v2_tracking_artifact.py path\\to\\video.mp4
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CONFIG
from app.pipeline.orchestrator import PoseEstimator, PrimaryShooterSelector, YoloMultiDetector
from app.pipeline.video_io import FrameReader, validate_video
from app.tracking.ball_tracker import BallTracker
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

import os
_WINDOWS_ENV = os.environ.get("DIAG_WINDOWS")
if _WINDOWS_ENV:
    WINDOWS = [tuple(int(x) for x in pair.split("-")) for pair in _WINDOWS_ENV.split(",")]
else:
    WINDOWS = [(0, 100), (290, 360), (510, 580), (1330, 1390), (1510, 1580)]


def in_window(fi: int) -> bool:
    return any(lo <= fi <= hi for lo, hi in WINDOWS)


def main():
    video_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("v2_tracking_diag.csv")

    meta = validate_video(video_path)
    reader = FrameReader(meta)

    detector = YoloMultiDetector.get()
    detector.warmup()
    checkpoint_override = os.environ.get("RFDETR_CHECKPOINT_OVERRIDE")
    rfdetr_checkpoint = Path(checkpoint_override) if checkpoint_override else (MODELS_DIR / CONFIG.ball_rim_rfdetr.checkpoint_name)
    rf = RFDETRBallRimDetector(str(rfdetr_checkpoint), CONFIG.ball_rim_rfdetr.confidence_floor)
    rf.warmup()
    pose_estimator = PoseEstimator()
    shooter_selector = PrimaryShooterSelector(min_track_frames=CONFIG.person.min_track_frames_for_primary)
    ball_tracker = BallTracker()

    rows = []
    frames_list = list(reader)
    total = len(frames_list)
    for i, af in enumerate(frames_list):
        want = in_window(af.frame_index)
        dets = detector.detect(af.image, af.frame_index, af.timestamp_sec) if want else {"person": []}
        primary_person = shooter_selector.select(dets["person"]) if want else None

        rf_raw = rf.predict_raw(af.image)
        validated = rf.extract_ball_detections(rf_raw, af.frame_index, af.timestamp_sec)
        rim_candidates = rf.extract_rim_candidates(rf_raw)

        # Snapshot tracker state BEFORE this frame's step (predicted position, miss streak).
        kf = ball_tracker._tracker.kf
        pre_px, pre_py = (kf.position if kf is not None else (None, None))
        misses_before = ball_tracker._tracker.misses_in_a_row

        obs = ball_tracker.step(af.frame_index, af.timestamp_sec, validated)

        if want:
            best_ball = ", ".join(f"({d.center[0]:.0f},{d.center[1]:.0f},c={d.confidence:.2f})" for d in validated) or "-"
            nearest_rim = min(rim_candidates, key=lambda c: ((c[0]-obs.center_x)**2+(c[1]-obs.center_y)**2)**0.5) if rim_candidates else None
            rim_str = f"({nearest_rim[0]:.0f},{nearest_rim[1]:.0f},r={nearest_rim[2]:.0f},c={nearest_rim[3]:.2f})" if nearest_rim else "-"
            # bbox geometry of whichever raw detection the tracker actually picked this frame
            # (matched by center proximity, since _pick_best_candidate already made the choice).
            picked_det = None
            if validated:
                picked_det = min(validated, key=lambda d: (d.center[0]-obs.center_x)**2 + (d.center[1]-obs.center_y)**2)
            bbox_w = picked_det.width if picked_det else None
            bbox_h = picked_det.height if picked_det else None
            bbox_radius = (max(bbox_w, bbox_h) / 2.0) if picked_det else None
            bbox_aspect = (bbox_w / bbox_h) if (picked_det and bbox_h) else None
            rows.append({
                "frame_index": af.frame_index, "t": round(af.timestamp_sec, 3),
                "raw_ball_dets": best_ball,
                "picked_x": round(obs.center_x, 1), "picked_y": round(obs.center_y, 1),
                "picked_source": obs.source.value if hasattr(obs.source, "value") else obs.source,
                "picked_conf": round(obs.confidence, 3),
                "bbox_w": round(bbox_w, 1) if bbox_w is not None else "",
                "bbox_h": round(bbox_h, 1) if bbox_h is not None else "",
                "bbox_radius": round(bbox_radius, 1) if bbox_radius is not None else "",
                "bbox_aspect_w_over_h": round(bbox_aspect, 3) if bbox_aspect is not None else "",
                "misses_before": misses_before,
                "kf_pred_before": f"({pre_px:.0f},{pre_py:.0f})" if pre_px is not None else "-",
                "nearest_rim": rim_str,
            })
        if i % 300 == 0:
            print(f"...{i}/{total}")

    pose_estimator.close()

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
