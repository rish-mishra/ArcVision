"""
READ-ONLY Part 2 evaluation for the SHADOW-ONLY app/research/net_motion_resolver.py
module (docs/NET_MOTION_SHADOW.md Part 2 -- controlled measurement).

Unlike Part 1 (scripts/net_motion_shadow_eval.py), this DOES run real
detector inference (YOLO person detection + RF-DETR ball/rim), per
instruction -- but ONLY over the same small set of bounded shot windows as
Part 1, never the full video: a SINGLE SEQUENTIAL pass per video (frame-index
seeking via cv2 is avoided -- unreliable on compressed video, keyframe-only
in practice) skips inference entirely on any frame outside every target
shot's window, and only actually runs YOLO/RF-DETR on the small fraction of
frames that matter. A fresh BallTracker/PrimaryShooterSelector is used per
shot (shot windows never overlap in time), not shared across the whole
video. Produces dense, per-frame REAL person bounding boxes and REAL ball
detections (with true DataSource provenance: DETECTED vs INTERPOLATED vs
PREDICTED) for masking, instead of Part 1's sparse/proportion-estimated
fallbacks. No production code change, no MADE/MISSED verdict.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CONFIG, MODELS_DIR
from app.pipeline.orchestrator import PrimaryShooterSelector, YoloMultiDetector
from app.pipeline.video_io import FrameReader, validate_video
from app.research.net_motion_resolver import BallSample, PersonSample, analyze_net_motion_from_frames
from app.tracking.ball_tracker import BallTracker
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector
from app.vision.types import DataSource, HoopLocation

OUT_DIR = Path("data/diagnostics/net_motion_shadow")
OUT_DIR.mkdir(parents=True, exist_ok=True)

_SOURCE_MAP = {DataSource.DETECTED: "detected", DataSource.INTERPOLATED: "interpolated",
               DataSource.PREDICTED: "predicted"}


def shot_window(shot: dict, pad_before: int = 12, pad_after: int = 12):
    a_frames = [c["a_frame"] for c in shot["candidate_pairs"]]
    b_frames = [c["b_frame"] for c in shot["candidate_pairs"]]
    fd_frames = [p["frame"] for p in shot["far_descent_detail"]]
    all_frames = a_frames + b_frames + fd_frames
    if not all_frames:
        lo, hi = shot["start_frame"], shot["start_frame"] + 60
    else:
        lo, hi = min(all_frames) - pad_before, max(all_frames) + pad_after
    return max(lo, shot["start_frame"] - pad_before), min(hi, shot["end_frame"])


def save_panel(gray_by_frame, frame_indices, ep, out_path: Path, title: str):
    if len(frame_indices) < 2 or not ep.relative_motion_series:
        return
    peak_i = int(np.argmax(ep.relative_motion_series)) + 1
    peak_fi = frame_indices[peak_i]
    prev_fi = frame_indices[peak_i - 1]
    pre_fi = frame_indices[0]

    def box(bgr, roi, color):
        if roi:
            cv2.rectangle(bgr, (roi.x0, roi.y0), (roi.x1, roi.y1), color, 1)

    raw = cv2.cvtColor(gray_by_frame[peak_fi], cv2.COLOR_GRAY2BGR)
    box(raw, ep.net_roi, (0, 255, 0)); box(raw, ep.control_roi_left, (255, 200, 0)); box(raw, ep.control_roi_right, (255, 200, 0))

    pre = cv2.cvtColor(gray_by_frame[pre_fi], cv2.COLOR_GRAY2BGR)
    box(pre, ep.net_roi, (0, 255, 0))

    diff = cv2.absdiff(gray_by_frame[peak_fi], gray_by_frame[prev_fi])
    diff_vis = cv2.applyColorMap(np.clip(diff.astype(np.int32) * 4, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    box(diff_vis, ep.net_roi, (0, 255, 0)); box(diff_vis, ep.control_roi_left, (0, 200, 255)); box(diff_vis, ep.control_roi_right, (0, 200, 255))

    tiles = [pre, raw, diff_vis]
    labels = [f"pre f{pre_fi}", f"peak f{peak_fi}", f"diff f{prev_fi}->f{peak_fi} (x4)"]
    h = 220
    resized = [cv2.resize(t, (int(t.shape[1] * h / t.shape[0]), h)) for t in tiles]
    row = np.hstack(resized)
    banner = np.full((56, row.shape[1], 3), (25, 25, 25), dtype=np.uint8)
    cv2.putText(banner, title, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    x = 6
    for lab, t in zip(labels, resized):
        cv2.putText(banner, lab, (x, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)
        x += t.shape[1]
    panel = np.vstack([banner, row])
    cv2.imwrite(str(out_path), panel)
    print(f"Saved: {out_path}")


def run(video_label: str, video_path: Path, hoop: HoopLocation, report_path: Path, targets: list, out_prefix: str):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    yolo = YoloMultiDetector.get()
    yolo.warmup()
    checkpoint = MODELS_DIR / CONFIG.ball_rim_rfdetr.checkpoint_name
    rf = RFDETRBallRimDetector(str(checkpoint), CONFIG.ball_rim_rfdetr.confidence_floor)
    rf.warmup()

    windows = {}
    for idx in targets:
        shot = next(s for s in report if s["shot_index"] == idx)
        lo, hi = shot_window(shot)
        windows[idx] = (lo, hi)
    overall_lo = min(lo for lo, hi in windows.values())
    overall_hi = max(hi for lo, hi in windows.values())
    wanted_by_shot = {idx: set(range(lo, hi + 1)) for idx, (lo, hi) in windows.items()}
    all_wanted = set().union(*wanted_by_shot.values())

    print(f"[{video_label}] Single sequential pass, frames {overall_lo}-{overall_hi} "
          f"({len(all_wanted)} of those actually processed)...", flush=True)

    meta = validate_video(video_path)
    reader = FrameReader(meta)

    trackers = {idx: (BallTracker(), PrimaryShooterSelector(min_track_frames=CONFIG.person.min_track_frames_for_primary))
                 for idx in targets}
    gray_by_shot = {idx: {} for idx in targets}
    ball_by_shot = {idx: {} for idx in targets}
    person_by_shot = {idx: {} for idx in targets}

    n_processed = 0
    for af in reader:
        if af.frame_index > overall_hi:
            break
        if af.frame_index < overall_lo:
            continue
        owning_shots = [idx for idx in targets if af.frame_index in wanted_by_shot[idx]]
        if not owning_shots:
            continue
        n_processed += 1
        if n_processed % 100 == 0:
            print(f"[{video_label}] ...processed {n_processed}/{len(all_wanted)}", flush=True)

        dets = yolo.detect(af.image, af.frame_index, af.timestamp_sec)
        rf_raw = rf.predict_raw(af.image)
        validated = rf.extract_ball_detections(rf_raw, af.frame_index, af.timestamp_sec)
        gray = cv2.cvtColor(af.image, cv2.COLOR_BGR2GRAY)

        for idx in owning_shots:
            ball_tracker, shooter_selector = trackers[idx]
            primary_person = shooter_selector.select(dets["person"])
            if primary_person is not None:
                person_by_shot[idx][af.frame_index] = PersonSample(
                    af.frame_index, primary_person.x1, primary_person.y1, primary_person.x2, primary_person.y2)
            obs = ball_tracker.step(af.frame_index, af.timestamp_sec, validated)
            if obs.source != DataSource.UNAVAILABLE:
                ball_by_shot[idx][af.frame_index] = BallSample(
                    af.frame_index, obs.center_x, obs.center_y, obs.radius_px,
                    source=_SOURCE_MAP.get(obs.source, "predicted"))
            gray_by_shot[idx][af.frame_index] = gray

    results = []
    for idx in targets:
        shot = next(s for s in report if s["shot_index"] == idx)
        fi_present = sorted(gray_by_shot[idx].keys())
        frames = [gray_by_shot[idx][fi] for fi in fi_present]
        ep = analyze_net_motion_from_frames(frames, fi_present, hoop, ball_by_shot[idx], person_by_shot[idx])
        n_person = len(person_by_shot[idx])
        n_ball_detected = sum(1 for b in ball_by_shot[idx].values() if b.source == "detected")

        results.append({
            "shot_index": idx,
            "production": {"outcome": shot["outcome"], "confidence": shot["outcome_confidence"], "reason": shot["outcome_reason"]},
            "person_frames_available": n_person, "ball_frames_detected": n_ball_detected, "n_frames_in_window": len(fi_present),
            "episode": {k: v for k, v in ep.__dict__.items() if k not in ("net_roi", "control_roi_left", "control_roi_right")},
        })
        med = float(np.median(ep.relative_motion_series)) if ep.relative_motion_series else 0.0
        print(f"[{video_label}] shot {idx}: n_pairs={ep.n_frame_pairs} elevated={ep.n_elevated_pairs} "
              f"fully_clean={ep.n_fully_clean_pairs} median_rel={med:.2f} "
              f"person_avail={n_person}/{len(fi_present)} ball_detected={n_ball_detected}/{len(fi_present)}", flush=True)
        save_panel(gray_by_shot[idx], fi_present, ep, OUT_DIR / f"{out_prefix}_shot{idx:02d}_part2.png",
                    f"{video_label} shot {idx} prod={shot['outcome']}({shot['outcome_confidence']:.2f}) [Part2 masked]")

    (OUT_DIR / f"{out_prefix}_net_motion_part2.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"[{video_label}] Saved: {OUT_DIR}/{out_prefix}_net_motion_part2.json\n")


def main():
    showcase_hoop = HoopLocation(rim_center_x=300.7, rim_center_y=146.2, rim_radius_px=28.2, confidence=0.968, votes=2954, method="rfdetr")
    run("SHOWCASE", Path("arcvision_demo_final.mov").resolve(), showcase_hoop,
         Path("data/diagnostics/arcvision_demo_final_forensic/shot_forensic_report.json"),
         [1, 3, 5, 8, 9, 10, 11], "showcase")

    v4_hoop = HoopLocation(rim_center_x=262.7, rim_center_y=154.5, rim_radius_px=29.9, confidence=0.961, votes=5761, method="rfdetr")
    run("V4", Path("real_test_04.mov").resolve(), v4_hoop,
         Path("data/diagnostics/video4_outcome_forensic/shot_forensic_report.json"),
         [9, 17, 21, 15, 19, 4, 5], "v4")


if __name__ == "__main__":
    main()
