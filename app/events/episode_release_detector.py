"""
Ball-centric release-EVENT detector -- SHADOW-ONLY temporal possession
EPISODE prototype (migration-plan follow-up to release_event_detector.py).

NOT wired into production, and NOT a replacement for
release_event_detector.py's TRANSITION-state baseline -- this is a second,
independent shadow detector evaluating a different architectural
hypothesis: that "is the ball controlled" is better modeled as an INTERVAL
(open -> confirm -> resolve) than as a per-frame or windowed predicate. See
the migration report comparing this against the TRANSITION baseline and the
(reverted, never-shipped) windowed-median patch for the reasoning that
motivated this prototype.

Reuses release_event_detector.py's trust filtering, geometry, and ascent-
qualification primitives UNCHANGED (_two_sided_consistency_filter,
_min_separation_norm, _is_separated, _above_both_wrists, _evaluate_ascent)
-- this module only replaces the CONTROLLED/TRANSITION frame-local
predicate with an explicit episode state machine, using ONLY pre-existing
ReleaseEventConfig constants (separation_threshold_norm,
strong_upward_velocity_norm, soft_upward_velocity_norm, consecutive_frames,
max_gap_seconds_within_streak). No new fitted constants were needed -- see
below for exactly why each state transition needed no new threshold.

State machine (per continuous trusted-observation stream):

  UNCONTROLLED -> APPROACHING: the ball comes within
  separation_threshold_norm of a wrist -- the SAME proximity gate the
  baseline already uses.

  APPROACHING -> POSSESSION: the ball-vs-wrist relative velocity magnitude
  stops decreasing (a discrete local minimum -- the shape of a genuine
  catch), while still within proximity. This is a MONOTONICITY check on
  consecutive relative-velocity samples, not a magnitude threshold -- no
  new constant. Confirmation requires at least two consecutive in-proximity
  trusted pairs (structurally necessary to detect a trend reversal, not a
  tuned window size).

  APPROACHING -> UNCONTROLLED: proximity is lost before a local minimum is
  ever reached -- nothing was confirmed, so there is no provenance to
  protect. This is what rejects the large majority of ordinary dribble
  touches, the same way CONTROLLED's strict predicate did in the baseline.

  POSSESSION -> POSSESSION: persists through ANY amount of in-proximity
  motion, however noisy. This is the entire point of the episode
  reframing: no window, no per-frame velocity-sign check, so it cannot
  suffer either failure mechanism diagnosed against the reverted windowed
  patch (stale pre-control contamination at fresh entry, or a settle run
  longer than a fixed window).

  POSSESSION -> SEPARATED: proximity is lost. The ascent-qualification
  check (_evaluate_ascent, unchanged) is evaluated on this SAME trusted
  pair immediately, exactly as the baseline's CONTROLLED -> SEPARATING
  transition does, so a release whose very first qualifying frame IS the
  separation frame loses no evidence.

  SEPARATED -> RELEASE: ascent qualification continues for
  consecutive_frames consecutive trusted pairs (unchanged streak logic).

  SEPARATED -> APPROACHING ("round trip" / dribble-bounce rejection): the
  ascent streak breaks AND the ball has come back within
  separation_threshold_norm of a wrist -- the signature of a completed
  independent bounce (left, then returned) rather than a shot. Provenance
  is discarded and a fresh APPROACHING interval begins from this same pair
  (equivalent to, but one step faster than, falling through UNCONTROLLED
  and re-entering APPROACHING on the next pair).

  SEPARATED -> UNCONTROLLED: the ascent streak breaks and the ball has NOT
  returned to proximity either -- it is simply drifting away without
  qualifying (a soft toss, a drop) and is not close to anything. No
  provenance survives; a later re-approach must re-confirm POSSESSION from
  scratch.

Known simplification vs. the TRANSITION baseline: this prototype does not
port the baseline's veto/override mechanism (compensating for a
stuck/misassociated wrist keypoint gluing a fast-separating ball to "still
close" for several frames). In the baseline that compensation was needed
because CONTROLLED's exit predicate is strict (proximity AND matching
relative velocity); here, POSSESSION's exit predicate is proximity ONLY, so
a stuck keypoint simply delays the POSSESSION -> SEPARATED transition by
the same number of frames the baseline's override was compensating for,
rather than blocking it -- the streak still starts (via the same immediate
on-transition ascent_ok check) once separation catches up. This can shift
release_frame a few frames later than the baseline on footage that
exercises the override path specifically; none of the three evaluation
videos' current baseline candidates use the "strong_override" path, so this
difference was not observable in this evaluation, but it is a genuine,
untested architectural difference, not a proven equivalence.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from app.config import CONFIG
from app.events.release_event_detector import (
    ReleaseEventCandidate,
    _above_both_wrists,
    _evaluate_ascent,
    _is_separated,
    _min_separation_norm,
    _two_sided_consistency_filter,
    _wrist_xy,
)
from app.events.shot_state_machine import FrameSignals


class _EpisodeState(Enum):
    UNCONTROLLED = "uncontrolled"
    APPROACHING = "approaching"
    POSSESSION = "possession"
    SEPARATED = "separated"


@dataclass
class EpisodeTraceEntry:
    """One state transition, for diagnostic use only -- mirrors
    release_event_detector.StateTraceEntry but carries the extra fields
    this state machine's transitions depend on (proximity, relative
    velocity). Never consumed by the candidate list itself."""
    a_frame: int
    b_frame: int
    state_before: str
    state_after: str
    vvel: Optional[float]
    separated: Optional[bool]
    proximity_ok: Optional[bool]
    rel_vel: Optional[float]


def _relative_velocity_to_nearest_wrist(a_pos: Tuple[float, float, float], b_pos: Tuple[float, float, float],
                                          f_a: FrameSignals, f_b: FrameSignals, torso_scale_px: float
                                          ) -> Optional[float]:
    """abs(ball_vy - wrist_vy) against whichever wrist is nearest at b --
    the same computation release_event_detector._is_controlled_transition
    uses internally, exposed without its final magnitude threshold, since
    this module confirms POSSESSION via monotonicity, not a magnitude
    cutoff."""
    if torso_scale_px <= 0:
        return None
    ball_xy = (b_pos[0], b_pos[1])
    best = _min_separation_norm(ball_xy, f_b, torso_scale_px)
    if best is None:
        return None
    side = best[1]
    w_a = _wrist_xy(f_a, side)
    w_b = _wrist_xy(f_b, side)
    if w_a is None or w_b is None:
        return None
    dt = b_pos[2] - a_pos[2]
    if dt <= 1e-6:
        return None
    wrist_vy = (w_b[1] - w_a[1]) / dt / torso_scale_px
    ball_vy = (b_pos[1] - a_pos[1]) / dt / torso_scale_px
    return abs(ball_vy - wrist_vy)


def detect_release_events_episode(frames: List[FrameSignals], torso_scale_px: float,
                                    cfg=None, trace: Optional[List[EpisodeTraceEntry]] = None
                                    ) -> List[ReleaseEventCandidate]:
    """
    Shadow-only prototype: the same trusted-pair scan as
    release_event_detector.detect_release_events, but gates release
    candidates on an explicit possession EPISODE (open -> confirm ->
    resolve) instead of a per-frame/windowed CONTROLLED predicate. See the
    module docstring for the full state machine and its reasoning.
    """
    cfg = cfg or CONFIG.release_event
    trusted = _two_sided_consistency_filter(frames)
    ordered_trusted_fi = sorted(trusted.keys())
    by_frame_index = {f.frame_index: f for f in frames}

    events: List[ReleaseEventCandidate] = []
    state = _EpisodeState.UNCONTROLLED
    streak: List[Tuple[FrameSignals, str, Optional[float]]] = []
    prev_rel_vel: Optional[float] = None

    for a_fi, b_fi in zip(ordered_trusted_fi, ordered_trusted_fi[1:]):
        a_pos, b_pos = trusted[a_fi], trusted[b_fi]
        f_a, f_b = by_frame_index[a_fi], by_frame_index[b_fi]
        gap_seconds = b_pos[2] - a_pos[2]
        state_before = state

        if not (1e-6 < gap_seconds <= cfg.max_gap_seconds_within_streak):
            state = _EpisodeState.UNCONTROLLED
            streak = []
            prev_rel_vel = None
            if trace is not None:
                trace.append(EpisodeTraceEntry(a_fi, b_fi, state_before.value, state.value, None, None, None, None))
            continue

        vvel = ((b_pos[1] - a_pos[1]) / gap_seconds) / torso_scale_px
        ball_xy = (b_pos[0], b_pos[1])
        separated = _is_separated(ball_xy, f_b, cfg.separation_threshold_norm, torso_scale_px)
        separation_norm = _min_separation_norm(ball_xy, f_b, torso_scale_px)
        separation_norm = separation_norm[0] if separation_norm is not None else None
        proximity_ok = None if separated is None else (not separated)
        above_both = _above_both_wrists(ball_xy, f_b)
        rel_vel = _relative_velocity_to_nearest_wrist(a_pos, b_pos, f_a, f_b, torso_scale_px)
        ascent_ok, ascent_path = _evaluate_ascent(vvel, separated, above_both, cfg)

        if state == _EpisodeState.UNCONTROLLED:
            if proximity_ok:
                state = _EpisodeState.APPROACHING
                prev_rel_vel = rel_vel
            else:
                prev_rel_vel = None
            if trace is not None:
                trace.append(EpisodeTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, proximity_ok, rel_vel))
            continue

        if state == _EpisodeState.APPROACHING:
            if not proximity_ok:
                state = _EpisodeState.UNCONTROLLED
                prev_rel_vel = None
            elif rel_vel is not None and prev_rel_vel is not None and rel_vel >= prev_rel_vel:
                # Relative velocity stopped decreasing -- a local minimum:
                # the shape of a genuine catch has been observed.
                state = _EpisodeState.POSSESSION
                prev_rel_vel = None
            else:
                prev_rel_vel = rel_vel
            if trace is not None:
                trace.append(EpisodeTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, proximity_ok, rel_vel))
            continue

        if state == _EpisodeState.POSSESSION:
            if proximity_ok:
                if trace is not None:
                    trace.append(EpisodeTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, proximity_ok, rel_vel))
                continue  # settle noise, however large -- no window, no lag
            # Proximity broken -- possession is ending. Check this SAME
            # pair for an immediate qualifying ascent, same as the
            # baseline's CONTROLLED -> SEPARATING transition, so a release
            # whose very first qualifying frame IS the separation frame
            # loses no evidence.
            state = _EpisodeState.SEPARATED
            streak = [(f_b, ascent_path, separation_norm)] if ascent_ok else []
            if trace is not None:
                trace.append(EpisodeTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, proximity_ok, rel_vel))
            continue

        # state == SEPARATED
        if ascent_ok:
            streak.append((f_b, ascent_path, separation_norm))
            if len(streak) >= cfg.consecutive_frames:
                release_f, release_path, release_sep = streak[0]
                base_confidence = {"strong": 0.75, "soft": 0.6}[release_path]
                bonus = 0.05 * (len(streak) - cfg.consecutive_frames)
                confidence = min(1.0, base_confidence + bonus)
                events.append(ReleaseEventCandidate(
                    release_frame=release_f.frame_index,
                    release_timestamp_sec=release_f.timestamp_sec,
                    confidence=round(confidence, 3),
                    path=release_path,
                    evidence={
                        "consecutive_qualifying_frames": len(streak),
                        "separation_norm_at_release": round(release_sep, 3) if release_sep is not None else None,
                    },
                ))
                streak = []
                state = _EpisodeState.UNCONTROLLED
            if trace is not None:
                trace.append(EpisodeTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, proximity_ok, rel_vel))
            continue

        # Ascent broke.
        streak = []
        if proximity_ok:
            # Round trip: the ball left and came back without ever
            # qualifying as a launch -- a completed independent bounce,
            # not a shot. Provenance is discarded; a fresh approach begins
            # from this same pair.
            state = _EpisodeState.APPROACHING
            prev_rel_vel = rel_vel
        else:
            state = _EpisodeState.UNCONTROLLED
            prev_rel_vel = None
        if trace is not None:
            trace.append(EpisodeTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, proximity_ok, rel_vel))

    return events
