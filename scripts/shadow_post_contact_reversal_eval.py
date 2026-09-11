"""
READ-ONLY evaluation script for the SHADOW-ONLY app/research/post_contact_reversal.py
module. Reproduces the exact same detection/tracking/state-machine/enrichment
pass production uses (same pattern as scripts/forensic_arcvision_demo_final.py
and scripts/forensic_video4_outcome_evidence.py), then calls BOTH the real,
unmodified production outcome_detector.detect_outcome() AND the shadow
analyze_post_contact_reversal() on each shot's flight points, side by side.
Makes no production code change and does not modify production behavior in
any way -- this only ever reads flight_points that already exist.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CONFIG, MODELS_DIR
from app.events import outcome_detector as od
from app.events.shot_state_machine import ShotStateMachine
from app.pipeline.orchestrator import (
    PoseEstimator, PrimaryShooterSelector, YoloMultiDetector, aggregate_hoop_candidates,
    build_frame_signals,
)
from app.pipeline.video_io import FrameReader, validate_video
from app.research.post_contact_reversal import analyze_post_contact_reversal
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector
from app.vision.detection.near_hoop_enrichment import enrich_near_hoop
from app.vision.types import PoseFrame


def process_video(video_path: Path, out_dir: Path, video_label: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = validate_video(video_path)
    reader = FrameReader(meta)
    w, h = reader.analysis_width, reader.analysis_height

    detector = YoloMultiDetector.get()
    detector.warmup()

    checkpoint = MODELS_DIR / CONFIG.ball_rim_rfdetr.checkpoint_name
    rf = RFDETRBallRimDetector(str(checkpoint), CONFIG.ball_rim_rfdetr.confidence_floor)
    rf.warmup()

    pose_estimator = PoseEstimator()
    shooter_selector = PrimaryShooterSelector(min_track_frames=CONFIG.person.min_track_frames_for_primary)
    from app.tracking.ball_tracker import BallTracker
    ball_tracker = BallTracker()

    pose_frames, ball_observations, hoop_candidates = [], [], []
    frames_list = list(reader)
    total = len(frames_list)
    print(f"[{video_label}] Total frames: {total}", flush=True)

    for i, af in enumerate(frames_list):
        dets = detector.detect(af.image, af.frame_index, af.timestamp_sec)
        primary_person = shooter_selector.select(dets["person"])
        if primary_person is not None:
            pf = pose_estimator.process_crop(af.image, (primary_person.x1, primary_person.y1,
                                                          primary_person.x2, primary_person.y2),
                                              af.frame_index, af.timestamp_sec)
        else:
            pf = PoseFrame(af.frame_index, af.timestamp_sec, detected=False)
        pose_frames.append(pf)

        rf_raw = rf.predict_raw(af.image)
        validated = rf.extract_ball_detections(rf_raw, af.frame_index, af.timestamp_sec)
        rim_raw = rf.extract_rim_candidates(rf_raw)

        obs = ball_tracker.step(af.frame_index, af.timestamp_sec, validated)
        ball_observations.append(obs)
        hoop_candidates.extend((af.frame_index, x, y, r, c, "rfdetr") for (x, y, r, c) in rim_raw)

        if i % 500 == 0:
            print(f"[{video_label}] ...{i}/{total}", flush=True)

    pose_estimator.close()
    hoop = aggregate_hoop_candidates(hoop_candidates)
    print(f"[{video_label}] Hoop: center=({hoop.rim_center_x:.1f},{hoop.rim_center_y:.1f}) "
          f"r={hoop.rim_radius_px:.1f} conf={hoop.confidence} votes={hoop.votes}", flush=True)

    frame_signals = build_frame_signals(frames_list, pose_frames, ball_observations, w, h)
    machine = ShotStateMachine(enable_trace=False)
    windows = machine.process(frame_signals)
    print(f"[{video_label}] Detected {len(windows)} windows", flush=True)

    enriched_by_shot = enrich_near_hoop(video_path, meta, windows, ball_observations, hoop, w, h)

    report = []
    for win in windows:
        base_flight_start = win.release_candidate_frame or win.upward_start_frame or win.start_frame
        enriched_full = enriched_by_shot.get(win.shot_index, [])
        flight_points = [o for o in enriched_full if o.frame_index >= base_flight_start] if enriched_full else \
            [o for o in ball_observations if base_flight_start <= o.frame_index <= win.end_frame]
        flight_points = sorted(flight_points, key=lambda p: p.frame_index)

        prod_outcome = od.detect_outcome(flight_points, hoop)
        shadow_ep = analyze_post_contact_reversal(flight_points, hoop)

        release_t = next((f.timestamp_sec for f in frame_signals if f.frame_index == base_flight_start), None)
        row = {
            "shot_index": win.shot_index,
            "release_time_sec": release_t,
            "n_flight_points": len(flight_points),
            "production": {
                "outcome": prod_outcome.outcome.value, "confidence": prod_outcome.confidence,
                "reason": prod_outcome.reason,
            },
            "shadow": {k: v for k, v in asdict(shadow_ep).items()},
        }
        report.append(row)
        print(f"[{video_label}] shot {win.shot_index:2d} t={release_t:.2f}  "
              f"prod={prod_outcome.outcome.value}({prod_outcome.confidence:.2f}, {prod_outcome.reason})  "
              f"shadow: reversal={shadow_ep.reversal_detected} escape={shadow_ep.escape_detected} "
              f"quality={shadow_ep.evidence_quality} reason={shadow_ep.reason}", flush=True)

    (out_dir / "shadow_reversal_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[{video_label}] Saved: {out_dir}/shadow_reversal_report.json\n", flush=True)


def main():
    # V4-only this run (Outcome Reliability Pass #3B) -- showcase was already
    # validated separately; V1/V2/V3 intentionally not run, per instruction
    # to run only V4 and avoid unnecessary simultaneous heavy jobs.
    process_video(Path("real_test_04.mov").resolve(),
                   Path("data/diagnostics/shadow_reversal_v4"), "V4")


if __name__ == "__main__":
    main()
