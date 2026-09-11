"""
Developer/debug overlay: numeric confidences, data provenance (detected vs
interpolated vs predicted vs unavailable), per-joint pose visibility, and
hoop aggregation confidence -- everything needed to diagnose *why* the
pipeline made a given call on a real video, as opposed to the clean
replay's minimal overlay. For raw per-frame detector candidate boxes
(before tracking/validation), use scripts/diagnose_video.py instead, which
runs the detectors standalone and dumps every candidate.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import cv2

from app.analytics.shot_record import ShotRecord
from app.logging_config import get_logger
from app.pipeline.video_io import FrameReader, VideoMeta, transcode_to_browser_mp4
from app.vision.types import BallObservation, DataSource, HoopLocation, PoseFrame

log = get_logger("annotation.diagnostic")

_SOURCE_COLORS = {
    DataSource.DETECTED: (0, 255, 0),
    DataSource.INTERPOLATED: (0, 255, 255),
    DataSource.PREDICTED: (0, 140, 255),
    DataSource.UNAVAILABLE: (0, 0, 255),
}

_JOINTS = ("left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
           "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle")


def _hud_line(img, text, y, color=(255, 255, 255)):
    cv2.putText(img, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


def render_diagnostic_video(video_path: Path, meta: VideoMeta, shots: List[ShotRecord],
                              hoop: Optional[HoopLocation], pose_frames: List[PoseFrame],
                              ball_observations: List[BallObservation], output_path: Path) -> Path:
    reader = FrameReader(meta)
    w, h = reader.analysis_width, reader.analysis_height
    pose_by_frame = {p.frame_index: p for p in pose_frames}
    ball_by_frame = {o.frame_index: o for o in ball_observations}

    raw_output = output_path.with_suffix(".raw.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(raw_output), fourcc, reader.effective_fps, (w, h))

    try:
        for af in reader:
            frame = af.image.copy()
            pf = pose_by_frame.get(af.frame_index)
            obs = ball_by_frame.get(af.frame_index)

            if pf and pf.detected:
                for joint in _JOINTS:
                    lm = pf.landmark(joint)
                    if lm is None:
                        continue
                    color = (0, int(255 * lm.visibility), int(255 * (1 - lm.visibility)))
                    cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 3, color, -1, cv2.LINE_AA)

            if obs is not None and obs.source != DataSource.UNAVAILABLE:
                color = _SOURCE_COLORS[obs.source]
                cv2.circle(frame, (int(obs.center_x), int(obs.center_y)), int(obs.radius_px), color, 2, cv2.LINE_AA)
                cv2.putText(frame, f"{obs.source.value} {obs.confidence:.2f}",
                             (int(obs.center_x) + 10, int(obs.center_y)),
                             cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)

            if hoop:
                center = (int(hoop.rim_center_x), int(hoop.rim_center_y))
                cv2.ellipse(frame, center, (int(hoop.rim_radius_px), int(hoop.rim_radius_px * 0.35)), 0, 0, 360,
                             (255, 140, 0), 1, cv2.LINE_AA)

            y = 20
            _hud_line(frame, f"frame={af.frame_index} t={af.timestamp_sec:.2f}s", y); y += 18
            _hud_line(frame, f"pose_conf={pf.pose_confidence:.2f}" if pf else "pose=none", y); y += 18
            if obs:
                _hud_line(frame, f"ball_src={obs.source.value} conf={obs.confidence:.2f}", y); y += 18
            _hud_line(frame, f"hoop_conf={hoop.confidence:.2f} votes={hoop.votes}" if hoop else "hoop=none", y)
            y += 18

            for s in shots:
                if s.start_time_sec <= af.timestamp_sec <= s.end_time_sec:
                    _hud_line(frame, f"shot#{s.shot_index} outcome={s.outcome.value} "
                                       f"rel_conf={s.release_confidence:.2f} side={s.shooting_side}", y,
                               (0, 255, 255))
                    break

            writer.write(frame)
    finally:
        writer.release()

    transcode_to_browser_mp4(raw_output, output_path)
    raw_output.unlink(missing_ok=True)
    log.info("Wrote diagnostic video to %s", output_path)
    return output_path
