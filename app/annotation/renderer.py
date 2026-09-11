"""
Renders the clean, user-facing annotated replay: pose skeleton, tracked
ball with a short trajectory trail, hoop location, current shot number,
a RELEASE marker at the release moment, and the MAKE/MISS/UNKNOWN result
after each shot. Deliberately restrained -- this is not the diagnostic
overlay (see diagnostic_renderer.py), so it avoids piling on numeric
readouts that would clutter the replay.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from app.analytics.shot_record import ShotRecord
from app.events.outcome_detector import ShotOutcome
from app.logging_config import get_logger
from app.pipeline.video_io import FrameReader, VideoMeta, transcode_to_browser_mp4
from app.vision.types import BallObservation, DataSource, HoopLocation, PoseFrame

log = get_logger("annotation.renderer")

_SKELETON_EDGES = [
    ("left_shoulder", "right_shoulder"), ("left_hip", "right_hip"),
    ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
    ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
    ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
]

_COLOR_SKELETON = (60, 220, 255)
_COLOR_BALL_DETECTED = (0, 255, 90)
_COLOR_BALL_SOFT = (0, 200, 255)
_COLOR_HOOP = (255, 140, 0)
_COLOR_TEXT_BG = (20, 20, 20)
_OUTCOME_COLOR = {
    ShotOutcome.MADE: (0, 220, 0),
    ShotOutcome.MISSED: (0, 0, 230),
    ShotOutcome.UNKNOWN: (0, 200, 255),
}


def _draw_label(img, text, org, color=(255, 255, 255), scale=0.6, thickness=1):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    x, y = org
    cv2.rectangle(img, (x - 4, y - th - 6), (x + tw + 4, y + 4), _COLOR_TEXT_BG, -1)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def _draw_skeleton(img, pf: PoseFrame, w: int, h: int):
    if not pf.detected:
        return
    for a, b in _SKELETON_EDGES:
        la, lb = pf.landmark(a), pf.landmark(b)
        if la and lb and la.visibility > 0.4 and lb.visibility > 0.4:
            p1 = (int(la.x * w), int(la.y * h))
            p2 = (int(lb.x * w), int(lb.y * h))
            cv2.line(img, p1, p2, _COLOR_SKELETON, 2, cv2.LINE_AA)
    for name in ("left_wrist", "right_wrist", "left_shoulder", "right_shoulder"):
        lm = pf.landmark(name)
        if lm and lm.visibility > 0.4:
            cv2.circle(img, (int(lm.x * w), int(lm.y * h)), 4, _COLOR_SKELETON, -1, cv2.LINE_AA)


def _draw_ball_trail(img, trail: List[BallObservation]):
    n = len(trail)
    for i, obs in enumerate(trail):
        if obs.source == DataSource.UNAVAILABLE or np.isnan(obs.center_x):
            continue
        alpha = (i + 1) / max(n, 1)
        color = _COLOR_BALL_DETECTED if obs.source == DataSource.DETECTED else _COLOR_BALL_SOFT
        radius = max(2, int(obs.radius_px * (0.4 + 0.6 * alpha)))
        cv2.circle(img, (int(obs.center_x), int(obs.center_y)), radius, color, 2, cv2.LINE_AA)


def _draw_hoop(img, hoop: Optional[HoopLocation]):
    if hoop is None:
        return
    center = (int(hoop.rim_center_x), int(hoop.rim_center_y))
    cv2.ellipse(img, center, (int(hoop.rim_radius_px), int(hoop.rim_radius_px * 0.35)), 0, 0, 360,
                 _COLOR_HOOP, 2, cv2.LINE_AA)


def _active_shot_for_time(shots: List[ShotRecord], t: float, post_result_window: float = 1.2) -> Optional[ShotRecord]:
    for s in shots:
        if s.start_time_sec <= t <= s.end_time_sec + post_result_window:
            return s
    return None


def render_annotated_video(video_path: Path, meta: VideoMeta, shots: List[ShotRecord],
                             hoop: Optional[HoopLocation], pose_frames: List[PoseFrame],
                             ball_observations: List[BallObservation], output_path: Path) -> Path:
    reader = FrameReader(meta)
    w, h = reader.analysis_width, reader.analysis_height
    pose_by_frame = {p.frame_index: p for p in pose_frames}
    ball_by_frame = {o.frame_index: o for o in ball_observations}

    raw_output = output_path.with_suffix(".raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(raw_output), fourcc, reader.effective_fps, (w, h))

    trail_len = 10
    try:
        for af in reader:
            frame = af.image.copy()
            pf = pose_by_frame.get(af.frame_index)
            if pf:
                _draw_skeleton(frame, pf, w, h)

            trail = [ball_by_frame[i] for i in range(max(0, af.frame_index - trail_len), af.frame_index + 1)
                     if i in ball_by_frame]
            _draw_ball_trail(frame, trail)
            _draw_hoop(frame, hoop)

            shot = _active_shot_for_time(shots, af.timestamp_sec)
            if shot:
                _draw_label(frame, f"SHOT {shot.shot_index}", (12, 30), (255, 255, 255))
                if shot.release_time_sec is not None and abs(af.timestamp_sec - shot.release_time_sec) < 0.12:
                    _draw_label(frame, "RELEASE", (12, 60), (0, 255, 255))
                if af.timestamp_sec > shot.end_time_sec:
                    color = _OUTCOME_COLOR.get(shot.outcome, (255, 255, 255))
                    label = shot.outcome.value.upper()
                    if shot.outcome == ShotOutcome.UNKNOWN:
                        label = "UNKNOWN"
                    _draw_label(frame, label, (12, 90), color, scale=0.8, thickness=2)

            writer.write(frame)
    finally:
        writer.release()

    transcode_to_browser_mp4(raw_output, output_path)
    raw_output.unlink(missing_ok=True)
    log.info("Wrote annotated video to %s", output_path)
    return output_path
