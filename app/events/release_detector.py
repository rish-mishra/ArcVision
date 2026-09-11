"""
Refines the exact release moment within a shot window already bounded by
the shot state machine. The state machine gives a coarse candidate frame
(first sustained ball-hand separation); this module tightens that estimate
using ball-hand distance trend, upward velocity, and elbow extension, and
reports a confidence plus a bounded uncertainty window rather than
pretending a single frame is certain when the underlying signal is noisy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.config import CONFIG
from app.events.shot_state_machine import FrameSignals, ShotWindow


@dataclass
class ReleaseEstimate:
    release_frame: int
    release_timestamp_sec: float
    window_start_frame: int
    window_end_frame: int
    confidence: float
    elbow_angle_at_release_deg: Optional[float] = None
    basis: str = ""


def estimate_release(shot: ShotWindow, frames: List[FrameSignals],
                      elbow_angles: Optional[dict] = None, cfg=None) -> Optional[ReleaseEstimate]:
    """
    frames: the full per-frame signal list (same one given to the state
    machine); elbow_angles: optional {frame_index: angle_deg} for the
    shooting arm, used only to refine confidence, not required.
    """
    cfg = cfg or CONFIG.release
    if shot.release_candidate_frame is None:
        return None

    by_frame = {f.frame_index: f for f in frames}
    candidate = shot.release_candidate_frame
    lo = max(shot.start_frame, candidate - cfg.search_window_frames)
    hi = min(shot.end_frame, candidate + cfg.search_window_frames)
    window_frames = [by_frame[i] for i in range(lo, hi + 1) if i in by_frame]

    if not window_frames:
        return None

    # Find the first frame in the window where separation clearly and
    # persistently exceeds threshold (a stricter, more precise re-check
    # than the state machine's coarser trigger).
    best_frame = candidate
    found_precise = False
    for f in window_frames:
        if (f.ball_hand_dist_norm is not None
                and f.ball_hand_dist_norm >= cfg.hand_ball_distance_norm_threshold
                and f.ball_vertical_velocity_norm is not None
                and f.ball_vertical_velocity_norm <= -cfg.min_upward_velocity_norm):
            best_frame = f.frame_index
            found_precise = True
            break

    signal = by_frame.get(best_frame)
    basis_parts = []
    score = 0.4  # baseline: we at least have the state machine's candidate

    if found_precise:
        score += 0.3
        basis_parts.append("hand_ball_separation")
    if (signal and signal.ball_vertical_velocity_norm is not None
            and signal.ball_vertical_velocity_norm <= -cfg.min_upward_velocity_norm):
        score += 0.15
        basis_parts.append("upward_velocity")

    elbow_at_release = None
    if elbow_angles:
        elbow_at_release = elbow_angles.get(best_frame)
        if elbow_at_release is not None and elbow_at_release >= 140:
            score += 0.15
            basis_parts.append("elbow_extension")

    score = min(1.0, score)
    win_lo = max(shot.start_frame, best_frame - cfg.confidence_window_frames)
    win_hi = min(shot.end_frame, best_frame + cfg.confidence_window_frames)

    return ReleaseEstimate(
        release_frame=best_frame,
        release_timestamp_sec=signal.timestamp_sec if signal else by_frame[candidate].timestamp_sec,
        window_start_frame=win_lo,
        window_end_frame=win_hi,
        confidence=round(score, 3),
        elbow_angle_at_release_deg=elbow_at_release,
        basis=",".join(basis_parts) if basis_parts else "state_machine_candidate_only",
    )
