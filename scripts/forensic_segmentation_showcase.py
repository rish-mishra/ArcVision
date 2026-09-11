"""
READ-ONLY forensic script for arcvision_demo_final.mov's TWO known false shot
events (~11.104s, ~87.728s), per docs/FINAL_DEMO_BLIND_EVALUATION.md.
Reproduces the exact same detection/tracking/state-machine pass production
uses, but with ShotStateMachine(enable_trace=True) so every frame's
IDLE/LOAD/UPWARD/FLIGHT transition is recorded. Makes no production code
change. Dumps windows + full per-frame trace to JSON and prints a
frame-by-frame table around each false event plus its neighboring genuine
shot for direct comparison.
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
from app.vision.types import PoseFrame

VIDEO = Path("arcvision_demo_final.mov").resolve()
OUT_DIR = Path("data/diagnostics/arcvision_demo_final_segmentation_forensic")
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

    fs_dump = [{
        "frame_index": f.frame_index, "timestamp_sec": f.timestamp_sec, "ball_available": f.ball_available,
        "ball_x": f.ball_x, "ball_y": f.ball_y, "ball_hand_dist_norm": f.ball_hand_dist_norm,
        "ball_vertical_velocity_norm": f.ball_vertical_velocity_norm, "knee_angle_deg": f.knee_angle_deg,
        "shoulder_y": f.shoulder_y, "pose_confidence": f.pose_confidence, "ball_is_observed": f.ball_is_observed,
        "hip_x_norm": f.hip_x_norm,
    } for f in frame_signals]
    (OUT_DIR / "frame_signals.json").write_text(json.dumps(fs_dump), encoding="utf-8")

    machine = ShotStateMachine(enable_trace=True)
    windows = machine.process(frame_signals)
    print(f"Detected {len(windows)} windows", flush=True)

    def trigger_type(win):
        return "fallback (upward-flight-only)" if any(
            "load_phase_inferred" in x for x in win.warnings) else "primary (ball-hand proximity)"

    win_report = []
    for win in windows:
        start_t = next((f.timestamp_sec for f in frame_signals if f.frame_index == win.start_frame), None)
        release_frame = win.release_candidate_frame
        release_t = next((f.timestamp_sec for f in frame_signals if f.frame_index == release_frame), None) \
            if release_frame is not None else None
        win_report.append({
            "shot_index": win.shot_index, "start_frame": win.start_frame, "start_time": start_t,
            "load_start_frame": win.load_start_frame, "upward_start_frame": win.upward_start_frame,
            "release_frame": release_frame, "release_time": release_t,
            "end_frame": win.end_frame, "trigger": trigger_type(win), "warnings": win.warnings,
            "load_to_upward_frames": (win.upward_start_frame - win.load_start_frame)
                if (win.upward_start_frame is not None and win.load_start_frame is not None) else None,
        })
        print(f"shot {win.shot_index}: trigger={trigger_type(win)} start_t={start_t:.3f} "
              f"load@{win.load_start_frame} upward@{win.upward_start_frame} "
              f"release@{release_frame}({release_t}) end@{win.end_frame} warnings={win.warnings}", flush=True)

    trace_rows = [{
        "frame_index": t.frame_index, "timestamp_sec": t.timestamp_sec,
        "phase_before": t.phase_before, "phase_after": t.phase_after,
        "ball_available": t.ball_available, "ball_hand_dist_norm": t.ball_hand_dist_norm,
        "ball_vertical_velocity_norm": t.ball_vertical_velocity_norm, "knee_angle_deg": t.knee_angle_deg,
        "fallback_run": t.fallback_run, "separation_run": t.separation_run,
        "stationary_run": t.stationary_run, "unavailable_run": t.unavailable_run,
    } for t in machine.trace]

    fs_by_frame = {f.frame_index: f for f in frame_signals}

    (OUT_DIR / "windows.json").write_text(json.dumps(win_report, indent=2), encoding="utf-8")
    (OUT_DIR / "trace.json").write_text(json.dumps(trace_rows, indent=2), encoding="utf-8")

    def dump_window_seconds(center_t, label, pad_before=1.5, pad_after=1.5):
        print(f"\n=== {label} (around t={center_t:.3f}s) ===")
        for row in trace_rows:
            if center_t - pad_before <= row["timestamp_sec"] <= center_t + pad_after:
                fs = fs_by_frame.get(row["frame_index"])
                lw = fs.left_wrist_xy if fs else None
                rw = fs.right_wrist_xy if fs else None
                transition = f"{row['phase_before']}->{row['phase_after']}" if row["phase_before"] != row["phase_after"] else row["phase_after"]
                print(f"  f{row['frame_index']:5d} t={row['timestamp_sec']:7.3f} {transition:14s} "
                      f"ball_avail={str(row['ball_available']):5s} hand_d={row['ball_hand_dist_norm']} "
                      f"vvel={row['ball_vertical_velocity_norm']} knee={row['knee_angle_deg']} "
                      f"lw={lw} rw={rw}")

    dump_window_seconds(11.104, "FALSE EVENT #1")
    dump_window_seconds(12.104, "NEIGHBORING GENUINE SHOT (truth shot 2)")
    dump_window_seconds(87.728, "FALSE EVENT #2")
    dump_window_seconds(89.729, "NEIGHBORING GENUINE SHOT (truth shot 10)")

    print(f"\nSaved: {OUT_DIR}/windows.json, {OUT_DIR}/trace.json")


if __name__ == "__main__":
    main()
