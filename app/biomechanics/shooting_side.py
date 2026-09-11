"""Determines which arm is the shooting arm for a given shot attempt."""
from __future__ import annotations

from typing import List, Optional

from app.biomechanics.geometry import distance
from app.vision.types import PoseFrame


def determine_shooting_side(pose_frames: List[PoseFrame], ball_positions: dict,
                             start_frame: int, end_frame: int) -> Optional[str]:
    """
    ball_positions: {frame_index: (x, y)} for frames with a reliable ball
    observation. Compares mean wrist-ball distance for each arm across the
    shot window; the closer wrist, on average, is the shooting hand.
    """
    left_dists, right_dists = [], []
    for pf in pose_frames:
        if not (start_frame <= pf.frame_index <= end_frame):
            continue
        ball = ball_positions.get(pf.frame_index)
        if ball is None:
            continue
        lw = pf.landmark("left_wrist")
        rw = pf.landmark("right_wrist")
        if lw and lw.visibility >= 0.4:
            left_dists.append(distance((lw.x, lw.y), ball))
        if rw and rw.visibility >= 0.4:
            right_dists.append(distance((rw.x, rw.y), ball))

    if not left_dists and not right_dists:
        return None
    left_mean = sum(left_dists) / len(left_dists) if left_dists else float("inf")
    right_mean = sum(right_dists) / len(right_dists) if right_dists else float("inf")
    if left_mean == float("inf") and right_mean == float("inf"):
        return None
    return "left" if left_mean < right_mean else "right"
