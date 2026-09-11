"""
Phase 6 A/B benchmark: existing YOLOv8+YOLO-World+classical-CV detector
stack vs. the fine-tuned RF-DETR ball/rim detector, on real_test_01.mp4.mov.

Runs BOTH stacks over every analyzed frame (not the production-sampled
hoop cadence, so this is an apples-to-apples per-frame coverage
comparison), independently of the Kalman tracker / outcome detector --
this measures raw per-frame detection QUALITY, which is the actual
variable under test; tracking/interpolation is a downstream consumer that
stays identical regardless of which detector feeds it.

Does NOT use the known MAKE/MISS outcome labels anywhere -- shot windows
(start/release/end times) come from the already-validated shot-segmentation
result, used only to define WHEN a shot's flight is happening, not what
happened during it.

Usage:
    .venv\\Scripts\\python scripts\\benchmark_ball_rim_detectors.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from app.pipeline.video_io import FrameReader, validate_video
from app.tracking.hoop_aggregator import aggregate_hoop_candidates
from app.vision.detection.ball_detector import validate_ball_candidates
from app.vision.detection.ball_detector_learned import LearnedBallDetector
from app.vision.detection.hoop_detector import detect_hoop_candidates
from app.vision.detection.hoop_detector_learned import LearnedHoopDetector
from app.vision.detection.yolo_detector import YoloMultiDetector
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector

import os

ROOT = Path(__file__).resolve().parent.parent
VIDEO_PATH = ROOT / "real_test_01.mp4.mov"
SESSION_PATH = ROOT / "data" / "diagnostics" / "real_test_01" / "session_result.json"
# BENCHMARK_CHECKPOINT_OVERRIDE: diagnostic-only escape hatch for A/B comparing an
# alternate checkpoint; omitting it reproduces the exact existing default.
_checkpoint_override = os.environ.get("BENCHMARK_CHECKPOINT_OVERRIDE")
CHECKPOINT_PATH = Path(_checkpoint_override) if _checkpoint_override else (
    ROOT / "data" / "training_runs" / "rfdetr_ball_rim_v1" / "checkpoint_best_ema.pth"
)
_out_suffix = os.environ.get("BENCHMARK_OUT_SUFFIX", "")
OUT_PATH = ROOT / "data" / "diagnostics" / "detector_benchmark" / f"benchmark_report{_out_suffix}.json"


def _longest_gap(frames_with_detection: set, lo: int, hi: int) -> int:
    longest = 0
    current = 0
    for f in range(lo, hi + 1):
        if f in frames_with_detection:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    session = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    fps = session["video_meta"]["fps"]
    shots = session["shots"]

    meta = validate_video(VIDEO_PATH)
    reader = FrameReader(meta)
    frames = list(reader)
    total_frames = len(frames)
    print(f"Total analyzed frames: {total_frames}")

    # --- Existing stack ---
    print("Loading existing detector stack (YOLOv8 + YOLO-World + classical CV)...")
    yolo = YoloMultiDetector.get()
    yolo.warmup()
    learned_ball = LearnedBallDetector.get()
    learned_ball.warmup()
    learned_hoop = LearnedHoopDetector.get()
    learned_hoop.warmup()

    existing_ball_by_frame = {}
    existing_hoop_candidates = []  # (frame_index, x, y, r, conf, source)

    t0 = time.time()
    for af in frames:
        dets = yolo.detect(af.image, af.frame_index, af.timestamp_sec)
        validated = validate_ball_candidates(af.image, dets["ball_candidate"])
        validated = validated + learned_ball.detect(af.image, af.frame_index, af.timestamp_sec)
        existing_ball_by_frame[af.frame_index] = validated

        for (x, y, r, conf) in detect_hoop_candidates(af.image):
            existing_hoop_candidates.append((af.frame_index, x, y, r, conf, "classical"))
        for (x, y, r, conf) in learned_hoop.detect(af.image):
            existing_hoop_candidates.append((af.frame_index, x, y, r, conf, "learned"))
    existing_time = time.time() - t0
    print(f"Existing stack: {existing_time:.1f}s ({total_frames / existing_time:.1f} fps)")

    # --- RF-DETR stack ---
    print("Loading RF-DETR ball/rim detector...")
    rfdetr = RFDETRBallRimDetector(str(CHECKPOINT_PATH))
    rfdetr.warmup()

    rfdetr_ball_by_frame = {}
    rfdetr_hoop_candidates = []

    t0 = time.time()
    for af in frames:
        raw = rfdetr.predict_raw(af.image)
        rfdetr_ball_by_frame[af.frame_index] = rfdetr.extract_ball_detections(raw, af.frame_index, af.timestamp_sec)
        for (x, y, r, conf) in rfdetr.extract_rim_candidates(raw):
            rfdetr_hoop_candidates.append((af.frame_index, x, y, r, conf, "rfdetr"))
    rfdetr_time = time.time() - t0
    print(f"RF-DETR stack: {rfdetr_time:.1f}s ({total_frames / rfdetr_time:.1f} fps)")

    # --- BALL metrics ---
    def ball_report(by_frame):
        frames_with_det = {f for f, dets in by_frame.items() if dets}
        all_confs = [d.confidence for dets in by_frame.values() for d in dets]
        n_multi = sum(1 for dets in by_frame.values() if len(dets) > 1)
        report = {
            "total_frames": total_frames,
            "frames_with_detection": len(frames_with_det),
            "coverage_frac": round(len(frames_with_det) / total_frames, 3),
            "mean_confidence": round(float(np.mean(all_confs)), 3) if all_confs else None,
            "median_confidence": round(float(np.median(all_confs)), 3) if all_confs else None,
            "frames_with_multiple_candidates": n_multi,
            "longest_blackout_frames_overall": _longest_gap(frames_with_det, 0, total_frames - 1),
            "per_shot": [],
        }
        for s in shots:
            lo = int(round(s["release_time_sec"] * fps)) if s["release_time_sec"] else int(round(s["start_time_sec"] * fps))
            hi = int(round(s["end_time_sec"] * fps))
            flight_len = hi - lo + 1
            covered = sum(1 for f in range(lo, hi + 1) if f in frames_with_det)
            near_rim_lo = lo + int(0.7 * flight_len)  # last 30% of flight -- approach/rim-interaction proxy
            near_rim_covered = sum(1 for f in range(near_rim_lo, hi + 1) if f in frames_with_det)
            near_rim_total = hi - near_rim_lo + 1
            release_window = range(max(0, lo - 2), lo + 3)
            release_covered = sum(1 for f in release_window if f in frames_with_det)
            report["per_shot"].append({
                "shot_index": s["shot_index"],
                "flight_coverage_frac": round(covered / flight_len, 3) if flight_len else None,
                "near_rim_coverage_frac": round(near_rim_covered / near_rim_total, 3) if near_rim_total else None,
                "release_window_coverage": f"{release_covered}/{len(list(release_window))}",
                "longest_blackout_in_flight": _longest_gap(frames_with_det, lo, hi),
            })
        return report

    ball_existing = ball_report(existing_ball_by_frame)
    ball_rfdetr = ball_report(rfdetr_ball_by_frame)

    # --- RIM/HOOP metrics ---
    def hoop_report(candidates):
        frames_with_det = {c[0] for c in candidates}
        hoop = aggregate_hoop_candidates(candidates)
        report = {
            "frames_with_detection": len(frames_with_det),
            "coverage_frac": round(len(frames_with_det) / total_frames, 3),
        }
        if hoop is not None:
            report.update({
                "rim_center_x": round(hoop.rim_center_x, 1), "rim_center_y": round(hoop.rim_center_y, 1),
                "rim_radius_px": round(hoop.rim_radius_px, 1), "confidence": hoop.confidence,
                "votes": hoop.votes, "method": hoop.method,
            })
            # positional stability: std dev of per-frame candidates within
            # the winning cluster's rough vicinity (2x its own radius).
            near = [(c[1], c[2]) for c in candidates
                     if ((c[1] - hoop.rim_center_x) ** 2 + (c[2] - hoop.rim_center_y) ** 2) ** 0.5 < hoop.rim_radius_px * 2]
            if len(near) >= 2:
                xs, ys = zip(*near)
                report["positional_stability_std_px"] = round(float(np.mean([np.std(xs), np.std(ys)])), 2)
                report["n_points_used_for_stability"] = len(near)
        else:
            report["hoop"] = None
        return report

    hoop_existing = hoop_report(existing_hoop_candidates)
    hoop_rfdetr = hoop_report(rfdetr_hoop_candidates)

    result = {
        "total_frames": total_frames,
        "performance": {
            "existing_stack_seconds": round(existing_time, 1),
            "existing_stack_fps": round(total_frames / existing_time, 2),
            "rfdetr_seconds": round(rfdetr_time, 1),
            "rfdetr_fps": round(total_frames / rfdetr_time, 2),
        },
        "ball": {"existing_stack": ball_existing, "rfdetr": ball_rfdetr},
        "rim": {"existing_stack": hoop_existing, "rfdetr": hoop_rfdetr},
    }
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nSaved benchmark report to {OUT_PATH}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
