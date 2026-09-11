"""
MediaPipe BlazePose wrapper. Extracts the subset of landmarks the rest of
the pipeline needs (see POSE_LANDMARK_NAMES), applies light exponential
smoothing to reduce per-frame jitter, and reports a single pose-confidence
score per frame from landmark visibility so downstream code can exclude
low-quality frames instead of trusting noisy joints.

Smoothing is intentionally light and is meant to be disabled/frozen by the
caller for the few frames immediately around a candidate release event
(see app.config.PoseConfig.smoothing_freeze_window_frames), since heavy
smoothing would blur exactly the moment that matters most.
"""
from __future__ import annotations

from typing import List, Optional

import cv2
import numpy as np

from app.config import CONFIG
from app.logging_config import get_logger
from app.vision.types import Landmark, PoseFrame, POSE_LANDMARK_NAMES

log = get_logger("vision.pose")

# Maps our named joints to MediaPipe's PoseLandmark index.
_MP_INDEX = {
    "nose": 0,
    "left_shoulder": 11, "right_shoulder": 12,
    "left_elbow": 13, "right_elbow": 14,
    "left_wrist": 15, "right_wrist": 16,
    "left_hip": 23, "right_hip": 24,
    "left_knee": 25, "right_knee": 26,
    "left_ankle": 27, "right_ankle": 28,
}

_CORE_JOINTS_FOR_CONFIDENCE = (
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee",
)


class PoseEstimator:
    def __init__(self, cfg=None):
        import mediapipe as mp
        self.cfg = cfg or CONFIG.pose
        self._mp_pose = mp.solutions.pose
        self._pose = self._mp_pose.Pose(
            model_complexity=self.cfg.model_complexity,
            min_detection_confidence=self.cfg.min_detection_confidence,
            min_tracking_confidence=self.cfg.min_tracking_confidence,
            static_image_mode=False,
        )
        self._prev_smoothed: Optional[dict] = None

    def close(self):
        self._pose.close()

    def _extract(self, results, frame_index: int, timestamp_sec: float) -> PoseFrame:
        if not results.pose_landmarks:
            return PoseFrame(frame_index, timestamp_sec, detected=False)

        lm_list = results.pose_landmarks.landmark
        landmarks = {}
        for name, idx in _MP_INDEX.items():
            lm = lm_list[idx]
            landmarks[name] = Landmark(x=lm.x, y=lm.y, z=lm.z, visibility=lm.visibility)

        visibilities = [landmarks[n].visibility for n in _CORE_JOINTS_FOR_CONFIDENCE]
        pose_confidence = float(np.mean(visibilities)) if visibilities else 0.0

        return PoseFrame(frame_index, timestamp_sec, detected=True, landmarks=landmarks,
                          pose_confidence=pose_confidence)

    def _smooth(self, pf: PoseFrame, freeze: bool) -> PoseFrame:
        alpha = self.cfg.smoothing_alpha
        if not pf.detected:
            self._prev_smoothed = None
            return pf
        if self._prev_smoothed is None or freeze:
            self._prev_smoothed = {n: (l.x, l.y, l.z) for n, l in pf.landmarks.items()}
            pf.smoothed = freeze
            return pf

        new_smoothed = {}
        for name, lm in pf.landmarks.items():
            px, py, pz = self._prev_smoothed.get(name, (lm.x, lm.y, lm.z))
            sx = alpha * lm.x + (1 - alpha) * px
            sy = alpha * lm.y + (1 - alpha) * py
            sz = alpha * lm.z + (1 - alpha) * pz
            new_smoothed[name] = (sx, sy, sz)
            pf.landmarks[name] = Landmark(x=sx, y=sy, z=sz, visibility=lm.visibility)
        self._prev_smoothed = new_smoothed
        pf.smoothed = True
        return pf

    def process_frame(self, frame_bgr: np.ndarray, frame_index: int, timestamp_sec: float,
                       freeze_smoothing: bool = False) -> PoseFrame:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self._pose.process(rgb)
        pf = self._extract(results, frame_index, timestamp_sec)
        return self._smooth(pf, freeze=freeze_smoothing)

    def process_crop(self, frame_bgr: np.ndarray, bbox, frame_index: int, timestamp_sec: float,
                      freeze_smoothing: bool = False) -> PoseFrame:
        """Runs pose on a crop (e.g. the primary-shooter box) and maps
        landmarks back to full-frame normalized coordinates."""
        h, w = frame_bgr.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return PoseFrame(frame_index, timestamp_sec, detected=False)

        crop = frame_bgr[y1:y2, x1:x2]
        pf = self.process_frame(crop, frame_index, timestamp_sec, freeze_smoothing)
        if not pf.detected:
            return pf

        cw, ch = (x2 - x1), (y2 - y1)
        remapped = {}
        for name, lm in pf.landmarks.items():
            remapped[name] = Landmark(
                x=(x1 + lm.x * cw) / w,
                y=(y1 + lm.y * ch) / h,
                z=lm.z,
                visibility=lm.visibility,
            )
        pf.landmarks = remapped
        return pf
