"""
Associates per-frame ball detection candidates (there may be zero, one, or
several -- e.g. two "sports ball" boxes because of a similarly colored
object in the background) into a single coherent ball track over time.
"""
from __future__ import annotations

from typing import List, Optional

from app.config import CONFIG
from app.logging_config import get_logger
from app.tracking.kalman_tracker import SingleObjectTracker
from app.vision.types import BallObservation, DataSource, Detection

log = get_logger("tracking.ball")


class BallTracker:
    def __init__(self):
        cfg = CONFIG.tracker
        self._tracker = SingleObjectTracker(
            max_age_frames=cfg.max_age_frames,
            max_center_jump_px=cfg.max_center_jump_px_per_frame,
            max_extrapolation_frames=cfg.max_extrapolation_frames,
        )
        self._track_id = 1
        self._radius_ema: Optional[float] = None

    def _pick_best_candidate(self, candidates: List[Detection]) -> Optional[Detection]:
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        if self._tracker.kf is not None:
            px, py = self._tracker.kf.position
            def dist(d: Detection) -> float:
                cx, cy = d.center
                return ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            candidates = sorted(candidates, key=lambda d: (dist(d), -d.confidence))
            return candidates[0]
        return max(candidates, key=lambda d: d.confidence)

    def step(self, frame_index: int, timestamp_sec: float,
             candidates: List[Detection]) -> BallObservation:
        best = self._pick_best_candidate(candidates)
        xy = best.center if best else None
        conf = best.confidence if best else 0.0

        point = self._tracker.step(frame_index, timestamp_sec, xy, conf)

        if best is not None:
            r = max(best.width, best.height) / 2.0
            self._radius_ema = r if self._radius_ema is None else 0.7 * self._radius_ema + 0.3 * r
        radius = self._radius_ema or 8.0

        return BallObservation(
            frame_index=frame_index,
            timestamp_sec=timestamp_sec,
            center_x=point.x,
            center_y=point.y,
            radius_px=radius,
            confidence=point.confidence,
            source=point.source,
            track_id=self._track_id,
        )
