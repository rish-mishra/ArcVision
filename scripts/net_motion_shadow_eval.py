"""
READ-ONLY diagnostic evaluation for the SHADOW-ONLY app/research/net_motion_resolver.py
module (docs/NET_MOTION_SHADOW.md). Does NOT re-run RF-DETR/pose -- reuses
existing cached forensic reports (shot windows) and existing per-frame ball
position caches, and decodes ONLY the bounded frame ranges needed (grayscale,
via a single sequential pass per video) directly from the source video files.
Produces diagnostic JSON (raw/relative motion measurements, no MADE/MISSED
verdict) plus human-viewable PNG panels (pre/interaction/post frames, ROI
overlay, per-pixel diff visualization) for visual sanity-checking. Makes no
production code change and reuses the same read-only pattern as this
session's other diagnostic scripts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.video_io import FrameReader, validate_video
from app.research.net_motion_resolver import BallSample, analyze_net_motion_from_frames
from app.vision.types import HoopLocation

OUT_DIR = Path("data/diagnostics/net_motion_shadow")
OUT_DIR.mkdir(parents=True, exist_ok=True)


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


def dense_ball_lookup(frame_signals_path: Path | None):
    """Showcase only: dense per-frame ball_x/ball_y (no radius -- resolver
    falls back to its physically-reasoned ball-radius proportion, per its
    own docstring, exactly the documented use case for that fallback)."""
    if frame_signals_path is None or not frame_signals_path.exists():
        return {}
    data = json.loads(frame_signals_path.read_text(encoding="utf-8"))
    out = {}
    for f in data:
        if f["ball_available"]:
            out[f["frame_index"]] = BallSample(frame_index=f["frame_index"], center_x=f["ball_x"], center_y=f["ball_y"])
    return out


def sparse_ball_lookup(outcome_forensic_report: list, shot_index: int):
    """V4 only: sparse ball positions from cached candidate-pair samples
    (only tight-band frames have positions available without re-running
    detection) -- an honest limitation, documented in the report."""
    shot = next(s for s in outcome_forensic_report if s["shot_index"] == shot_index)
    out = {}
    for c in shot["candidate_pairs"]:
        out[c["a_frame"]] = BallSample(frame_index=c["a_frame"], center_x=c["a_xy"][0], center_y=c["a_xy"][1])
        out[c["b_frame"]] = BallSample(frame_index=c["b_frame"], center_x=c["b_xy"][0], center_y=c["b_xy"][1])
    for p in shot["far_descent_detail"]:
        out[p["frame"]] = BallSample(frame_index=p["frame"], center_x=p["xy"][0], center_y=p["xy"][1])
    return out


def decode_gray_frames(video_path: Path, wanted_frames: set):
    meta = validate_video(video_path)
    reader = FrameReader(meta)
    out = {}
    max_wanted = max(wanted_frames)
    for af in reader:
        if af.frame_index > max_wanted:
            break
        if af.frame_index in wanted_frames:
            out[af.frame_index] = cv2.cvtColor(af.image, cv2.COLOR_BGR2GRAY)
    return out


def save_panel(gray_by_frame: dict, frame_indices: list, ep, out_path: Path, title: str):
    if len(frame_indices) < 2:
        return
    pre_fi = frame_indices[0]
    # "strongest post-interaction frame" = the frame pair with max relative motion
    if ep.relative_motion_series:
        peak_i = int(np.argmax(ep.relative_motion_series)) + 1  # index into frame_indices
        peak_fi = frame_indices[peak_i]
    else:
        peak_fi = frame_indices[len(frame_indices) // 2]
    mid_fi = frame_indices[len(frame_indices) // 2]

    def to_bgr_with_roi(fi):
        g = gray_by_frame[fi]
        bgr = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
        if ep.net_roi:
            cv2.rectangle(bgr, (ep.net_roi.x0, ep.net_roi.y0), (ep.net_roi.x1, ep.net_roi.y1), (0, 255, 0), 1)
        if ep.control_roi_left:
            cv2.rectangle(bgr, (ep.control_roi_left.x0, ep.control_roi_left.y0), (ep.control_roi_left.x1, ep.control_roi_left.y1), (255, 200, 0), 1)
        if ep.control_roi_right:
            cv2.rectangle(bgr, (ep.control_roi_right.x0, ep.control_roi_right.y0), (ep.control_roi_right.x1, ep.control_roi_right.y1), (255, 200, 0), 1)
        return bgr

    tiles = [to_bgr_with_roi(pre_fi), to_bgr_with_roi(mid_fi), to_bgr_with_roi(peak_fi)]
    labels = [f"pre f{pre_fi}", f"mid f{mid_fi}", f"peak-relmotion f{peak_fi}"]

    # Diff visualization for the peak pair.
    if peak_fi in gray_by_frame and frame_indices.index(peak_fi) > 0:
        prev_fi = frame_indices[frame_indices.index(peak_fi) - 1]
        diff = cv2.absdiff(gray_by_frame[peak_fi], gray_by_frame[prev_fi])
        diff_vis = cv2.applyColorMap(np.clip(diff.astype(np.int32) * 4, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
        if ep.net_roi:
            cv2.rectangle(diff_vis, (ep.net_roi.x0, ep.net_roi.y0), (ep.net_roi.x1, ep.net_roi.y1), (0, 255, 0), 1)
        tiles.append(diff_vis)
        labels.append(f"diff f{prev_fi}->f{peak_fi} (x4 gain)")

    h = 220
    resized = []
    for t in tiles:
        scale = h / t.shape[0]
        resized.append(cv2.resize(t, (int(t.shape[1] * scale), h)))
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


def run_showcase():
    hoop = HoopLocation(rim_center_x=300.7, rim_center_y=146.2, rim_radius_px=28.2, confidence=0.968, votes=2954, method="rfdetr")
    report = json.loads(Path("data/diagnostics/arcvision_demo_final_forensic/shot_forensic_report.json").read_text(encoding="utf-8"))
    ball_lookup = dense_ball_lookup(Path("data/diagnostics/arcvision_demo_final_segmentation_forensic/frame_signals.json"))

    targets = [1, 3, 9, 10, 11, 5, 8]
    windows = {}
    wanted = set()
    for idx in targets:
        shot = next(s for s in report if s["shot_index"] == idx)
        lo, hi = shot_window(shot)
        windows[idx] = list(range(lo, hi + 1))
        wanted.update(windows[idx])

    print(f"SHOWCASE: decoding {len(wanted)} frames...")
    gray_by_frame = decode_gray_frames(Path("arcvision_demo_final.mov").resolve(), wanted)

    results = []
    for idx in targets:
        frame_indices = [fi for fi in windows[idx] if fi in gray_by_frame]
        frames = [gray_by_frame[fi] for fi in frame_indices]
        ep = analyze_net_motion_from_frames(frames, frame_indices, hoop, ball_lookup)
        shot = next(s for s in report if s["shot_index"] == idx)
        results.append({
            "shot_index": idx, "production": {"outcome": shot["outcome"], "confidence": shot["outcome_confidence"], "reason": shot["outcome_reason"]},
            "episode": {k: v for k, v in ep.__dict__.items() if k not in ("net_roi", "control_roi_left", "control_roi_right")},
        })
        print(f"shot {idx}: prod={shot['outcome']}({shot['outcome_confidence']:.2f}) "
              f"n_pairs={ep.n_frame_pairs} elevated={ep.n_elevated_pairs} max_rel={ep.max_relative_motion:.2f} mean_rel={ep.mean_relative_motion:.2f}")
        save_panel(gray_by_frame, frame_indices, ep, OUT_DIR / f"showcase_shot{idx:02d}.png",
                    f"SHOWCASE shot {idx} prod={shot['outcome']}({shot['outcome_confidence']:.2f})")

    (OUT_DIR / "showcase_net_motion.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved: {OUT_DIR}/showcase_net_motion.json\n")


def run_v4():
    hoop = HoopLocation(rim_center_x=262.7, rim_center_y=154.5, rim_radius_px=29.9, confidence=0.961, votes=5761, method="rfdetr")
    report = json.loads(Path("data/diagnostics/video4_outcome_forensic/shot_forensic_report.json").read_text(encoding="utf-8"))

    targets = [9, 17, 21, 15, 19, 4, 5]
    windows = {}
    wanted = set()
    for idx in targets:
        shot = next(s for s in report if s["shot_index"] == idx)
        lo, hi = shot_window(shot)
        windows[idx] = list(range(lo, hi + 1))
        wanted.update(windows[idx])

    print(f"V4: decoding {len(wanted)} frames...")
    gray_by_frame = decode_gray_frames(Path("real_test_04.mov").resolve(), wanted)

    results = []
    for idx in targets:
        ball_lookup = sparse_ball_lookup(report, idx)
        frame_indices = [fi for fi in windows[idx] if fi in gray_by_frame]
        frames = [gray_by_frame[fi] for fi in frame_indices]
        ep = analyze_net_motion_from_frames(frames, frame_indices, hoop, ball_lookup)
        shot = next(s for s in report if s["shot_index"] == idx)
        results.append({
            "shot_index": idx, "production": {"outcome": shot["outcome"], "confidence": shot["outcome_confidence"], "reason": shot["outcome_reason"]},
            "episode": {k: v for k, v in ep.__dict__.items() if k not in ("net_roi", "control_roi_left", "control_roi_right")},
        })
        print(f"shot {idx}: prod={shot['outcome']}({shot['outcome_confidence']:.2f}) "
              f"n_pairs={ep.n_frame_pairs} elevated={ep.n_elevated_pairs} max_rel={ep.max_relative_motion:.2f} mean_rel={ep.mean_relative_motion:.2f}")
        save_panel(gray_by_frame, frame_indices, ep, OUT_DIR / f"v4_shot{idx:02d}.png",
                    f"V4 shot {idx} prod={shot['outcome']}({shot['outcome_confidence']:.2f})")

    (OUT_DIR / "v4_net_motion.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved: {OUT_DIR}/v4_net_motion.json\n")


if __name__ == "__main__":
    run_showcase()
    run_v4()
