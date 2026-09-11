"""
Downstream, bounded pose-at-arm corroboration for
trajectory_shot_detector.py -- SHADOW-ONLY, Architecture C Experiment 2.

Not a possession/CONTROLLED/episode state machine: no persistence across
frames, no episode, nothing carried forward. It asks exactly one bounded
question about an already-confirmed candidate: was ANY wrist within
CONFIG.release_event.separation_threshold_norm of the ball at any trusted
frame in the consecutive_frames immediately before the arm streak began?
Both constants are reused verbatim from release_event_detector.py's
existing config -- separation_threshold_norm is its own "in/near the hand"
proximity bound, consecutive_frames is its own streak-length unit -- no
new fitted constant was introduced for this check.

Motivation: hoop corroboration (Experiment 1) cut confirmed false
positives substantially but could not reliably separate a genuinely
unattended loose ball bouncing near the rim (still hoop-corroborated,
since the bounce itself is near the hoop) from a real player-launched
shot. The two differ in exactly one way a hoop-only check can't see:
whether a person's hand was anywhere near the ball right before it
started rising. This does not require classifying "control" over an
interval (that's what TRANSITION and the episode prototype did, and both
struggled) -- it only asks whether a hand was nearby at all, once, at a
single well-defined moment, which is a much weaker and cheaper claim.

Never required: a candidate with zero wrist data over the lookback window
reports "no_pose_data", treated as neutral by the caller's combination
policy, never as disqualifying -- pose remains auxiliary evidence, per
the architecture rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.config import CONFIG
from app.events.release_event_detector import _min_separation_norm, _two_sided_consistency_filter
from app.events.shot_state_machine import FrameSignals
from app.events.trajectory_shot_detector import TrajectoryShotCandidate


@dataclass
class PoseAtArmCorroboration:
    tier: str  # "pose_corroborated" | "no_pose_evidence" | "no_pose_data"
    min_distance_norm: Optional[float] = None


def corroborate(candidate: TrajectoryShotCandidate, frames: List[FrameSignals],
                  torso_scale_px: float, cfg=None) -> PoseAtArmCorroboration:
    cfg = cfg or CONFIG.release_event
    if torso_scale_px <= 0:
        return PoseAtArmCorroboration("no_pose_data")

    trusted = _two_sided_consistency_filter(frames)
    by_frame_index = {f.frame_index: f for f in frames}
    ordered = sorted(fi for fi in trusted if fi <= candidate.arm_frame)
    window = ordered[-cfg.consecutive_frames:] if ordered else []

    best: Optional[float] = None
    any_pose_data = False
    for fi in window:
        x, y, _t = trusted[fi]
        f = by_frame_index.get(fi)
        if f is None:
            continue
        result = _min_separation_norm((x, y), f, torso_scale_px)
        if result is None:
            continue
        any_pose_data = True
        dist, _side = result
        if best is None or dist < best:
            best = dist

    if not any_pose_data:
        return PoseAtArmCorroboration("no_pose_data")
    if best is not None and best <= cfg.separation_threshold_norm:
        return PoseAtArmCorroboration("pose_corroborated", round(best, 3))
    return PoseAtArmCorroboration("no_pose_evidence", round(best, 3) if best is not None else None)
