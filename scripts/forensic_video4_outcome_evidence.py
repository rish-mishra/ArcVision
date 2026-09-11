"""
READ-ONLY forensic script for real_test_04.mov (Video 4, frozen 18-shot ground
truth in docs/VIDEO4_EVALUATION_PROTOCOL.md). Same structure as
forensic_arcvision_demo_final.py -- reproduces the exact same detection/
tracking/state-machine pass production used, and directly re-derives, using the
REAL unmodified app.events.outcome_detector internals, exactly which evidence
branch produced (or failed to produce) each shot's outcome, dumping every
candidate MADE crossing pair actually evaluated (not just the best one) for
every shot. Makes no production code change.
"""
from __future__ import annotations

import json
import sys
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
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector
from app.vision.detection.near_hoop_enrichment import enrich_near_hoop
from app.vision.types import DataSource, PoseFrame

VIDEO = Path("real_test_04.mov").resolve()
OUT_DIR = Path("data/diagnostics/video4_outcome_forensic")
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
    raw_ball_candidates_by_frame = {}

    frames_list = list(reader)
    total = len(frames_list)
    print(f"Total frames: {total}", flush=True)

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
            {"x": round(dd.center[0], 1), "y": round(dd.center[1], 1), "conf": round(dd.confidence, 3)}
            for dd in validated
        ]
        rim_raw = rf.extract_rim_candidates(rf_raw)

        obs = ball_tracker.step(af.frame_index, af.timestamp_sec, validated)
        ball_observations.append(obs)
        hoop_candidates.extend((af.frame_index, x, y, r, c, "rfdetr") for (x, y, r, c) in rim_raw)

        if i % 300 == 0:
            print(f"...{i}/{total}", flush=True)

    pose_estimator.close()
    hoop = aggregate_hoop_candidates(hoop_candidates)
    print(f"Hoop: center=({hoop.rim_center_x:.1f},{hoop.rim_center_y:.1f}) r={hoop.rim_radius_px:.1f} "
          f"conf={hoop.confidence} votes={hoop.votes}", flush=True)

    frame_signals = build_frame_signals(frames_list, pose_frames, ball_observations, w, h)
    machine = ShotStateMachine(enable_trace=True)
    windows = machine.process(frame_signals)
    print(f"Detected {len(windows)} windows", flush=True)

    enriched_by_shot = enrich_near_hoop(VIDEO, meta, windows, ball_observations, hoop, w, h)
    ball_by_frame = {o.frame_index: o for o in ball_observations}

    def trigger_type(win):
        return "fallback (upward-flight-only)" if any(
            "load_phase_inferred" in x for x in win.warnings) else "primary (ball-hand proximity)"

    report = []
    cfg = CONFIG.outcome
    for win in windows:
        base_flight_start = win.release_candidate_frame or win.upward_start_frame or win.start_frame
        enriched_full = enriched_by_shot.get(win.shot_index, [])
        flight_points = [o for o in enriched_full if o.frame_index >= base_flight_start] if enriched_full else \
            [o for o in ball_observations if base_flight_start <= o.frame_index <= win.end_frame]

        # Re-derive with full visibility into every candidate pair considered,
        # using the REAL unmodified helper functions (read-only reuse).
        points = sorted(flight_points, key=lambda p: p.frame_index)
        reliable = od._reliable(points)
        reliable = od._reject_trajectory_outliers(reliable, cfg)
        candidates_dump = []
        apex = od._find_apex(reliable) if reliable else None
        if apex is not None and len(reliable) >= cfg.min_descent_points_to_attempt:
            descent_pts = [p for p in reliable if p.frame_index >= apex.frame_index]
            avg_radius = sum(p.radius_px for p in reliable) / len(reliable)
            tight_band = od._interaction_band(hoop, avg_radius, cfg)
            wide_band = od._wide_zone(hoop, avg_radius, cfg)
            descent_above_tight = [p for p in descent_pts if od._above_rim(p, hoop) and od._in_band(p, hoop, tight_band)]
            descent_below_tight = [p for p in descent_pts if od._below_rim(p, hoop) and od._in_band(p, hoop, tight_band)]
            max_drift = hoop.rim_radius_px * cfg.max_crossing_drift_frac_of_rim_radius
            for a in descent_above_tight:
                later_below = [b for b in descent_below_tight
                                if b.frame_index > a.frame_index
                                and (b.timestamp_sec - a.timestamp_sec) <= cfg.max_seconds_through_rim]
                for b in later_below:
                    drift = abs(b.center_x - a.center_x)
                    between = [p for p in reliable if a.frame_index < p.frame_index < b.frame_index]
                    deflected = any(not od._in_band(p, hoop, wide_band) for p in between)
                    dip = od._occlusion_dip_ratio([a] + between + [b], points) if not deflected else None
                    candidates_dump.append({
                        "a_frame": a.frame_index, "a_xy": [round(a.center_x, 1), round(a.center_y, 1)],
                        "b_frame": b.frame_index, "b_xy": [round(b.center_x, 1), round(b.center_y, 1)],
                        "drift_px": round(drift, 1), "max_drift_px": round(max_drift, 1),
                        "deflected_between": deflected,
                        "dip_ratio": round(dip, 3) if dip is not None else None,
                        "dip_cutoff": cfg.min_occlusion_dip_frac,
                        "passes_drift": drift <= max_drift, "passes_occlusion": (dip is not None and dip <= cfg.min_occlusion_dip_frac),
                    })
            # near-apex far-descent / beside / deflection evidence dump too
            near_apex_descent = [p for p in descent_pts
                                  if (p.timestamp_sec - apex.timestamp_sec) <= cfg.max_seconds_from_apex_for_descent_evidence]
            far_descent = [p for p in near_apex_descent if od._below_rim(p, hoop) and not od._in_band(p, hoop, wide_band)]
            far_descent_detail = [{"frame": p.frame_index, "xy": [round(p.center_x, 1), round(p.center_y, 1)],
                                     "t_since_apex": round(p.timestamp_sec - apex.timestamp_sec, 3),
                                     "source": p.source.value} for p in far_descent]
        else:
            far_descent_detail = []

        prod_outcome = od.detect_outcome(flight_points, hoop)

        report.append({
            "shot_index": win.shot_index,
            "start_frame": win.start_frame, "start_time": next((f.timestamp_sec for f in frame_signals if f.frame_index == win.start_frame), None),
            "load_start_frame": win.load_start_frame, "upward_start_frame": win.upward_start_frame,
            "release_frame": win.release_candidate_frame,
            "end_frame": win.end_frame,
            "trigger": trigger_type(win),
            "fsm_warnings": win.warnings,
            "outcome": prod_outcome.outcome.value, "outcome_confidence": prod_outcome.confidence,
            "outcome_reason": prod_outcome.reason,
            "n_candidate_pairs_evaluated": len(candidates_dump),
            "candidate_pairs": candidates_dump,
            "far_descent_detail": far_descent_detail,
        })

    (OUT_DIR / "shot_forensic_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== Trigger types ===")
    for r in report:
        print(f"shot {r['shot_index']}: trigger={r['trigger']} start_t={r['start_time']:.2f} "
              f"outcome={r['outcome']} conf={r['outcome_confidence']} n_candidates={r['n_candidate_pairs_evaluated']}")

    print(f"\nSaved: {OUT_DIR}/shot_forensic_report.json")


if __name__ == "__main__":
    main()
