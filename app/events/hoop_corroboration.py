"""
Downstream hoop-proximity corroboration for trajectory_shot_detector.py --
SHADOW-ONLY, Experiment 1 of the Architecture C follow-up.

Does NOT change trajectory_shot_detector.py's arm/confirm decision at all
(hoop proximity is explicitly not required, per the architecture rules --
an airball must still confirm on flight shape alone). This module only
TIERS an already-confirmed candidate by whether its tracked flight ever
came within a generous, already-established distance of the hoop
(CONFIG.outcome.wide_zone_frac_of_rim_radius -- the same "wide zone"
outcome_detector.py already uses for its own beside-hoop/approach
evidence, not a new fitted constant), for evaluation purposes: does
tiering by hoop proximity meaningfully separate real shots from the two
false-positive classes found in the hoop-free evaluation (ordinary
dribbles, loose-ball rebounds)?

Re-derives the trusted ball-position stream the same way
trajectory_shot_detector.py does (_two_sided_consistency_filter) rather
than threading extra state through it, so the baseline module stays
completely unmodified and independently revertible.

The tracked span used for the distance check follows the trusted stream
from the arm frame forward -- through the SAME bounded gap tolerance
trajectory_shot_detector.py already uses (max_gap_seconds_within_streak),
not just to trajectory_shot_detector's own descent_confirmed_frame -- that
frame is only the FIRST observed step of the descent leg, one step past
the apex, and a real shot's ball is typically still far above the rim at
that point; stopping there was an early implementation bug (measured on
V2: a visually-confirmed real shot's own tracked flight showed as 19 rim
radii from the hoop under that cutoff, purely because the span ended
before the descent leg had gone anywhere). The follow continues up to
CONFIG.shot.max_flight_duration_frames past the arm frame -- an existing
constant already used elsewhere in this codebase to bound a shot's flight
duration, not a new one introduced for this check.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.config import CONFIG
from app.events.release_event_detector import _two_sided_consistency_filter
from app.events.shot_state_machine import FrameSignals
from app.events.trajectory_shot_detector import TrajectoryShotCandidate
from app.vision.types import HoopLocation


@dataclass
class HoopCorroboration:
    tier: str  # "hoop_corroborated" | "no_hoop_evidence" | "no_hoop_location"
    min_distance_rim_radii: Optional[float] = None


def corroborate(candidate: TrajectoryShotCandidate, frames: List[FrameSignals],
                  hoop: Optional[HoopLocation], cfg=None, shot_cfg=None) -> HoopCorroboration:
    cfg = cfg or CONFIG.outcome
    shot_cfg = shot_cfg or CONFIG.shot
    if hoop is None or hoop.confidence < cfg.min_hoop_confidence_to_attempt or hoop.rim_radius_px <= 0:
        return HoopCorroboration("no_hoop_location")

    trusted = _two_sided_consistency_filter(frames)
    ordered = sorted(fi for fi in trusted if fi >= candidate.arm_frame)
    span = []
    prev_t = None
    frame_limit = candidate.arm_frame + shot_cfg.max_flight_duration_frames
    for fi in ordered:
        if fi > frame_limit:
            break
        pos = trusted[fi]
        if prev_t is not None and not (1e-6 < pos[2] - prev_t <= CONFIG.release_event.max_gap_seconds_within_streak):
            break  # trust chain broken -- the rest is unrelated motion
        span.append(pos)
        prev_t = pos[2]
    if not span:
        return HoopCorroboration("no_hoop_evidence")

    min_dist = min(
        ((x - hoop.rim_center_x) ** 2 + (y - hoop.rim_center_y) ** 2) ** 0.5
        for x, y, _t in span
    ) / hoop.rim_radius_px

    if min_dist <= cfg.wide_zone_frac_of_rim_radius:
        return HoopCorroboration("hoop_corroborated", round(min_dist, 2))
    return HoopCorroboration("no_hoop_evidence", round(min_dist, 2))
