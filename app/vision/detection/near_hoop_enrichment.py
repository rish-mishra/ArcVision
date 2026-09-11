"""
Densifies ball-position evidence specifically in the vicinity of the hoop,
for each already-segmented shot's flight window, without touching the
global ball_observations that shot segmentation and biomechanics already
depend on.

Why a separate pass: the global tracker's trajectory (built once, for the
whole video, before the hoop is even known) essentially never reaches the
hoop's immediate vicinity on real footage -- diagnosed on a real video, the
closest confirmed point for any of seven real shots was 300+ pixels from a
39px-radius rim. Re-reading just each shot's flight window and running a
hoop-ROI-scoped, upscaled secondary detector (see hoop_roi_ball_detector.py)
against it is cheap (a few dozen frames per shot, not the whole video) and
targets exactly the evidence gap that matters most for outcome detection.

Single-frame, single-candidate trust was tried first and diagnosed as
insufficient on real footage: a real made shot's ball is clearly visible to
the eye in a run of consecutive near-hoop frames, but the ROI detector's
classical (color/circularity) pass -- the only one firing at all near an
overexposed sky background where YOLO-World's "basketball" prompt produced
nothing -- caps every single-frame candidate at a flat, low confidence
(around 0.25), because only one of its two corroborating cues (shape,
color) passes at a time in this lighting. No fixed per-frame confidence
floor can be raised or lowered to fix that without either trusting pure
noise elsewhere or discarding this real evidence -- the discriminating
signal was never in any one frame's score.

What actually separates the real ball from clutter (net wires, backboard
edges, stray background shapes) here is temporal coherence: the genuine
ball's candidate position in one frame is where the next frame's genuine
candidate should physically be, given the shot's own already-observed
speed, while spurious detections do not line up into any such path. So
this module builds a per-shot chain across frames -- seeded from the
shot's own last solid (DETECTED/INTERPOLATED) global point, extended frame
by frame to whichever ROI candidate is closest to the position predicted
from the chain so far, gated by a maximum speed calibrated from that same
video's own observed ball motion (never a hardcoded constant) -- and only
trusts the points in a chain long enough (several consecutive frames) to
not plausibly be coincidence. A chain that never reaches that length is
discarded entirely rather than partially trusted.

This never overrides a frame the global tracker already DETECTED or
INTERPOLATED with real confidence -- it only fills in frames where the
global trajectory has nothing (UNAVAILABLE) or only a bare Kalman guess
(PREDICTED), and only for points that survive the chain-coherence gate
above. Every added point is tagged `DataSource.DETECTED`; its confidence
reflects both the underlying detector's own score and how many consecutive
frames corroborate it, never a flat or invented number.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from app.analytics.shot_record import ShotRecord
from app.config import CONFIG
from app.events.shot_state_machine import ShotWindow
from app.logging_config import get_logger
from app.pipeline.video_io import FrameReader
from app.vision.detection.hoop_roi_ball_detector import HoopROIBallDetector
from app.vision.types import BallObservation, DataSource, HoopLocation

log = get_logger("vision.near_hoop_enrichment")

# A chain shorter than this (consecutive-ish accepted frames, gaps allowed)
# is not trusted at all -- one or two coincidentally-aligned candidates is
# not enough to distinguish a real ball path from clutter that happens to
# line up once.
MIN_CHAIN_LENGTH = 3

# Safety multiplier applied to this video's own observed max ball speed
# when gating how far a chain may jump between frames -- descent
# accelerates under gravity, so the gate must allow somewhat faster motion
# than the fastest *observed* consecutive-frame displacement, without being
# so loose it accepts unrelated clutter.
SPEED_GATE_SAFETY_FACTOR = 1.6

# Floor for the per-frame confidence a chain member must have to even be
# considered as a candidate to extend the chain with (keeps pure-noise
# contours -- near-zero circularity/color support -- out of consideration
# regardless of how the chain gate would otherwise score their position).
MIN_CANDIDATE_CONFIDENCE = 0.15


def _observed_max_speed_px_per_sec(ball_observations: List[BallObservation]) -> float:
    """
    Self-calibrates a per-video speed bound from this same video's own
    genuine (DETECTED) consecutive-frame ball displacements, instead of
    an arbitrary or video-specific constant -- the 95th percentile of
    observed speeds, so a handful of noisy outlier pairs can't blow the
    bound out, but real fast stretches (e.g. near-apex or descent) set it.
    """
    detected = sorted((o for o in ball_observations if o.source == DataSource.DETECTED),
                        key=lambda o: o.frame_index)
    speeds = []
    for a, b in zip(detected, detected[1:]):
        dt = b.timestamp_sec - a.timestamp_sec
        if dt <= 1e-6:
            continue
        dist = ((b.center_x - a.center_x) ** 2 + (b.center_y - a.center_y) ** 2) ** 0.5
        speeds.append(dist / dt)
    if not speeds:
        return 0.0
    speeds.sort()
    idx = min(len(speeds) - 1, int(round(0.95 * (len(speeds) - 1))))
    return speeds[idx]


_STATIC_REPEAT_EPS_PX = 2.0
_MAX_CONSECUTIVE_STATIC_REPEATS = 2

# Iterative projectile-fit pruning: unpowered flight has constant
# horizontal velocity and constant vertical acceleration (gravity) over the
# short span of a single shot, so this is a physically-grounded check (not
# a full 3D reconstruction) for whether a chained point actually belongs on
# the same arc as the rest -- a candidate that was accepted frame-to-frame
# under the speed gate (a real but coarse constraint) can still be a
# clutter detour that happens to be reachable at each step without lying
# on the one consistent arc the genuine ball traces.
_PROJECTILE_FIT_MIN_POINTS = 5
_PROJECTILE_FIT_MAX_ITERS = 8
_PROJECTILE_FIT_RESIDUAL_FLOOR_PX = 12.0


def _anchors_at_or_before(ball_observations: List[BallObservation], frame_index: int) -> List[BallObservation]:
    """The two most recent genuine (DETECTED/INTERPOLATED) points at or
    before frame_index, oldest first -- used to seed both a position and an
    initial velocity estimate for the chain, rather than assuming the ball
    is still sitting at its last-known position."""
    candidates = sorted((o for o in ball_observations
                           if o.frame_index <= frame_index and o.source in (DataSource.DETECTED, DataSource.INTERPOLATED)),
                          key=lambda o: o.frame_index)
    return candidates[-2:]


def _prune_by_projectile_fit(seed: BallObservation, points: List[BallObservation],
                                hoop: HoopLocation) -> List[BallObservation]:
    """
    Fits this shot's own chain (seed + newly-recovered points) to constant
    horizontal velocity / constant vertical acceleration, then iteratively
    drops whichever point disagrees with that fit the most -- refitting
    each time -- until every remaining point is within a residual bound
    (a floor in pixels, or a multiple of the fit's own residual spread,
    whichever is larger, so a small handful of genuinely tight points
    doesn't force an unreasonably strict cutoff). Requires at least
    _PROJECTILE_FIT_MIN_POINTS total points to fit at all; with fewer,
    there isn't enough data to distinguish a real curve from noise, so
    every point is kept as-is.
    """
    all_points = [seed] + list(points)
    if len(all_points) < _PROJECTILE_FIT_MIN_POINTS:
        return points

    kept = list(points)
    for _ in range(_PROJECTILE_FIT_MAX_ITERS):
        fit_set = [seed] + kept
        if len(fit_set) < _PROJECTILE_FIT_MIN_POINTS:
            break
        t0 = fit_set[0].timestamp_sec
        ts = np.array([p.timestamp_sec - t0 for p in fit_set])
        xs = np.array([p.center_x for p in fit_set])
        ys = np.array([p.center_y for p in fit_set])

        y_coef = np.polyfit(ts, ys, 2)
        x_coef = np.polyfit(ts, xs, 1)
        y_pred = np.polyval(y_coef, ts)
        x_pred = np.polyval(x_coef, ts)
        residuals = np.sqrt((xs - x_pred) ** 2 + (ys - y_pred) ** 2)

        # Capped by a fixed multiple of rim size, not left to scale
        # unboundedly with the fit's own median residual -- a chain that
        # includes a wrong detour drags the median up too, which would
        # otherwise let the threshold grow to excuse exactly the points it
        # should be catching.
        threshold = max(_PROJECTILE_FIT_RESIDUAL_FLOOR_PX,
                          min(hoop.rim_radius_px * 1.5, 2.5 * float(np.median(residuals))))
        # residuals[0] is the seed's own residual -- never drop the seed.
        worst_idx = int(np.argmax(residuals[1:])) + 1 if len(residuals) > 1 else -1
        if worst_idx == -1 or residuals[worst_idx] <= threshold:
            break
        kept.pop(worst_idx - 1)  # -1 to account for the seed at index 0

    return kept


def _build_chain_for_shot(lo: int, hi: int, ball_observations: List[BallObservation],
                            per_frame_candidates: Dict[int, List], hoop: HoopLocation,
                            max_speed_px_per_sec: float) -> List[BallObservation]:
    """
    Walks frames lo..hi in order, extending a single position/velocity
    chain seeded from the last one or two genuine (DETECTED/INTERPOLATED)
    global points at or before this range. At each gap frame, accepts the
    candidate closest to the position PREDICTED from the chain's current
    velocity (not a frozen last-known position -- a real ball keeps moving
    through a blackout, and gating against a stale position lets the
    tolerance balloon over a long gap until it accepts whatever's nearby,
    which on real footage turned out to be background clutter rather than
    the ball). The gate itself still grows with elapsed time (a longer gap
    carries more prediction uncertainty) but off a moving reference point,
    scaled from this video's own observed ball speed.

    A candidate that repeats (within a couple of pixels) the position the
    chain already sits at, for more than _MAX_CONSECUTIVE_STATIC_REPEATS
    frames in a row, ends the chain right there instead of being accepted
    -- a ball in flight or falling essentially never holds one exact pixel
    position for multiple consecutive frames, so a run of exact repeats is
    far more consistent with the detector having locked onto a fixed
    background feature (a window, a light, a backboard corner) than with
    the ball genuinely stopping in mid-air.

    Returns the newly-recovered points only (existing global points are
    left for the caller to keep as-is) -- and returns nothing at all unless
    the chain reaches MIN_CHAIN_LENGTH accepted points.
    """
    seed_anchors = _anchors_at_or_before(ball_observations, lo)
    if not seed_anchors or max_speed_px_per_sec <= 0:
        return []

    seed = seed_anchors[-1]
    last_pos = (seed.center_x, seed.center_y)
    last_t = seed.timestamp_sec
    if len(seed_anchors) == 2:
        a, b = seed_anchors
        dt0 = b.timestamp_sec - a.timestamp_sec
        velocity = ((b.center_x - a.center_x) / dt0, (b.center_y - a.center_y) / dt0) if dt0 > 1e-6 else (0.0, 0.0)
    else:
        velocity = (0.0, 0.0)

    newly_accepted: List[BallObservation] = []
    static_repeats = 0

    for fi in range(lo, hi + 1):
        candidates = per_frame_candidates.get(fi)
        if not candidates:
            continue
        best_choice = None
        best_dist = None
        best_pos = None
        for det in candidates:
            if det.confidence < MIN_CANDIDATE_CONFIDENCE:
                continue
            cx, cy = det.center
            dt = det.timestamp_sec - last_t
            if dt <= 0:
                continue
            pred_x = last_pos[0] + velocity[0] * dt
            pred_y = last_pos[1] + velocity[1] * dt
            gate = max_speed_px_per_sec * SPEED_GATE_SAFETY_FACTOR * dt * 0.5 + hoop.rim_radius_px * 0.75
            dist = ((cx - pred_x) ** 2 + (cy - pred_y) ** 2) ** 0.5
            if dist > gate:
                continue
            if best_dist is None or dist < best_dist:
                best_dist, best_choice, best_pos = dist, det, (cx, cy)
        if best_choice is None:
            continue

        repeat = (abs(best_pos[0] - last_pos[0]) < _STATIC_REPEAT_EPS_PX
                   and abs(best_pos[1] - last_pos[1]) < _STATIC_REPEAT_EPS_PX)
        if repeat:
            static_repeats += 1
            if static_repeats > _MAX_CONSECUTIVE_STATIC_REPEATS:
                break
        else:
            static_repeats = 0

        dt = best_choice.timestamp_sec - last_t
        if dt > 1e-6:
            velocity = ((best_pos[0] - last_pos[0]) / dt, (best_pos[1] - last_pos[1]) / dt)
        last_pos = best_pos
        last_t = best_choice.timestamp_sec
        newly_accepted.append(BallObservation(
            frame_index=best_choice.frame_index, timestamp_sec=best_choice.timestamp_sec,
            center_x=best_pos[0], center_y=best_pos[1], radius_px=max(best_choice.width, best_choice.height) / 2.0,
            confidence=best_choice.confidence, source=DataSource.DETECTED, track_id=None,
        ))

    newly_accepted = _prune_by_projectile_fit(seed, newly_accepted, hoop)

    if len(newly_accepted) < MIN_CHAIN_LENGTH:
        return []

    n = len(newly_accepted)
    out = []
    for p in newly_accepted:
        chained_confidence = min(0.6, p.confidence + 0.05 * n)
        out.append(BallObservation(
            frame_index=p.frame_index, timestamp_sec=p.timestamp_sec,
            center_x=p.center_x, center_y=p.center_y, radius_px=p.radius_px,
            confidence=chained_confidence, source=DataSource.DETECTED, track_id=None,
        ))
    return out


def enrich_near_hoop(video_path, meta, windows: List[ShotWindow], ball_observations: List[BallObservation],
                       hoop: Optional[HoopLocation], w: int, h: int,
                       margin_sec: float = 0.5) -> Dict[int, List[BallObservation]]:
    """
    Returns {shot_index: enriched flight-window trajectory}. If hoop is
    None, returns the original (un-enriched) trajectory per shot --
    there's no known location to focus a search around.
    """
    ball_by_frame = {o.frame_index: o for o in ball_observations}
    enriched: Dict[int, List[BallObservation]] = {}

    if hoop is None or not windows:
        for win in windows:
            enriched[win.shot_index] = [o for o in ball_observations
                                          if win.start_frame <= o.frame_index <= win.end_frame]
        return enriched

    roi_detector = HoopROIBallDetector(hoop, w, h)
    roi_detector.warmup()
    max_speed_px_per_sec = _observed_max_speed_px_per_sec(ball_observations)

    # Bound each shot's re-read window: never before the shot's own start,
    # never past a small margin beyond its end, and never into the next
    # shot's territory.
    sorted_windows = sorted(windows, key=lambda ww: ww.start_frame)
    fps = meta.fps
    ranges = []
    for idx, win in enumerate(sorted_windows):
        next_start = sorted_windows[idx + 1].start_frame if idx + 1 < len(sorted_windows) else None
        margin_frames = int(margin_sec * fps)
        hi = win.end_frame + margin_frames
        if next_start is not None:
            hi = min(hi, next_start - 1)
        ranges.append((win.shot_index, win.start_frame, hi))

    frame_to_shots: Dict[int, List[int]] = {}
    for shot_index, lo, hi in ranges:
        for fi in range(lo, hi + 1):
            frame_to_shots.setdefault(fi, []).append(shot_index)

    if not frame_to_shots:
        return {win.shot_index: [] for win in windows}

    lo_all = min(frame_to_shots)
    hi_all = max(frame_to_shots)

    per_shot_frame_candidates: Dict[int, Dict[int, List]] = {sid: {} for sid, _, _ in ranges}

    reader = FrameReader(meta)
    n_candidate_frames = 0
    for af in reader:
        if af.frame_index < lo_all or af.frame_index > hi_all:
            continue
        shot_ids = frame_to_shots.get(af.frame_index)
        if not shot_ids:
            continue

        existing = ball_by_frame.get(af.frame_index)
        already_solid = existing is not None and existing.source in (DataSource.DETECTED, DataSource.INTERPOLATED)
        if already_solid:
            continue

        candidates = roi_detector.detect(af.image, af.frame_index, af.timestamp_sec)
        if not candidates:
            continue
        n_candidate_frames += 1
        for sid in shot_ids:
            per_shot_frame_candidates[sid][af.frame_index] = candidates

    added_points: Dict[int, List[BallObservation]] = {}
    n_enriched_frames = 0
    for shot_index, lo, hi in ranges:
        chain = _build_chain_for_shot(lo, hi, ball_observations, per_shot_frame_candidates[shot_index],
                                        hoop, max_speed_px_per_sec)
        added_points[shot_index] = chain
        n_enriched_frames += len(chain)

    log.info("Near-hoop enrichment considered %d candidate frame(s), added %d trusted point(s) across %d shot(s)",
              n_candidate_frames, n_enriched_frames, len(ranges))

    for shot_index, lo, hi in ranges:
        base = [o for o in ball_observations if lo <= o.frame_index <= hi]
        extra = added_points.get(shot_index, [])
        extra_frames = {o.frame_index for o in extra}
        base = [o for o in base if o.frame_index not in extra_frames]
        merged = sorted(base + extra, key=lambda o: o.frame_index)
        enriched[shot_index] = merged

    return enriched
