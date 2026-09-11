"""
Produces a detailed, per-shot evidence timeline for a video: every detected
shot's start/release/end frames and times, the state-machine phase at each
analyzed frame, ball position/source/confidence, ball-hand distance,
vertical velocity, knee angle, and which trigger (primary ball-hand
proximity vs. fallback upward-flight-only) started it.

This is the primary tool for judging whether a detected shot is real or a
false positive from real footage -- run it, then look at the frames right
around each shot's start for what physically caused the state machine to
begin a LOAD/UPWARD phase there.

Usage:
    .venv\\Scripts\\python scripts\\shot_timeline_debug.py path\\to\\video.mp4 [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.events.shot_state_machine import ShotStateMachine
from app.pipeline.orchestrator import (
    LearnedBallDetector, LearnedHoopDetector, PoseEstimator, PrimaryShooterSelector,
    YoloMultiDetector, aggregate_hoop_candidates, build_frame_signals, detect_hoop_candidates,
    validate_ball_candidates,
)
from app.config import CONFIG, MODELS_DIR
from app.pipeline.video_io import FrameReader, validate_video
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector
from app.vision.types import BallObservation, DataSource, PoseFrame


def run_detection_only(video_path: Path, rfdetr_checkpoint_override: Path | None = None):
    """Same detection/pose/tracking pass as run_pipeline (including the
    RF-DETR-primary / generic-stack-fallback branch -- see
    app/pipeline/orchestrator.py), without annotation/analytics -- just
    what's needed to feed the state machine.

    ``rfdetr_checkpoint_override``: diagnostic-only escape hatch for A/B
    comparing an alternate checkpoint (e.g. a candidate fine-tune) without
    touching CONFIG.ball_rim_rfdetr.checkpoint_name -- production's actual
    checkpoint selection is untouched by this parameter; omitting it
    reproduces the exact existing behavior."""
    from app.tracking.ball_tracker import BallTracker

    meta = validate_video(video_path)
    reader = FrameReader(meta)
    w, h = reader.analysis_width, reader.analysis_height

    detector = YoloMultiDetector.get()  # still needed for "person" detection either way
    detector.warmup()

    rf_ball_rim_detector = None
    rfdetr_checkpoint = rfdetr_checkpoint_override or (MODELS_DIR / CONFIG.ball_rim_rfdetr.checkpoint_name)
    if CONFIG.ball_rim_rfdetr.enabled and rfdetr_checkpoint.exists():
        rf_ball_rim_detector = RFDETRBallRimDetector(str(rfdetr_checkpoint), CONFIG.ball_rim_rfdetr.confidence_floor)
        rf_ball_rim_detector.warmup()
        print("Using fine-tuned RF-DETR ball/rim detector.")

    learned_ball = learned_hoop = None
    if rf_ball_rim_detector is None:
        learned_ball = LearnedBallDetector.get() if CONFIG.ball.use_learned_detector else None
        if learned_ball:
            learned_ball.warmup()
        learned_hoop = LearnedHoopDetector.get() if CONFIG.hoop.use_learned_detector else None
        if learned_hoop:
            learned_hoop.warmup()
    pose_estimator = PoseEstimator()
    shooter_selector = PrimaryShooterSelector(min_track_frames=CONFIG.person.min_track_frames_for_primary)
    ball_tracker = BallTracker()

    pose_frames, ball_observations, hoop_candidates = [], [], []
    frames_list = list(reader)
    total = len(frames_list)
    hoop_stride = max(1, total // CONFIG.hoop.sample_frame_count)

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

        if rf_ball_rim_detector is not None:
            rf_raw = rf_ball_rim_detector.predict_raw(af.image)
            validated = rf_ball_rim_detector.extract_ball_detections(rf_raw, af.frame_index, af.timestamp_sec)
        else:
            validated = validate_ball_candidates(af.image, dets["ball_candidate"])
            if learned_ball is not None:
                validated = validated + learned_ball.detect(af.image, af.frame_index, af.timestamp_sec)
        obs = ball_tracker.step(af.frame_index, af.timestamp_sec, validated)
        ball_observations.append(obs)

        if i % hoop_stride == 0:
            if rf_ball_rim_detector is not None:
                hoop_candidates.extend((af.frame_index, x, y, r, c, "rfdetr")
                                         for (x, y, r, c) in rf_ball_rim_detector.extract_rim_candidates(rf_raw))
            else:
                hoop_candidates.extend((af.frame_index, x, y, r, c, "classical")
                                         for (x, y, r, c) in detect_hoop_candidates(af.image))
                if learned_hoop is not None:
                    hoop_candidates.extend((af.frame_index, x, y, r, c, "learned")
                                             for (x, y, r, c) in learned_hoop.detect(af.image))
        if i % 200 == 0:
            print(f"...{i}/{total} frames processed")

    pose_estimator.close()
    hoop = aggregate_hoop_candidates(hoop_candidates)
    return meta, frames_list, pose_frames, ball_observations, hoop, w, h


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=str)
    parser.add_argument("--out-dir", type=str, default=None)
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    out_dir = Path(args.out_dir) if args.out_dir else Path("data/diagnostics") / (video_path.stem + "_shot_timeline")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running detection pass on {video_path}...")
    meta, frames_list, pose_frames, ball_observations, hoop, w, h = run_detection_only(video_path)

    frame_signals = build_frame_signals(frames_list, pose_frames, ball_observations, w, h)

    machine = ShotStateMachine(enable_trace=True)
    windows = machine.process(frame_signals)
    print(f"\nDetected {len(windows)} candidate shot(s).")

    trace_by_frame = {t.frame_index: t for t in machine.trace}

    # Full per-frame trace CSV, for anything not covered by the summary below.
    import csv
    with (out_dir / "full_trace.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["frame_index", "timestamp_sec", "phase_before", "phase_after", "ball_available",
                           "ball_hand_dist_norm", "ball_vertical_velocity_norm", "knee_angle_deg",
                           "fallback_run", "separation_run", "stationary_run", "unavailable_run"])
        for t in machine.trace:
            writer.writerow([t.frame_index, round(t.timestamp_sec, 3), t.phase_before, t.phase_after,
                               t.ball_available, t.ball_hand_dist_norm, t.ball_vertical_velocity_norm,
                               t.knee_angle_deg, t.fallback_run, t.separation_run, t.stationary_run,
                               t.unavailable_run])

    ball_by_frame = {o.frame_index: o for o in ball_observations}

    report = []
    for w_ in windows:
        # Determine trigger: fallback if the warnings mention it.
        triggered_via = "fallback (upward-flight-only)" if any(
            "load_phase_inferred" in x for x in w_.warnings) else "primary (ball-hand proximity)"

        window_frames = list(range(w_.start_frame, w_.end_frame + 1))
        detail_rows = []
        for fi in window_frames:
            t = trace_by_frame.get(fi)
            obs = ball_by_frame.get(fi)
            fs = next((f for f in frame_signals if f.frame_index == fi), None)
            detail_rows.append({
                "frame": fi,
                "t": round(fs.timestamp_sec, 3) if fs else None,
                "phase": f"{t.phase_before}->{t.phase_after}" if t else None,
                "ball_src": obs.source.value if obs else None,
                "ball_conf": round(obs.confidence, 3) if obs else None,
                "ball_xy": (round(obs.center_x), round(obs.center_y)) if obs and obs.source != DataSource.UNAVAILABLE else None,
                "hand_dist": round(fs.ball_hand_dist_norm, 3) if fs and fs.ball_hand_dist_norm is not None else None,
                "vvel": round(fs.ball_vertical_velocity_norm, 3) if fs and fs.ball_vertical_velocity_norm is not None else None,
                "knee_deg": round(fs.knee_angle_deg, 1) if fs and fs.knee_angle_deg is not None else None,
            })

        shot_report = {
            "shot_index": w_.shot_index,
            "start_frame": w_.start_frame, "start_time": round(window_frames_time(frame_signals, w_.start_frame), 3),
            "load_start_frame": w_.load_start_frame,
            "upward_start_frame": w_.upward_start_frame,
            "release_frame": w_.release_candidate_frame,
            "release_time": round(window_frames_time(frame_signals, w_.release_candidate_frame), 3) if w_.release_candidate_frame is not None else None,
            "end_frame": w_.end_frame, "end_time": round(window_frames_time(frame_signals, w_.end_frame), 3),
            "trigger": triggered_via,
            "warnings": w_.warnings,
            "n_frames_in_window": len(window_frames),
            "detail": detail_rows,
        }
        report.append(shot_report)

    (out_dir / "shot_timeline.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n=== Shot timeline summary ===")
    for s in report:
        print(f"\nShot {s['shot_index']}: trigger={s['trigger']}")
        print(f"  start={s['start_frame']} (t={s['start_time']}s)  "
              f"load_start={s['load_start_frame']}  upward_start={s['upward_start_frame']}  "
              f"release={s['release_frame']} (t={s['release_time']}s)  end={s['end_frame']} (t={s['end_time']}s)")
        print(f"  warnings: {s['warnings']}")
        print(f"  frames in window: {s['n_frames_in_window']}")

    if hoop:
        print(f"\nHoop: center=({hoop.rim_center_x:.0f},{hoop.rim_center_y:.0f}) r={hoop.rim_radius_px:.0f} "
              f"conf={hoop.confidence} votes={hoop.votes} method={hoop.method}")

    print(f"\nSaved: {out_dir}/shot_timeline.json (full detail per shot), {out_dir}/full_trace.csv (every frame)")


def window_frames_time(frame_signals, frame_index):
    if frame_index is None:
        return None
    for f in frame_signals:
        if f.frame_index == frame_index:
            return f.timestamp_sec
    return None


if __name__ == "__main__":
    main()
