"""
Segments a full session into individual shot attempts using an explicit
finite-state machine driven by multiple signals (ball-hand distance, ball
vertical velocity, knee flexion, ball height relative to the shoulder).

Using a single signal ("ball moved upward") would also fire on dribbles,
passes, and ball retrieval, so the machine requires a LOAD phase (knee
flexion drop while the ball stays near the hand) before it will recognize
an UPWARD phase, and requires the ball to rise above shoulder height and
then separate from the hand before declaring a RELEASE. This is what keeps
dribbles/passes from being miscounted as shots -- see tests/test_shot_state_machine.py
for the synthetic sequences this is validated against.

Primary trigger vs. fallback trigger: the primary path requires the ball to
be directly tracked near the shooting hand to enter LOAD. Diagnosing a real
video showed this can fail almost entirely in practice -- a held/gripped
basketball is small and partly occluded by fingers, which is hard for a
generic object detector, even though the SAME video's ball detections were
reasonably reliable once the ball was in clear flight (larger, unoccluded,
high contrast against open background). If continuous ball-hand tracking
were required to ever start a shot, a session with this (common, not
unusual) detection profile would report zero shots despite every release
being directly observable in the data. The fallback trigger recognizes a
sustained, confirmed upward ball flight as a release-in-progress on its
own, and reconstructs the load window afterward from the pose-only
knee-angle trace in the few seconds before it -- pose tracking held up
fine (>95% of frames) on that same video even where ball tracking did not.

The machine runs over the whole (already-extracted) per-frame signal
sequence rather than streaming live, since analysis happens after upload,
so backward lookback for the fallback path is just an index operation on
data already in memory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from app.config import CONFIG


class ShotPhase(str, Enum):
    IDLE = "idle"
    LOAD = "load"
    UPWARD = "upward"
    RELEASED = "released"
    FLIGHT = "flight"
    RESET = "reset"


@dataclass
class FrameSignals:
    frame_index: int
    timestamp_sec: float
    ball_available: bool
    ball_x: Optional[float] = None
    ball_y: Optional[float] = None
    ball_hand_dist_norm: Optional[float] = None
    ball_vertical_velocity_norm: Optional[float] = None  # negative = moving up
    knee_angle_deg: Optional[float] = None
    shoulder_y: Optional[float] = None
    pose_confidence: float = 0.0
    # True only for a genuinely DETECTED or short-gap-INTERPOLATED ball
    # position; False for a purely Kalman-extrapolated (PREDICTED) one.
    # `ball_available` alone doesn't distinguish these, which matters for
    # the fallback trigger below: it has no other corroborating evidence,
    # so it must not fire on the tracker's own momentum guess continuing
    # an upward trend after the real ball was last actually seen.
    ball_is_observed: bool = True
    # Shooter's hip-center x position, in torso-length units (same scale
    # as ball_hand_dist_norm/velocity). Absolute value is meaningless --
    # only used to measure how much the shooter translated horizontally
    # over a window, to distinguish a stationary shot's load from walking.
    hip_x_norm: Optional[float] = None
    # Raw pixel positions of each wrist, when detected -- additive fields
    # for app/events/release_event_detector.py (migration-plan Phase 1),
    # which needs each wrist's actual position (to check separation from
    # BOTH wrists and height relative to BOTH wrists independently), not
    # just the single nearest-wrist scalar distance ball_hand_dist_norm
    # already provides for the existing state machine. Unused by
    # ShotStateMachine itself.
    left_wrist_xy: Optional["tuple[float, float]"] = None
    right_wrist_xy: Optional["tuple[float, float]"] = None
    # The raw DataSource behind ball_x/ball_y (DETECTED/INTERPOLATED/
    # PREDICTED/UNAVAILABLE) -- ball_is_observed above already collapses
    # DETECTED and INTERPOLATED into one boolean for the existing state
    # machine, which is coarser than release_event_detector.py needs: it
    # must distinguish a genuine detection from an interpolated bridge to
    # anchor its own outlier rejection the same way outcome_detector.py's
    # _reject_trajectory_outliers does. Unused by ShotStateMachine itself.
    ball_source: Optional[object] = None


@dataclass
class ShotWindow:
    shot_index: int
    start_frame: int
    end_frame: int
    load_start_frame: Optional[int]
    upward_start_frame: Optional[int]
    release_candidate_frame: Optional[int]
    flight_end_frame: Optional[int]
    warnings: List[str] = field(default_factory=list)


@dataclass
class TraceEvent:
    """One row per analyzed frame, recorded when `enable_trace=True`.
    Exists purely for diagnosing real-footage failures (see
    scripts/shot_timeline_debug.py) -- production runs leave this off."""
    frame_index: int
    timestamp_sec: float
    phase_before: str
    phase_after: str
    ball_available: bool
    ball_hand_dist_norm: Optional[float]
    ball_vertical_velocity_norm: Optional[float]
    knee_angle_deg: Optional[float]
    fallback_run: int
    separation_run: int
    stationary_run: int
    unavailable_run: int


def _genuine_knee_dip_nearby(frames: List[FrameSignals], hi_index: int, lo_bound_frame: int,
                               lookback_frames: int, min_drop_deg: float) -> bool:
    """
    True if the knee-angle trace shows a real DIP -- extended, then bent
    down to a local minimum that sits at or near `hi_index` -- somewhere in
    the window ending at `hi_index`, reaching back up to `lookback_frames`,
    but never before `lo_bound_frame` (e.g. the end of the previous shot --
    otherwise an unrelated later burst could "borrow" a genuine dip that
    actually belonged to an earlier, already-closed shot). Permissive
    (returns True) when no knee data is available in the window at all,
    per the "don't require every signal" principle.

    This used to be a plain max-min range check with no regard for order,
    which a real video exposed as a false positive once ball tracking got
    dense enough to reliably reach this check at all: the very first
    frames of a clip caught the shooter mid-motion with knees already
    bent (say 130 degrees) from whatever they were doing before the clip
    starts, simply straightening to a normal standing pose (170-179
    degrees) as they picked up the ball -- range comfortably over
    min_drop_deg, but the *direction* is backwards (extending, never
    bending), which is not a shooting load at all. Requiring a genuinely
    higher, extended baseline BEFORE the minimum is what tells a real bend
    apart from that one-directional straightening.

    Deliberately does NOT also require a rise AFTER the minimum: this is
    called both retrospectively, well after a release has completed (where
    "after" data exists), and live, evaluating the CURRENT frame as the
    fallback trigger watches for the upward burst as it happens -- at that
    moment the deepest knee bend often coincides with `hi_index` itself
    (the release is only just beginning), so no "after" data can exist yet
    by construction. A real video's actual release frame was misclassified
    (reverted to idle instead of progressing to the upward/flight phases)
    when this function required both sides, which is precisely that
    causal, live-evaluation case -- confirming the "after" requirement was
    wrong, not just overly cautious.

    Used identically by both trigger paths: a primary-trigger LOAD phase
    is often recognized late (ball-hand detection frequently only
    confirms proximity after the real dip has already started, since a
    held ball is hard to detect at all -- see the ball-detector notes),
    so checking only "how much lower did the knee get AFTER load was
    recognized" misses dips that happened just before. Looking backward
    from wherever we currently are, the same way the fallback trigger
    already needs to, fixes that asymmetry.
    """
    lo = max(lo_bound_frame, hi_index - lookback_frames + 1, 0)
    windowed = [(idx, f.knee_angle_deg) for idx, f in enumerate(frames[lo:hi_index + 1], start=lo)
                 if f.knee_angle_deg is not None]
    if not windowed:
        return True
    min_idx, min_val = min(windowed, key=lambda p: p[1])
    before = [v for idx, v in windowed if idx < min_idx]
    if not before:
        # Nothing precedes the lowest angle in the available window -- no
        # visibility into whether it was reached by a genuine bend from a
        # more extended baseline, or the window simply starts already bent
        # (e.g. a clip beginning mid-motion).
        return False
    return (max(before) - min_val) >= min_drop_deg


def _shooter_was_stationary_nearby(frames: List[FrameSignals], hi_index: int, lo_bound_frame: int,
                                      lookback_frames: int, max_translation_norm: float) -> bool:
    """
    True if the shooter's hip position stayed within `max_translation_norm`
    torso-lengths over the window ending at `hi_index` (same bounding rule
    as the knee-dip check). A jump shot is taken from an essentially
    stationary base; walking while dribbling is not, and unlike the knee
    angle, natural gait produces a REAL (not noise) knee-flexion dip large
    enough to otherwise pass the load check above -- horizontal
    translation is what actually distinguishes the two. Permissive (True)
    when no hip-position data is available.
    """
    lo = max(lo_bound_frame, hi_index - lookback_frames + 1, 0)
    values = [f.hip_x_norm for f in frames[lo:hi_index + 1] if f.hip_x_norm is not None]
    if not values:
        return True
    return (max(values) - min(values)) <= max_translation_norm


def _is_upward_velocity_burst(f: FrameSignals, cfg) -> bool:
    """True when the ball is confirmed and moving upward fast, with no
    requirement on its height yet -- used for the LOAD->UPWARD trigger,
    which can fire right as the ball starts rising (before it has
    necessarily cleared shoulder height)."""
    return (f.ball_available and f.ball_vertical_velocity_norm is not None
            and f.ball_vertical_velocity_norm <= -cfg.upward_velocity_threshold_norm)


def _is_upward_flight_signal(f: FrameSignals, cfg) -> bool:
    """True when this frame's ball motion looks like part of a genuine,
    already-in-progress release/flight: moving up fast AND at or above
    shoulder height (permissive when shoulder height is unknown). Used to
    (a) confirm a real separation/release once already in UPWARD, where
    the docstring's "rise above shoulder height" requirement actually
    belongs, and (b) qualify the fallback trigger, which has no preceding
    LOAD confirmation to lean on and so needs the stricter bar."""
    return _is_upward_velocity_burst(f, cfg) and (
        f.shoulder_y is None or f.ball_y is None or f.ball_y <= f.shoulder_y
    )


class ShotStateMachine:
    def __init__(self, cfg=None, enable_trace: bool = False):
        self.cfg = cfg or CONFIG.shot
        self.trace: Optional[List[TraceEvent]] = [] if enable_trace else None
        self._phase = ShotPhase.IDLE
        self._load_start: Optional[int] = None
        self._upward_start: Optional[int] = None
        self._separation_run = 0
        self._release_frame: Optional[int] = None
        self._stationary_run = 0
        self._unavailable_run = 0
        self._shot_start: Optional[int] = None
        self._flight_frames_elapsed = 0
        self._fallback_run = 0
        self._fallback_triggered = False
        self._windows: List[ShotWindow] = []
        self._next_shot_index = 1
        self._last_shot_end: Optional[int] = None
        # Set only when a window closes WITHOUT positive confirmation that
        # the ball's motion actually concluded (flight-duration cap or a
        # tracking blackout) -- never after a confirmed settle. See
        # ShotDetectionConfig.post_flight_ownership_frames.
        self._fallback_suppressed_until: Optional[int] = None

    def _reset_to_idle(self):
        self._phase = ShotPhase.IDLE
        self._load_start = None
        self._upward_start = None
        self._separation_run = 0
        self._release_frame = None
        self._stationary_run = 0
        self._unavailable_run = 0
        self._shot_start = None
        self._flight_frames_elapsed = 0
        self._fallback_run = 0
        self._fallback_triggered = False

    def _cooldown_ok(self, frame_index: int) -> bool:
        if self._last_shot_end is None:
            return True
        return (frame_index - self._last_shot_end) >= self.cfg.min_frames_between_shots

    def process(self, frames: List[FrameSignals]) -> List[ShotWindow]:
        for i in range(len(frames)):
            if self.trace is not None:
                f = frames[i]
                phase_before = self._phase.value
                self._step(frames, i)
                self.trace.append(TraceEvent(
                    frame_index=f.frame_index, timestamp_sec=f.timestamp_sec,
                    phase_before=phase_before, phase_after=self._phase.value,
                    ball_available=f.ball_available, ball_hand_dist_norm=f.ball_hand_dist_norm,
                    ball_vertical_velocity_norm=f.ball_vertical_velocity_norm,
                    knee_angle_deg=f.knee_angle_deg, fallback_run=self._fallback_run,
                    separation_run=self._separation_run, stationary_run=self._stationary_run,
                    unavailable_run=self._unavailable_run,
                ))
            else:
                self._step(frames, i)
        # If the sequence ends mid-flight, close out the last shot window.
        if self._phase in (ShotPhase.RELEASED, ShotPhase.FLIGHT) and self._shot_start is not None:
            self._emit_window(frames[-1].frame_index, warnings=["video_ended_during_flight"], confirmed_settled=False)
            self._reset_to_idle()
        return self._windows

    def _emit_window(self, end_frame: int, warnings: Optional[List[str]] = None, confirmed_settled: bool = False):
        w_list = list(warnings or [])
        if self._fallback_triggered:
            w_list.append("load_phase_inferred_from_pose_only_ball_not_tracked_near_hand")
        w = ShotWindow(
            shot_index=self._next_shot_index,
            start_frame=self._shot_start,
            end_frame=end_frame,
            load_start_frame=self._load_start,
            upward_start_frame=self._upward_start,
            release_candidate_frame=self._release_frame,
            flight_end_frame=end_frame,
            warnings=w_list,
        )
        self._windows.append(w)
        if not confirmed_settled:
            # This closure did NOT positively confirm the ball's motion
            # concluded (a duration cap or a tracking blackout, not a
            # confirmed return to the hand) -- the same ball may still be
            # continuing its flight. Give this shot "ownership" of any
            # immediately-following fallback-triggered upward-flight signal
            # for a bounded window, rather than letting it be mistaken for a
            # brand new release. Never suppresses the PRIMARY (ball-hand-
            # proximity) trigger, which has its own, real evidence of a new
            # catch.
            self._fallback_suppressed_until = end_frame + self.cfg.post_flight_ownership_frames
        self._next_shot_index += 1
        self._last_shot_end = end_frame

    def _try_fallback_trigger(self, frames: List[FrameSignals], i: int) -> bool:
        """Checks whether the last `fallback_trigger_frames` frames (ending
        at i) form a sustained, confirmed upward ball flight; if so,
        reconstructs a load window from the pose-only knee-angle trace
        immediately before it and jumps straight to UPWARD.

        Sustained upward ball velocity alone is NOT enough here -- a rim
        rebound produces exactly that signal with the shooter standing
        still (knee angle flat), and this trigger has no preceding LOAD
        confirmation to lean on the way the primary trigger does. So it
        additionally requires the lookback window to show a genuine knee
        flexion dip (see the primary-trigger check below for why this
        specific check catches both a real video's rebound false positive
        and a dribble-bounce false positive)."""
        cfg = self.cfg
        n = cfg.fallback_trigger_frames
        if i + 1 < n:
            return False
        window = frames[i - n + 1: i + 1]
        if not all(_is_upward_flight_signal(wf, cfg) for wf in window):
            return False
        if not any(wf.ball_is_observed for wf in window):
            # Every frame in the qualifying burst is purely a Kalman
            # extrapolation, not an actual detection -- this is the
            # tracker's own momentum guess, not observed evidence of a
            # real release. Do not trust it on its own.
            return False

        upward_start_frame = window[0].frame_index
        # Never let the reconstructed load window reach back into (or
        # before) the PREVIOUS shot's own window -- otherwise a knee dip
        # that genuinely belonged to that earlier shot could get "borrowed"
        # to justify an unrelated later burst (a rebound right after a
        # shot has plenty of real knee-bend history sitting right there in
        # the lookback range).
        lo_bound = (self._last_shot_end + 1) if self._last_shot_end is not None else 0
        if not _genuine_knee_dip_nearby(frames, i - n, lo_bound, cfg.load_lookback_max_frames,
                                          cfg.load_knee_flexion_drop_deg):
            # No genuine loading motion in this window -- most likely a
            # rebound, a retrieval, or another non-shot upward ball
            # movement observed while the shooter was standing still.
            return False
        if not _shooter_was_stationary_nearby(frames, i - n, lo_bound, cfg.load_lookback_max_frames,
                                                 cfg.max_load_hip_translation_norm):
            # Real knee flexion, but the shooter was walking, not set up
            # for a shot (e.g. dribbling toward the hoop) -- gait produces
            # a genuine dip on its own.
            return False

        lookback_lo = max(lo_bound, (i - n + 1) - cfg.load_lookback_max_frames, 0)
        lookback = [wf for wf in frames[lookback_lo: i - n + 1] if wf.knee_angle_deg is not None]

        if lookback:
            load_frame = min(lookback, key=lambda wf: wf.knee_angle_deg)
            load_start_frame = load_frame.frame_index
        else:
            load_start_frame = upward_start_frame

        self._phase = ShotPhase.UPWARD
        self._upward_start = upward_start_frame
        self._load_start = load_start_frame
        self._shot_start = load_start_frame
        self._fallback_triggered = True
        self._separation_run = 0
        return True

    def _step(self, frames: List[FrameSignals], i: int):
        cfg = self.cfg
        f = frames[i]

        if self._phase == ShotPhase.IDLE:
            if not self._cooldown_ok(f.frame_index):
                return

            if (f.ball_available and f.ball_hand_dist_norm is not None
                    and f.ball_hand_dist_norm <= cfg.hand_proximity_threshold_norm
                    and f.knee_angle_deg is not None):
                self._phase = ShotPhase.LOAD
                self._load_start = f.frame_index
                self._shot_start = f.frame_index
                self._fallback_run = 0
                return

            # A shot window that just closed WITHOUT positive confirmation
            # the ball's motion concluded (flight-duration cap or a
            # tracking blackout) still "owns" the ball for a bounded window
            # afterward -- an immediately-continuing upward-flight signal
            # is far more likely the tail of that same flight than a brand
            # new release with no preceding load evidence of its own. This
            # never blocks the PRIMARY trigger above (real ball-hand-
            # proximity evidence of a new catch), only this evidence-free
            # fallback path.
            if (self._fallback_suppressed_until is not None
                    and f.frame_index < self._fallback_suppressed_until):
                self._fallback_run = 0
                return

            # Primary trigger didn't fire this frame (ball not confirmed
            # near the hand) -- track whether we're mid-way through a
            # sustained upward flight burst anyway (fallback trigger).
            if _is_upward_flight_signal(f, cfg):
                self._fallback_run += 1
            else:
                self._fallback_run = 0
            if self._fallback_run >= cfg.fallback_trigger_frames:
                self._try_fallback_trigger(frames, i)

        elif self._phase == ShotPhase.LOAD:
            upward_now = _is_upward_velocity_burst(f, cfg)

            # A dribble bounce produces exactly the same "ball near hand,
            # then moving up fast" signature as a real release -- the
            # difference is that a real shot's load phase involves a
            # genuine, sustained knee-flexion dip, and a dribble (or
            # standing still) does not. Require that dip somewhere in the
            # recent history (looking backward past LOAD's own start, not
            # just "after entry" -- ball-hand detection often only
            # confirms proximity late, well after the real dip already
            # began, since a held ball is hard to detect at all) before
            # treating the upward burst as a release rather than a bounce.
            lo_bound = (self._last_shot_end + 1) if self._last_shot_end is not None else 0
            knee_drop_ok = _genuine_knee_dip_nearby(
                frames, i, lo_bound, cfg.load_lookback_max_frames, cfg.load_knee_flexion_drop_deg
            )
            # Real knee flexion alone isn't enough either -- normal
            # walking gait produces a genuine (not noise) dip too. A shot
            # is taken from a stationary base; require the shooter's hips
            # not to have translated much over the same window.
            stationary_ok = _shooter_was_stationary_nearby(
                frames, i, lo_bound, cfg.load_lookback_max_frames, cfg.max_load_hip_translation_norm
            )
            knee_drop_ok = knee_drop_ok and stationary_ok

            # A strong upward burst IS the load->upward transition, even if
            # ball-hand distance has already ticked past the proximity
            # threshold this same frame (that's expected: the ball is
            # leaving the hand as it's released). Check this BEFORE the
            # "ball wandered off" abandonment check below, otherwise a real
            # release would incorrectly look like the ball just drifting
            # away from an idle hand (which is what should abandon a
            # dribble/pass instead).
            if upward_now and knee_drop_ok:
                self._phase = ShotPhase.UPWARD
                self._upward_start = f.frame_index
                return

            still_close = (f.ball_available and f.ball_hand_dist_norm is not None
                            and f.ball_hand_dist_norm <= cfg.hand_proximity_threshold_norm)
            if not still_close:
                # Ball left the hand area with no upward-release signal --
                # most likely a dribble or a pass, not a shot. Abandon.
                self._reset_to_idle()
                return

            # A genuine shooter may legitimately hold/aim/pump-fake for
            # several seconds before releasing -- this budget is generous
            # specifically so that dwell never gets confused with (or
            # forced to compete against) the separate, much tighter FLIGHT
            # budget below. It still exists so prolonged dribbling/holding
            # (ball repeatedly bouncing back near the hand, so `still_close`
            # never fails) can't dwell in LOAD forever and report an
            # implausibly long, stale shot start time once something
            # finally triggers.
            if (f.frame_index - self._shot_start) > cfg.max_pre_release_duration_frames:
                self._reset_to_idle()

        elif self._phase == ShotPhase.UPWARD:
            if not f.ball_available:
                # A tracking dropout is not itself positive evidence of
                # separation -- the ball may simply be occluded/blurred
                # while still right at the hand (the same "absence isn't
                # evidence" principle FLIGHT's own ball-missing handling
                # below already relies on for a different claim). It may
                # only EXTEND an already-confirmed departure (a real frame
                # already showed the ball genuinely far AND above shoulder
                # height), never manufacture one on its own -- a noisy
                # near-hand touch with no real release can otherwise "seal"
                # a phantom shot the instant tracking drops out, with no
                # confirmed distance ever actually observed.
                if self._separation_run > 0:
                    self._separation_run += 1
            else:
                far = (f.ball_hand_dist_norm is not None
                       and f.ball_hand_dist_norm > cfg.hand_proximity_threshold_norm)
                above_shoulder = (
                    f.shoulder_y is None or f.ball_y is None or f.ball_y <= f.shoulder_y
                )
                if far and above_shoulder:
                    self._separation_run += 1
                else:
                    self._separation_run = 0

            if self._separation_run >= cfg.release_separation_frames:
                self._release_frame = max(f.frame_index - cfg.release_separation_frames + 1,
                                            self._upward_start)
                self._phase = ShotPhase.FLIGHT
                self._flight_frames_elapsed = 0

            duration = f.frame_index - self._shot_start
            if duration > cfg.max_pre_release_duration_frames:
                # Ball never cleanly separated -- likely a false start; abandon.
                self._reset_to_idle()

        elif self._phase == ShotPhase.FLIGHT:
            self._flight_frames_elapsed += 1
            # Measured from RELEASE, not from shot_start -- a shooter who
            # legitimately dwelled for several seconds before releasing
            # (see max_pre_release_duration_frames above) must not have
            # that pre-release time eat into the flight's own budget. A
            # real video's shooter held for ~4.8s before releasing, which
            # under the old, single shared budget left only ~0.2s of
            # flight before a forced close -- while the ball was still
            # unambiguously airborne -- which then let the fallback
            # trigger mistake the rest of that same flight for a brand
            # new shot. Giving flight a fresh budget from its own start
            # fixes that at the root; post_flight_ownership_frames below
            # is defense-in-depth for the rarer case where a real flight
            # still exceeds even this dedicated budget.
            duration = f.frame_index - self._release_frame

            # Two distinct "settled" signals with two different patience
            # budgets. A CONFIRMED return of the ball near the hand is
            # strong evidence and closes the window quickly. The ball
            # simply going undetected is NOT evidence the shot ended --
            # real footage routinely loses the ball for many consecutive
            # frames purely from detector limitations, even mid-flight --
            # but an unresolved total blackout still can't be allowed to
            # run all the way out to max_flight_duration_frames, or the
            # window swallows the start of the *next* shot. So a longer,
            # physically-motivated blackout budget (roughly how long a
            # real shot's flight can take) applies instead. Either ball
            # visible AND clearly still far from the hand resets both --
            # that's unambiguous evidence the shot is still in progress.
            ball_confirmed_settled = (
                f.ball_available and f.ball_hand_dist_norm is not None
                and f.ball_hand_dist_norm <= cfg.hand_proximity_threshold_norm
            )
            ball_missing = not f.ball_available

            if ball_confirmed_settled:
                self._stationary_run += 1
                self._unavailable_run = 0
            elif ball_missing:
                self._unavailable_run += 1
                self._stationary_run = 0
            else:
                self._stationary_run = 0
                self._unavailable_run = 0

            if self._stationary_run >= cfg.reset_stationary_frames:
                # The ball CONFIRMED returning near the hand is positive
                # evidence the shot's motion is over -- safe to let an
                # immediately-following upward signal be treated as a
                # genuinely new shot (no fallback suppression).
                warnings = []
                if duration < cfg.min_shot_duration_frames:
                    warnings.append("short_duration")
                self._emit_window(f.frame_index, warnings=warnings, confirmed_settled=True)
                self._reset_to_idle()
            elif self._unavailable_run >= cfg.reset_unavailable_frames:
                warnings = ["closed_after_prolonged_ball_tracking_dropout"]
                if duration < cfg.min_shot_duration_frames:
                    warnings.append("short_duration")
                self._emit_window(f.frame_index, warnings=warnings, confirmed_settled=False)
                self._reset_to_idle()
            elif duration > cfg.max_flight_duration_frames:
                self._emit_window(f.frame_index, warnings=["max_duration_exceeded"], confirmed_settled=False)
                self._reset_to_idle()


def detect_shots(frames: List[FrameSignals], cfg=None) -> List[ShotWindow]:
    machine = ShotStateMachine(cfg)
    return machine.process(frames)
