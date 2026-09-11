"""
Ball-centric release-EVENT detector -- migration-plan Phase 1.

NOT wired into production. This is an isolated, independently-testable
module evaluated in SHADOW MODE against the existing shot_state_machine.py:
it consumes the same FrameSignals sequence the state machine does and
proposes its own, independent release candidates, so its output can be
compared against the current pipeline's without changing any production
behavior.

Architectural motivation (see the migration-plan diagnostic reports for
the full history): the existing state machine gates a shot's LOAD phase on
POSE FIRST (ball-hand proximity + a knee-flexion dip), and only confirms
with ball velocity -- which let a walking gait's incidental knee dip, or a
single frame of dribble-bounce velocity, fabricate a spurious shot record.
This module inverts that emphasis: ball vertical velocity is the PRIMARY
signal, and wrist-ball relationship is corroborating evidence, evaluated
through three structural findings from directly comparing genuine releases
against dribbles, rebounds, and tracking artifacts on real footage:

1. Trusted-observation continuity (`_two_sided_consistency_filter`): a
   DETECTED point that deviates from the local trend on BOTH the nearest
   real detection before and after it is a spurious detection, not merely
   a low-confidence one -- continuity, never a confidence cutoff.

2. Bounded-gap streaks: "consecutive evidence" is defined over consecutive
   TRUSTED observations tolerant of a short, bounded temporal gap between
   them (a correctly-rejected phantom-interpolated frame must not
   fragment two real detections a couple of frames apart), not consecutive
   raw frame indices.

3. UNCONTROLLED -> CONTROLLED -> TRANSITION -> SEPARATING -> RELEASE as an
   explicit, continuous episode, not a historical lookback. An earlier
   diagnostic pass allowed a RELEASE to arm if the ball had been
   "controlled" (near a wrist, low relative velocity) ANYWHERE in the last
   1.5s -- forensically auditing every remaining shadow-mode candidate on
   three real videos found this was THE dominant false-positive mechanism:
   a repeated dribble brings the ball briefly close to a wrist once per
   bounce, and that one close approach was authorizing a LATER, unrelated
   bounce's ascent, because nothing required the two to be part of the
   same continuous episode. A first version of the state model (CONTROLLED
   -> SEPARATING directly, no TRANSITION) fixed that, but introduced a
   worse regression: real continuous shooting motion routinely passes
   through one or two frames where the strict CONTROLLED predicate (tight
   proximity AND low relative velocity) is momentarily false -- the wrist
   is following through, not perfectly matching the ball's now-increasing
   speed -- before the ascent becomes strong enough to register as
   SEPARATING. Dropping straight to UNCONTROLLED on that frame discarded
   genuine provenance the large majority of the time, since UNCONTROLLED
   has no path back to SEPARATING without re-satisfying the strict
   CONTROLLED bar again, which a fast-departing ball essentially never
   does. TRANSITION exists to hold that provenance while evidence
   develops, without reopening the dribble class it took CONTROLLED's
   continuity requirement to close: the CONTROLLED/TRANSITION -> TRANSITION
   vs. -> UNCONTROLLED choice is decided by the sign of vvel, not a new
   fitted threshold -- a genuine developing launch's ambiguous frames stay
   net-upward or flat (vvel <= 0) the whole way through, while a dribble's
   control-to-fall moment is an unambiguous, immediate net-downward motion
   (vvel > 0). A stuck/misassociated wrist keypoint gluing a fast,
   genuinely-separating ball to "still close" is handled inside TRANSITION
   the same way the original veto override was: bounded, and only escapes
   into SEPARATING after `veto_override_frames` consecutive
   strong-but-unseparated observations.

A windowed (median-of-recent) refinement to the CONTROLLED/TRANSITION exit
decision was attempted and REVERTED after real-video evaluation: a rolling
median over the last `consecutive_frames` raw velocities fixed the targeted
single-frame-wobble misses but introduced a worse regression -- the window
lags at the moment control is FRESHLY established (it stays contaminated by
the ball's own pre-control settling-into-the-catch motion, which is
legitimate signal, not noise, for several frames), so genuine episodes that
TRANSITION alone already handled correctly were newly broken. See the
migration report for the full trace-level diagnosis. The remaining-recall
investigation (temporal possession episode vs. windowed predicate) is
ongoing; this module currently reflects TRANSITION-only (per-frame
CONTROLLED predicate), not the windowed variant.

Unlike the reference project this was modeled on, thresholds stay in this
pipeline's existing NORMALIZED (torso-length-relative) unit system -- see
ReleaseEventConfig's docstring in app/config.py.

This module does NOT yet implement the full decoupled architecture
(migration-plan Phase 4), and does NOT yet address the separately-diagnosed
duplicate/spillover class (a single genuine release's own continuing
flight producing more than one candidate) -- see the migration report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from app.config import CONFIG
from app.events.shot_state_machine import FrameSignals

_DETECTED_SOURCE_VALUE = "detected"
_INTERPOLATED_SOURCE_VALUE = "interpolated"
_WRIST_SIDES = ("left", "right")


class _ControlState(Enum):
    UNCONTROLLED = "uncontrolled"
    CONTROLLED = "controlled"
    TRANSITION = "transition"
    SEPARATING = "separating"


@dataclass
class ReleaseEventCandidate:
    release_frame: int
    release_timestamp_sec: float
    confidence: float
    path: str  # "strong" | "strong_override" | "soft"
    evidence: dict = field(default_factory=dict)


def _source_value(f: FrameSignals) -> Optional[str]:
    return getattr(f.ball_source, "value", f.ball_source)


def _wrist_xy(f: FrameSignals, side: str) -> Optional[Tuple[float, float]]:
    return f.left_wrist_xy if side == "left" else f.right_wrist_xy


# ---------------------------------------------------------------- trust

def _consistent(cur_xy: Tuple[float, float], prev: Tuple[float, float, float],
                  nxt: Tuple[float, float, float], cur_t: float,
                  span_frac: float, min_px: float) -> bool:
    """True if cur_xy is close to the straight-line interpolation between
    prev and nxt ((x, y, t) tuples) at cur_t, relative to the segment's own
    length -- the shared two-sided consistency test used for both DETECTED
    and INTERPOLATED points below."""
    px, py, pt = prev
    nx, ny, nt = nxt
    dt_total = nt - pt
    if dt_total <= 1e-6:
        return True
    t_frac = (cur_t - pt) / dt_total
    pred_x = px + t_frac * (nx - px)
    pred_y = py + t_frac * (ny - py)
    deviation = ((cur_xy[0] - pred_x) ** 2 + (cur_xy[1] - pred_y) ** 2) ** 0.5
    segment_span = ((nx - px) ** 2 + (ny - py) ** 2) ** 0.5
    tolerance = max(segment_span * span_frac, min_px)
    return deviation <= tolerance


def _two_sided_consistency_filter(frames: List[FrameSignals], span_frac: float = 0.6,
                                     min_px: float = 15.0) -> Dict[int, Tuple[float, float, float]]:
    """{frame_index: (x, y, timestamp_sec)} for frames whose ball position
    is trustworthy for evidence computation.

    Pass 1: DETECTED points are checked against the two nearest OTHER
    DETECTED points (previous and next in the detected-only subsequence).
    A DETECTED point that deviates from that local line is a spurious
    detection. The first and last DETECTED point in the whole sequence
    have no two-sided anchor and are trusted by default.

    Pass 2: INTERPOLATED points are checked the same way, anchored to the
    CLEANED detected set from pass 1.

    Never confidence-based."""
    detected = [f for f in frames if f.ball_x is not None and f.ball_y is not None
                and _source_value(f) == _DETECTED_SOURCE_VALUE]
    trusted: Dict[int, Tuple[float, float, float]] = {}
    clean_detected_ordered: List[FrameSignals] = []
    for i, f in enumerate(detected):
        if i == 0 or i == len(detected) - 1:
            keep = True
        else:
            prev, nxt = detected[i - 1], detected[i + 1]
            keep = _consistent((f.ball_x, f.ball_y),
                                 (prev.ball_x, prev.ball_y, prev.timestamp_sec),
                                 (nxt.ball_x, nxt.ball_y, nxt.timestamp_sec),
                                 f.timestamp_sec, span_frac, min_px)
        if keep:
            trusted[f.frame_index] = (f.ball_x, f.ball_y, f.timestamp_sec)
            clean_detected_ordered.append(f)

    if len(clean_detected_ordered) < 2:
        return trusted

    interpolated = [f for f in frames if f.ball_x is not None and f.ball_y is not None
                     and _source_value(f) == _INTERPOLATED_SOURCE_VALUE]
    for f in interpolated:
        before = None
        after = None
        for anchor in clean_detected_ordered:
            if anchor.frame_index < f.frame_index:
                before = anchor
            elif anchor.frame_index > f.frame_index:
                after = anchor
                break
        if before is None or after is None:
            continue
        if _consistent((f.ball_x, f.ball_y),
                        (before.ball_x, before.ball_y, before.timestamp_sec),
                        (after.ball_x, after.ball_y, after.timestamp_sec),
                        f.timestamp_sec, span_frac, min_px):
            trusted[f.frame_index] = (f.ball_x, f.ball_y, f.timestamp_sec)
    return trusted


# ------------------------------------------------------------- geometry

def _min_separation_norm(ball_xy: Tuple[float, float], f: FrameSignals,
                           torso_scale_px: float) -> Optional[Tuple[float, str]]:
    """(distance_norm, side) for the nearest tracked wrist, or None."""
    best = None
    for side in _WRIST_SIDES:
        wxy = _wrist_xy(f, side)
        if wxy is None or torso_scale_px <= 0:
            continue
        d = ((ball_xy[0] - wxy[0]) ** 2 + (ball_xy[1] - wxy[1]) ** 2) ** 0.5 / torso_scale_px
        if best is None or d < best[0]:
            best = (d, side)
    return best


def _is_separated(ball_xy: Tuple[float, float], f: FrameSignals, threshold_norm: float,
                    torso_scale_px: float) -> Optional[bool]:
    best = _min_separation_norm(ball_xy, f, torso_scale_px)
    if best is None:
        return None
    return best[0] > threshold_norm


def _above_both_wrists(ball_xy: Tuple[float, float], f: FrameSignals) -> Optional[bool]:
    if f.left_wrist_xy is None or f.right_wrist_xy is None:
        return None
    return ball_xy[1] < min(f.left_wrist_xy[1], f.right_wrist_xy[1])


# ------------------------------------------------------ controlled state

def _is_controlled_transition(a_pos: Tuple[float, float, float], b_pos: Tuple[float, float, float],
                                 f_b: FrameSignals, f_a: FrameSignals, torso_scale_px: float, cfg) -> bool:
    """True if, between trusted ball positions a -> b, the ball stayed
    within cfg.separation_threshold_norm of the SAME nearest wrist AND
    that wrist's own vertical velocity agreed with the ball's (relative
    speed under controlled_max_relative_velocity_norm) -- "the ball is
    being carried by this hand," not merely nearby. Uses the same (a, b)
    trusted pair -- and therefore the same bounded gap tolerance -- as the
    ascent-qualification check, so a brief validated tracking gap during
    genuine control cannot falsely terminate the episode."""
    if torso_scale_px <= 0:
        return False
    ball_xy = (b_pos[0], b_pos[1])
    best = _min_separation_norm(ball_xy, f_b, torso_scale_px)
    if best is None or best[0] > cfg.separation_threshold_norm:
        return False
    side = best[1]
    w_b = _wrist_xy(f_b, side)
    w_a = _wrist_xy(f_a, side)
    if w_a is None or w_b is None:
        return False
    dt = b_pos[2] - a_pos[2]
    if dt <= 1e-6:
        return False
    wrist_vy = (w_b[1] - w_a[1]) / dt / torso_scale_px
    ball_vy = (b_pos[1] - a_pos[1]) / dt / torso_scale_px
    return abs(ball_vy - wrist_vy) <= cfg.controlled_max_relative_velocity_norm


def _evaluate_ascent(vvel: float, separated: Optional[bool], above_both: Optional[bool], cfg
                       ) -> Tuple[bool, Optional[str]]:
    """Ascent qualification alone (no state/veto bookkeeping)."""
    if vvel <= -cfg.strong_upward_velocity_norm:
        if separated is True:
            return True, "strong"
        return False, None
    if (separated is True and above_both is True and vvel <= -cfg.soft_upward_velocity_norm):
        return True, "soft"
    return False, None


def _is_veto_pending(vvel: float, separated: Optional[bool], cfg) -> bool:
    """A strong-velocity ascent candidate whose separation check says
    'still close' -- either a genuine pump fake, or a stuck/misassociated
    wrist keypoint riding a real launch. Tracked separately so it can
    escape into SEPARATING after veto_override_frames, without ever
    letting a merely-close-but-otherwise-idle ball qualify."""
    return vvel <= -cfg.strong_upward_velocity_norm and separated is False


# ------------------------------------------------------------------ main

@dataclass
class StateTraceEntry:
    """One state transition, for diagnostic use only (audits how long the
    detector spends in each state, especially TRANSITION) -- never
    consumed by production or by the candidate list itself."""
    a_frame: int
    b_frame: int
    state_before: str
    state_after: str
    vvel: Optional[float]
    separated: Optional[bool]
    is_ctrl: bool


def detect_release_events(frames: List[FrameSignals], torso_scale_px: float,
                            cfg=None, trace: Optional[List[StateTraceEntry]] = None
                            ) -> List[ReleaseEventCandidate]:
    """
    Scans the full frame sequence and returns every independently-detected
    release candidate, using an explicit UNCONTROLLED -> CONTROLLED ->
    TRANSITION -> SEPARATING state per continuous trusted-observation
    episode. Does not know about shot windows, outcomes, or the existing
    state machine.

    `trace`, if given a list, is appended to with one StateTraceEntry per
    trusted-pair transition -- purely diagnostic (see
    scripts/audit_transition_duration.py), never affects the returned
    candidates.
    """
    cfg = cfg or CONFIG.release_event
    trusted = _two_sided_consistency_filter(frames)
    ordered_trusted_fi = sorted(trusted.keys())
    by_frame_index = {f.frame_index: f for f in frames}

    events: List[ReleaseEventCandidate] = []
    state = _ControlState.UNCONTROLLED
    streak: List["tuple[FrameSignals, str, Optional[float]]"] = []
    veto_streak = 0

    for a_fi, b_fi in zip(ordered_trusted_fi, ordered_trusted_fi[1:]):
        a_pos, b_pos = trusted[a_fi], trusted[b_fi]
        f_a, f_b = by_frame_index[a_fi], by_frame_index[b_fi]
        gap_seconds = b_pos[2] - a_pos[2]
        state_before = state

        if not (1e-6 < gap_seconds <= cfg.max_gap_seconds_within_streak):
            # Gap too large (or degenerate) to trust as continuous evidence
            # of anything -- neither a control episode nor an ascent
            # streak may cross it.
            state = _ControlState.UNCONTROLLED
            streak = []
            if trace is not None:
                trace.append(StateTraceEntry(a_fi, b_fi, state_before.value, state.value, None, None, False))
            veto_streak = 0
            continue

        vvel = ((b_pos[1] - a_pos[1]) / gap_seconds) / torso_scale_px
        ball_xy = (b_pos[0], b_pos[1])
        separated = _is_separated(ball_xy, f_b, cfg.separation_threshold_norm, torso_scale_px)
        separation_norm = _min_separation_norm(ball_xy, f_b, torso_scale_px)
        separation_norm = separation_norm[0] if separation_norm is not None else None
        above_both = _above_both_wrists(ball_xy, f_b)
        is_ctrl = _is_controlled_transition(a_pos, b_pos, f_b, f_a, torso_scale_px, cfg)
        ascent_ok, ascent_path = _evaluate_ascent(vvel, separated, above_both, cfg)

        if state == _ControlState.UNCONTROLLED:
            state = _ControlState.CONTROLLED if is_ctrl else _ControlState.UNCONTROLLED
            veto_streak = 0
            if trace is not None:
                trace.append(StateTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, is_ctrl))
            continue

        if state == _ControlState.CONTROLLED:
            if is_ctrl:
                if trace is not None:
                    trace.append(StateTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, is_ctrl))
                continue  # extend the same continuous control episode
            if ascent_ok:
                state = _ControlState.SEPARATING
                streak = [(f_b, ascent_path, separation_norm)]
                veto_streak = 0
            elif vvel <= 0:
                # The strict CONTROLLED predicate failed, but the ball is
                # not moving away/down -- this is normal developing-launch
                # ambiguity, not evidence the episode ended. Carry
                # provenance forward into TRANSITION rather than
                # discarding it.
                state = _ControlState.TRANSITION
                veto_streak = 1 if _is_veto_pending(vvel, separated, cfg) else 0
            else:
                # vvel > 0: the ball is moving away/down while not
                # gripped -- an unambiguous independent fall (a drop, a
                # dribble bounce's origin). This episode may never again
                # authorize a later ascent.
                state = _ControlState.UNCONTROLLED
                veto_streak = 0
            if trace is not None:
                trace.append(StateTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, is_ctrl))
            continue

        if state == _ControlState.TRANSITION:
            if is_ctrl:
                state = _ControlState.CONTROLLED  # ambiguity resolved back into genuine control
                veto_streak = 0
            elif ascent_ok:
                state = _ControlState.SEPARATING
                streak = [(f_b, ascent_path, separation_norm)]
                veto_streak = 0
            elif _is_veto_pending(vvel, separated, cfg):
                veto_streak += 1
                if veto_streak >= cfg.veto_override_frames:
                    state = _ControlState.SEPARATING
                    streak = [(f_b, "strong_override", separation_norm)]
                    veto_streak = 0
                # else: stay in TRANSITION, still an ambiguous glued-ball frame
            elif vvel <= 0:
                pass  # still developing, no new evidence either way -- stay in TRANSITION
            else:
                # vvel > 0: the ambiguity has resolved into a fall.
                # Provenance is discarded.
                state = _ControlState.UNCONTROLLED
                veto_streak = 0
            if trace is not None:
                trace.append(StateTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, is_ctrl))
            continue

        # state == SEPARATING
        if streak and streak[-1][1] == "strong_override":
            # A streak that started via the veto override is, by
            # definition, one where separation isn't a trusted signal
            # (the wrist keypoint is presumed stuck/misassociated) -- its
            # continuation must keep using the same relaxed, velocity-only
            # criterion, not suddenly re-demand separated=True on the very
            # next frame.
            continues = vvel <= -cfg.strong_upward_velocity_norm
            frame_path = "strong_override"
        else:
            continues, frame_path = ascent_ok, ascent_path
        if continues:
            streak.append((f_b, frame_path, separation_norm))
            if len(streak) >= cfg.consecutive_frames:
                release_f, release_path, release_sep = streak[0]
                base_confidence = {"strong": 0.75, "soft": 0.6, "strong_override": 0.55}[release_path]
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
                # Reset to UNCONTROLLED: the continuing flight is far from
                # any wrist, so it cannot spuriously re-satisfy CONTROLLED
                # and re-fire on the same physical ascent.
                state = _ControlState.UNCONTROLLED
                veto_streak = 0
            if trace is not None:
                trace.append(StateTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, is_ctrl))
            continue

        # Ascent broke -- never falls back to authorizing a NEW ascent
        # without a fresh control episode. Same vvel-sign reasoning as the
        # CONTROLLED branch: a broken ascent that's still net-upward/flat
        # is ambiguous, not disqualifying.
        streak = []
        if is_ctrl:
            state = _ControlState.CONTROLLED
        elif vvel <= 0:
            state = _ControlState.TRANSITION
        else:
            state = _ControlState.UNCONTROLLED
        veto_streak = 0
        if trace is not None:
            trace.append(StateTraceEntry(a_fi, b_fi, state_before.value, state.value, vvel, separated, is_ctrl))

    return events
