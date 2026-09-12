"""Determines which arm is the shooting arm for a given shot attempt."""
from __future__ import annotations

from typing import List, Optional

from app.biomechanics.geometry import distance
from app.vision.types import PoseFrame


def determine_shooting_side(pose_frames: List[PoseFrame], ball_positions: dict,
                             start_frame: int, end_frame: int) -> Optional[str]:
    """
    ball_positions: {frame_index: (x, y)} for frames with a reliable ball
    observation. Compares each arm's wrist-ball distance across the shot
    window; the closer wrist, on average, is the shooting hand.

    The average is weighted by each sample's landmark visibility (the same
    per-landmark confidence score already used everywhere else in this
    pipeline to gate quality -- e.g. the >=0.4 inclusion floor below, or the
    warnings in app/events/shot_state_machine.py), not a new signal. An
    unweighted mean previously let a handful of low-visibility, effectively
    noisy samples on one side outweigh many high-visibility samples on the
    other side whenever they happened to average out slightly closer to the
    ball -- observed in practice as the same shooter's shooting_side flipping
    left/right/left across consecutive shots in one session despite one
    wrist being consistently and substantially better-tracked than the other
    in every single one of them (visibility ~0.85-0.98 vs ~0.16-0.54 at
    release, for all 11 shots in the frozen demo session). Weighting by
    visibility means a handful of barely-passing 0.4-visibility samples can
    no longer outvote a consistently well-tracked side; it does not change
    what "left"/"right" mean (MediaPipe's own anatomical labeling, passed
    through unchanged) or add any new fitted threshold.
    """
    left_samples, right_samples = [], []  # (distance, visibility) pairs
    for pf in pose_frames:
        if not (start_frame <= pf.frame_index <= end_frame):
            continue
        ball = ball_positions.get(pf.frame_index)
        if ball is None:
            continue
        lw = pf.landmark("left_wrist")
        rw = pf.landmark("right_wrist")
        if lw and lw.visibility >= 0.4:
            left_samples.append((distance((lw.x, lw.y), ball), lw.visibility))
        if rw and rw.visibility >= 0.4:
            right_samples.append((distance((rw.x, rw.y), ball), rw.visibility))

    def weighted_mean(samples):
        total_weight = sum(v for _, v in samples)
        if total_weight <= 0:
            return None
        return sum(d * v for d, v in samples) / total_weight

    left_mean = weighted_mean(left_samples)
    right_mean = weighted_mean(right_samples)
    if left_mean is None and right_mean is None:
        return None
    if left_mean is None:
        return "right"
    if right_mean is None:
        return "left"
    return "left" if left_mean < right_mean else "right"
