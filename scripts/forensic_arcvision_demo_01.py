"""
One-off forensic script for investigating the UNKNOWN outcomes on
arcvision_demo_01_muted.mov (session 08b2d16fa1404b90). Read-only: makes no
production code changes. Reuses the exact same detection/tracking pass as
scripts/shot_timeline_debug.py, but additionally keeps the RAW per-frame
RF-DETR ball candidates (before tracker association) and rim candidates
near the hoop, so a discarded-by-the-tracker detection can be told apart
from RF-DETR never finding anything.

Usage:
    .venv\\Scripts\\python scripts\\forensic_arcvision_demo_01.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CONFIG, MODELS_DIR
from app.events.shot_state_machine import ShotStateMachine
from app.pipeline.orchestrator import (
    PoseEstimator, PrimaryShooterSelector, YoloMultiDetector, aggregate_hoop_candidates,
    build_frame_signals,
)
from app.pipeline.video_io import FrameReader, validate_video
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector
from app.vision.detection.near_hoop_enrichment import enrich_near_hoop
from app.vision.types import DataSource, PoseFrame
from app.events.outcome_detector import detect_outcome

VIDEO = Path("arcvision_demo_01_muted.mov").resolve()
OUT_DIR = Path("data/diagnostics/arcvision_demo_01_forensic")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    meta = validate_video(VIDEO)
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
    raw_ball_candidates_by_frame = {}   # frame_index -> list of {x,y,conf}
    rim_candidates_by_frame = {}        # frame_index -> list of {x,y,r,conf}

    frames_list = list(reader)
    total = len(frames_list)
    print(f"Total frames: {total}")

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
        raw_ball_candidates_by_frame[af.frame_index] = [
            {"x": round(d.center[0], 1), "y": round(d.center[1], 1), "conf": round(d.confidence, 3)}
            for d in validated
        ]
        rim_raw = rf.extract_rim_candidates(rf_raw)
        rim_candidates_by_frame[af.frame_index] = [
            {"x": round(x, 1), "y": round(y, 1), "r": round(r, 1), "conf": round(c, 3)}
            for (x, y, r, c) in rim_raw
        ]

        obs = ball_tracker.step(af.frame_index, af.timestamp_sec, validated)
        ball_observations.append(obs)

        hoop_candidates.extend((af.frame_index, x, y, r, c, "rfdetr")
                                for (x, y, r, c) in rim_raw)

        if i % 300 == 0:
            print(f"...{i}/{total}")

    pose_estimator.close()
    hoop = aggregate_hoop_candidates(hoop_candidates)
    print(f"Hoop: center=({hoop.rim_center_x:.1f},{hoop.rim_center_y:.1f}) r={hoop.rim_radius_px:.1f} "
          f"conf={hoop.confidence} votes={hoop.votes}")

    frame_signals = build_frame_signals(frames_list, pose_frames, ball_observations, w, h)
    machine = ShotStateMachine(enable_trace=True)
    windows = machine.process(frame_signals)
    print(f"Detected {len(windows)} windows")

    # Near-hoop enrichment exactly as production calls it.
    enriched_by_shot = enrich_near_hoop(VIDEO, meta, windows, ball_observations, hoop, w, h)

    ball_by_frame = {o.frame_index: o for o in ball_observations}

    def dump_window(win, margin_before=30, margin_after=90):
        lo = win.start_frame - margin_before
        hi = win.end_frame + margin_after
        rows = []
        for fi in range(lo, hi + 1):
            obs = ball_by_frame.get(fi)
            raw = raw_ball_candidates_by_frame.get(fi, [])
            rim = rim_candidates_by_frame.get(fi, [])
            in_window = win.start_frame <= fi <= win.end_frame
            row = {
                "frame": fi,
                "in_window": in_window,
                "past_end": fi > win.end_frame,
                "obs_source": obs.source.value if obs else None,
                "obs_conf": round(obs.confidence, 3) if obs else None,
                "obs_xy": [round(obs.center_x, 1), round(obs.center_y, 1)] if obs and obs.source != DataSource.UNAVAILABLE else None,
                "dist_to_rim_center_px": (
                    round(((obs.center_x - hoop.rim_center_x) ** 2 + (obs.center_y - hoop.rim_center_y) ** 2) ** 0.5, 1)
                    if obs and obs.source != DataSource.UNAVAILABLE else None
                ),
                "raw_rf_detr_ball_candidates": raw,
                "rim_candidates": rim,
            }
            rows.append(row)
        return rows

    outcome_report = {}
    for win in windows:
        base_flight_start = win.release_candidate_frame or win.upward_start_frame or win.start_frame
        original_flight = [o for o in ball_observations if base_flight_start <= o.frame_index <= win.end_frame]
        enriched_full = enriched_by_shot.get(win.shot_index, [])
        enriched_clamped = [o for o in enriched_full if base_flight_start <= o.frame_index <= win.end_frame]
        enriched_unclamped = [o for o in enriched_full if o.frame_index >= base_flight_start]

        out_original = detect_outcome(original_flight, hoop)
        out_prod_enriched = detect_outcome(enriched_clamped, hoop)          # what production actually computes
        out_extended = detect_outcome(enriched_unclamped, hoop)              # if the end_frame clamp were removed

        outcome_report[win.shot_index] = {
            "start_frame": win.start_frame, "end_frame": win.end_frame,
            "release_frame": win.release_candidate_frame, "warnings": win.warnings,
            "n_original_flight_points": len(original_flight),
            "n_enriched_points_beyond_end_frame": len([o for o in enriched_full if o.frame_index > win.end_frame]),
            "outcome_original_unenriched": {"outcome": out_original.outcome.value, "confidence": out_original.confidence, "reason": out_original.reason},
            "outcome_production_enriched_clamped": {"outcome": out_prod_enriched.outcome.value, "confidence": out_prod_enriched.confidence, "reason": out_prod_enriched.reason},
            "outcome_if_clamp_removed": {"outcome": out_extended.outcome.value, "confidence": out_extended.confidence, "reason": out_extended.reason, "evidence": out_extended.evidence},
        }

        detail = dump_window(win)
        (OUT_DIR / f"shot_{win.shot_index}_frames.json").write_text(json.dumps(detail, indent=2), encoding="utf-8")

    (OUT_DIR / "outcome_comparison.json").write_text(json.dumps(outcome_report, indent=2), encoding="utf-8")
    print("\n=== Outcome comparison (original vs production-enriched-but-clamped vs clamp-removed) ===")
    for sid, r in outcome_report.items():
        print(f"\nShot {sid}: end_frame={r['end_frame']}  extra_enriched_pts_beyond_end={r['n_enriched_points_beyond_end_frame']}")
        print(f"  unenriched:        {r['outcome_original_unenriched']}")
        print(f"  production(clamp): {r['outcome_production_enriched_clamped']}")
        print(f"  clamp removed:     {r['outcome_if_clamp_removed']['outcome']} conf={r['outcome_if_clamp_removed']['confidence']} reason={r['outcome_if_clamp_removed']['reason']}")

    print(f"\nSaved per-shot frame dumps and outcome_comparison.json to {OUT_DIR}")


if __name__ == "__main__":
    main()
