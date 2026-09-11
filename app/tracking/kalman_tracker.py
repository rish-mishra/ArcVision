"""
A small constant-velocity Kalman filter and a single-object track manager
built on top of it. This is intentionally lightweight (no external tracking
library) since the tracking problem here is narrow: follow one ball (or
aggregate one hoop) across frames, bridge short detector gaps, and clearly
mark when a position is no longer defensible.

State vector: [x, y, vx, vy] in analysis-resolution pixel coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.vision.types import DataSource


class ConstantVelocityKalmanFilter:
    def __init__(self, x: float, y: float, process_noise: float = 8.0, measurement_noise: float = 4.0):
        self.state = np.array([x, y, 0.0, 0.0], dtype=np.float64)
        self.P = np.eye(4) * 50.0
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float64)

    def _F(self, dt: float) -> np.ndarray:
        return np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=np.float64)

    def _Q(self, dt: float) -> np.ndarray:
        q = self.process_noise
        return np.array([
            [dt**4/4, 0, dt**3/2, 0],
            [0, dt**4/4, 0, dt**3/2],
            [dt**3/2, 0, dt**2, 0],
            [0, dt**3/2, 0, dt**2],
        ]) * q

    def predict(self, dt: float) -> None:
        F = self._F(dt)
        self.state = F @ self.state
        self.P = F @ self.P @ F.T + self._Q(dt)

    def update(self, z: np.ndarray) -> None:
        R = np.eye(2) * self.measurement_noise
        y = z - self.H @ self.state
        S = self.H @ self.P @ self.H.T + R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.state = self.state + K @ y
        self.P = (np.eye(4) - K @ self.H) @ self.P

    @property
    def position(self):
        return float(self.state[0]), float(self.state[1])

    @property
    def velocity(self):
        return float(self.state[2]), float(self.state[3])


@dataclass
class TrackedPoint:
    frame_index: int
    timestamp_sec: float
    x: float
    y: float
    source: DataSource
    confidence: float


class SingleObjectTracker:
    """
    Feed it detections (or None for a missed frame) in frame order; it
    returns the best-estimate position for every frame, correctly labeled
    as detected / interpolated / predicted / unavailable.
    """

    def __init__(self, max_age_frames: int = 12, max_center_jump_px: float = 140.0,
                 max_extrapolation_frames: int = 6):
        self.max_age_frames = max_age_frames
        self.max_center_jump_px = max_center_jump_px
        self.max_extrapolation_frames = max_extrapolation_frames
        self.kf: Optional[ConstantVelocityKalmanFilter] = None
        self.last_frame_index: Optional[int] = None
        self.misses_in_a_row = 0
        self.history: list[TrackedPoint] = []

    def _expected_jump_ok(self, x: float, y: float) -> bool:
        if self.kf is None:
            return True
        px, py = self.kf.position
        dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
        return dist <= self.max_center_jump_px * max(1, self.misses_in_a_row + 1)

    def step(self, frame_index: int, timestamp_sec: float,
              detection_xy: Optional[tuple], confidence: float = 0.0) -> TrackedPoint:
        dt = 1.0 / 30.0
        if self.last_frame_index is not None:
            dt = max(1e-3, timestamp_sec - self.history[-1].timestamp_sec) if self.history else dt

        if self.kf is None:
            if detection_xy is None:
                pt = TrackedPoint(frame_index, timestamp_sec, np.nan, np.nan,
                                   DataSource.UNAVAILABLE, 0.0)
                self.history.append(pt)
                self.last_frame_index = frame_index
                return pt
            self.kf = ConstantVelocityKalmanFilter(detection_xy[0], detection_xy[1])
            pt = TrackedPoint(frame_index, timestamp_sec, detection_xy[0], detection_xy[1],
                               DataSource.DETECTED, confidence)
            self.history.append(pt)
            self.misses_in_a_row = 0
            self.last_frame_index = frame_index
            return pt

        self.kf.predict(dt)

        if detection_xy is not None and self._expected_jump_ok(*detection_xy):
            self.kf.update(np.array(detection_xy, dtype=np.float64))
            self.misses_in_a_row = 0
            pt = TrackedPoint(frame_index, timestamp_sec, detection_xy[0], detection_xy[1],
                               DataSource.DETECTED, confidence)
        else:
            self.misses_in_a_row += 1
            if self.misses_in_a_row <= self.max_extrapolation_frames:
                px, py = self.kf.position
                source = DataSource.INTERPOLATED if self.misses_in_a_row <= 3 else DataSource.PREDICTED
                decay = max(0.0, 1.0 - self.misses_in_a_row / (self.max_extrapolation_frames + 1))
                pt = TrackedPoint(frame_index, timestamp_sec, px, py, source, 0.3 * decay)
            else:
                pt = TrackedPoint(frame_index, timestamp_sec, np.nan, np.nan,
                                   DataSource.UNAVAILABLE, 0.0)

        self.history.append(pt)
        self.last_frame_index = frame_index
        return pt
