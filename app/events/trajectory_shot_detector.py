"""
Ball-trajectory-primary shot-attempt detector -- SHADOW-ONLY prototype,
Architecture C (migration-plan follow-up to release_event_detector.py and
episode_release_detector.py).

NOT wired into production. Independent of both prior shadow experiments:
does NOT use the CONTROLLED/TRANSITION/possession-episode state model at
all. Motivated by directly reading a reference project's actual code
(github.com/aarnavshah12/shot-tracker, engine/state_machine.py /
engine/engine.py) rather than its README: that project never tries to
classify "is the ball controlled" precisely. Its release-arm gate is a
cheap, mostly pose-independent velocity threshold that is EXPECTED to fire
on things that aren't real shots (a documented, accepted residual class);
a false arm is then thrown away downstream, by checking whether the ball's
own subsequent flight actually behaves like a shot, never by refining the
upstream gate. Two independent, carefully-tested attempts in this codebase
to make the upstream gate itself precise (TRANSITION, then a temporal
possession episode) each fixed one failure class and introduced a
comparably-sized new one -- see the migration reports -- which is the
direct motivation for trying this instead of a third refinement pass.

Two-stage design:

1. ARM (the main scan loop in `detect_shot_attempts`): a short streak
   (`consecutive_frames`) of ball
   frames with qualifying upward velocity. Mirrors the reference project's
   actual split: a STRONG frame (vvel <= -strong_upward_velocity_norm)
   qualifies unconditionally UNLESS pose confidently says the ball is
   still separated=False from a wrist, in which case it is vetoed for up
   to `veto_override_frames` consecutive frames (bounded, same constant
   release_event_detector.py already uses) before overriding through
   anyway -- pose can only ever DELAY a strong arm, never block or require
   it. A SOFT frame (vvel <= -soft_upward_velocity_norm, separated is True,
   above both wrists) requires pose and exists only to catch slower
   floaters a hand-driven dribble bounce is unlikely to produce. This
   reuses release_event_detector.py's geometry primitives
   (_is_separated, _above_both_wrists, _two_sided_consistency_filter)
   verbatim -- only the ascent-qualification POLICY differs from
   _evaluate_ascent, specifically so that the strong path no longer
   requires separated is True (release_event_detector.py's does, which is
   exactly the "pose required for a strong arm" property this
   architecture is deliberately dropping).

2. CONFIRM (`_confirm_flight`): once armed, the SAME ball-position stream
   is followed forward -- no wrist/pose/hoop involvement at all -- until it
   stops rising (the apex, found by simple monotonicity, no threshold
   needed) and is then observed descending for at least one further step.
   The candidate is confirmed only if the rise phase lasted at least
   2 * consecutive_frames total steps AND a descent step was actually
   observed; otherwise it is discarded as an unconfirmed arm (the
   downstream-evidence mechanism that replaces upstream possession
   classification). No hoop location is used anywhere in this module, so
   an airball that never approaches a rim is confirmed exactly like a
   made shot -- outcome is not this module's job.

Known, deliberately-accepted limitation: requiring an OBSERVED descent
step means a genuine shot whose ball leaves the tracked frame at or near
its apex (common when a camera doesn't capture the full arc above the rim)
will be discarded as unconfirmed. This is a real, expected failure
mechanism on some footage, not a bug -- see the evaluation report for
whether/how often it actually occurs on the three real videos.

No hoop-proximity corroboration is implemented (deliberately, to keep this
the smallest experimental version and because the user's requirement is
that hoop proximity must never be REQUIRED) -- it is a natural, separable
extension, not attempted here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.config import CONFIG
from app.events.release_event_detector import (
    _above_both_wrists,
    _is_separated,
    _two_sided_consistency_filter,
)
from app.events.shot_state_machine import FrameSignals

Pos = Tuple[float, float, float]  # (x, y, timestamp_sec)


@dataclass
class TrajectoryShotCandidate:
    arm_frame: int
    arm_timestamp_sec: float
    arm_path: str  # "strong" | "strong_veto_override" | "soft"
    confirmed: bool
    discard_reason: Optional[str] = None
    apex_frame: Optional[int] = None
    apex_timestamp_sec: Optional[float] = None
    rise_steps: int = 0
    height_gained_norm: Optional[float] = None
    descent_confirmed_frame: Optional[int] = None
    evidence: dict = field(default_factory=dict)


def _evaluate_arm_frame(vvel: float, separated: Optional[bool], above_both: Optional[bool],
                          veto_streak: int, override_active: bool, cfg
                          ) -> Tuple[bool, Optional[str], int]:
    """(qualifies, path, new_veto_streak). Strong path never requires
    pose -- separated is None (no wrist tracked) qualifies immediately,
    same as separated is True. Only a confident separated is False delays
    it, bounded by veto_override_frames. Once the override has fired once
    for the in-progress streak (``override_active``), continuation no
    longer re-checks separation at all -- a wrist keypoint confidently
    (and wrongly) glued to the ball can't re-arm the veto one frame after
    escaping it, which would otherwise make the override streak
    unfinishable whenever the glue condition persists (exactly the
    real-world case the override exists to handle)."""
    if override_active:
        return (vvel <= -cfg.strong_upward_velocity_norm), "strong_veto_override", veto_streak
    if vvel <= -cfg.strong_upward_velocity_norm:
        if separated is False:
            veto_streak += 1
            if veto_streak >= cfg.veto_override_frames:
                return True, "strong_veto_override", 0
            return False, None, veto_streak
        return True, "strong", 0
    if (separated is True and above_both is True and vvel <= -cfg.soft_upward_velocity_norm):
        return True, "soft", 0
    return False, None, 0


def _confirm_flight(ordered_trusted_fi: List[int], trusted: Dict[int, Pos],
                      start_idx: int, arm_pos: Pos, last_streak_fi: int, cfg
                      ) -> Tuple[TrajectoryShotCandidate, int]:
    """Follows the ball position stream forward from start_idx (the index
    of the first frame AFTER the arm streak's last frame) with no
    wrist/hoop involvement, looking only at height over time. ``arm_pos``
    (the streak's first, lowest-so-far frame) is kept only for the
    height-gained report; the apex search itself must track from
    ``last_streak_fi`` (the streak's last, highest-so-far frame) --
    comparing against the streak's START would let a point that has
    already turned around, but is still above the arm frame, be
    misread as continued ascent. Returns the candidate and the index to
    resume the outer scan from."""
    rise_steps = cfg.consecutive_frames  # the arm streak itself was already rising
    apex_fi = last_streak_fi
    apex_pos = trusted[apex_fi]
    idx = start_idx
    n = len(ordered_trusted_fi)
    while idx < n:
        fi = ordered_trusted_fi[idx]
        pos = trusted[fi]
        prev_pos = trusted[ordered_trusted_fi[idx - 1]]
        gap = pos[2] - prev_pos[2]
        if not (1e-6 < gap <= cfg.max_gap_seconds_within_streak):
            break  # trust chain broken -- apex is whatever we've seen so far
        if pos[1] < apex_pos[1]:
            apex_fi, apex_pos = fi, pos
            rise_steps += 1
            idx += 1
            continue
        break  # this step shows the ball at/below the apex height: rise phase over

    descent_frame: Optional[int] = None
    if idx < n:
        fi = ordered_trusted_fi[idx]
        pos = trusted[fi]
        gap = pos[2] - apex_pos[2]
        if (1e-6 < gap <= cfg.max_gap_seconds_within_streak) and pos[1] > apex_pos[1]:
            descent_frame = fi

    confirmed = rise_steps >= 2 * cfg.consecutive_frames and descent_frame is not None
    reason = None
    if not confirmed:
        if rise_steps < 2 * cfg.consecutive_frames:
            reason = "rise_phase_too_short"
        else:
            reason = "no_descent_observed"

    candidate = TrajectoryShotCandidate(
        arm_frame=0, arm_timestamp_sec=0.0, arm_path="",  # filled in by caller
        confirmed=confirmed, discard_reason=reason,
        apex_frame=apex_fi, apex_timestamp_sec=apex_pos[2],
        rise_steps=rise_steps, height_gained_norm=None,
        descent_confirmed_frame=descent_frame,
    )
    return candidate, idx


def detect_shot_attempts(frames: List[FrameSignals], torso_scale_px: float,
                           cfg=None) -> List[TrajectoryShotCandidate]:
    """
    Scans the full frame sequence and returns every ARM candidate (both
    confirmed shot attempts and discarded false arms, tagged via
    `confirmed`/`discard_reason`) -- callers wanting only real shots should
    filter to `confirmed is True`. Uses no hoop location and no possession/
    CONTROLLED/episode state at all.
    """
    cfg = cfg or CONFIG.release_event
    trusted = _two_sided_consistency_filter(frames)
    ordered_trusted_fi = sorted(trusted.keys())
    by_frame_index = {f.frame_index: f for f in frames}

    candidates: List[TrajectoryShotCandidate] = []
    streak: List[Tuple[int, str]] = []
    veto_streak = 0
    override_active = False
    idx = 1
    n = len(ordered_trusted_fi)
    while idx < n:
        a_fi, b_fi = ordered_trusted_fi[idx - 1], ordered_trusted_fi[idx]
        a_pos, b_pos = trusted[a_fi], trusted[b_fi]
        f_b = by_frame_index[b_fi]
        gap = b_pos[2] - a_pos[2]

        if not (1e-6 < gap <= cfg.max_gap_seconds_within_streak):
            streak = []
            veto_streak = 0
            override_active = False
            idx += 1
            continue

        vvel = ((b_pos[1] - a_pos[1]) / gap) / torso_scale_px
        ball_xy = (b_pos[0], b_pos[1])
        separated = _is_separated(ball_xy, f_b, cfg.separation_threshold_norm, torso_scale_px)
        above_both = _above_both_wrists(ball_xy, f_b)

        qualifies, path, veto_streak = _evaluate_arm_frame(
            vvel, separated, above_both, veto_streak, override_active, cfg
        )
        if not qualifies:
            streak = []
            override_active = False
            idx += 1
            continue
        if path == "strong_veto_override":
            override_active = True

        streak.append((b_fi, path))
        if len(streak) < cfg.consecutive_frames:
            idx += 1
            continue

        arm_fi, arm_path = streak[0]
        arm_pos = trusted[arm_fi]
        last_streak_fi = streak[-1][0]
        candidate, next_idx = _confirm_flight(ordered_trusted_fi, trusted, idx + 1, arm_pos, last_streak_fi, cfg)
        candidate.arm_frame = arm_fi
        candidate.arm_timestamp_sec = arm_pos[2]
        candidate.arm_path = arm_path
        candidate.height_gained_norm = round(
            (arm_pos[1] - trusted[candidate.apex_frame][1]) / torso_scale_px, 3
        )
        candidates.append(candidate)

        streak = []
        veto_streak = 0
        override_active = False
        idx = max(next_idx, idx + 1)

    return candidates
