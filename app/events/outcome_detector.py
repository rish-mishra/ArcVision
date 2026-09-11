"""
Determines MADE / MISSED / UNKNOWN for a single shot from its ball
trajectory and the (video-level, mostly-static-camera) hoop location.

This is a full redesign, not a patch, after diagnosing seven real shots:
the earlier version classified outcome from isolated coordinate checks
("is there a point below rim height that's also far away") which could be
satisfied by an ordinary post-catch ball position anywhere in the window,
not genuine rim-interaction evidence -- on that real video, all seven
shots resolved to the exact same generic branch with an identical
confidence score, which was the bug's signature rather than seven
independent findings.

The redesign reasons about the trajectory as a temporal sequence of
phases -- RELEASE -> ASCENT -> APEX -> DESCENT -> HOOP APPROACH -> RIM
INTERACTION -> POST-RIM MOTION -- and only classifies MADE or MISSED when
there is positive, temporally-ordered, geometrically-coherent evidence for
that specific phase sequence, from points that were actually observed
(DETECTED or short-gap INTERPOLATED), never from PREDICTED-only (pure
Kalman extrapolation) points. Everything short of that positive-evidence
bar is UNKNOWN -- a first-class, expected outcome on real footage, not a
fallback to be minimized.

A second pass, after diagnosing nine more real shots on a different video
against revealed ground truth, found the phase-sequence architecture above
was sound but three of its evidence checks were not geometrically or
temporally strict enough: (1) the MADE crossing checked each point's own
distance from the rim center but never how far the crossing itself
drifted, so a diagonal rim/backboard deflection through the same
tolerance zone read the same as a clean pass-through; (2) both the MADE
crossing-gap and the MISS deflection evidence were bounded in raw frame
count, which penalizes exactly the frames hardest to track cleanly (rim/
net occlusion during a genuine pass-through) while imposing no real
temporal-relatedness bound, letting a stale point from a second or more
later (the ball already on the ground) be read as evidence about an
earlier crossing; (3) a clean, small-drift, occlusion-free crossing was
being scored as confidently as one with genuine occlusion evidence, even
though a single static camera cannot tell a ball that passed through the
rim's opening from one that sailed past its depth plane entirely --
occlusion (a confidence dip, or a genuine detection gap, during the
crossing) is the only proxy available for "actually went through," and
its absence is not proof of a miss, just absence of support for a make.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from app.config import CONFIG
from app.vision.types import BallObservation, DataSource, HoopLocation


class ShotOutcome(str, Enum):
    MADE = "made"
    MISSED = "missed"
    UNKNOWN = "unknown"


@dataclass
class OutcomeResult:
    outcome: ShotOutcome
    confidence: float
    reason: str
    points_above: int = 0
    points_below: int = 0
    crossing_gap_frames: Optional[int] = None
    evidence: dict = field(default_factory=dict)


_RELIABLE_SOURCES = (DataSource.DETECTED, DataSource.INTERPOLATED)


def _reliable(points: List[BallObservation]) -> List[BallObservation]:
    return [p for p in points if p.source in _RELIABLE_SOURCES and p.confidence > 0]


def _reject_trajectory_outliers(points: List[BallObservation], cfg) -> List[BallObservation]:
    """
    Drops INTERPOLATED points that are wildly inconsistent with a smooth
    path between the nearest genuine DETECTED points -- a real ball follows
    a continuous (parabolic, but locally near-linear over a few frames)
    arc, so an interpolated (Kalman-bridged) point that sits far from the
    straight line connecting the nearest real detections before and after
    it is far more likely a tracking-hijack artifact (the associator
    briefly locking onto a different object and the filter bridging that
    bad association) than a genuine ball position.

    A DETECTED point is never rejected here, and the "expected" position
    for consistency-checking is always anchored to the nearest bracketing
    DETECTED points when any exist (searching outward through the whole
    sequence, not just immediate list-neighbors). This was a real-video
    finding, not a hypothetical: with the original immediate-neighbor
    version, a run of several consecutive interpolated points that were
    mutually self-consistent (a stale Kalman bridge from a bad
    association, not the real ball) locally out-numbered and out-voted two
    isolated, high-confidence DETECTED points that were the genuine ball
    converging on the hoop -- so the filter kept the fabricated cluster
    and threw away the real evidence. Anchoring to the nearest real
    detections (and never rejecting a detection) fixes that: an
    interpolated run can no longer discredit the detections it was
    supposed to be bridging between.

    Points with no bracketing DETECTED point on one or both sides (e.g.
    interpolated points trailing after the last detection in the window)
    fall back to their immediate list-neighbors, since there is no more
    trustworthy anchor available.

    This is a light, local consistency check, not a full physics fit
    (monocular footage doesn't support one) -- it only catches gross
    discontinuities, and never touches the first/last point in the list.
    """
    if len(points) < 3:
        return points
    detected_idx = [i for i, p in enumerate(points) if p.source == DataSource.DETECTED]
    kept = []
    for i, cur in enumerate(points):
        if cur.source == DataSource.DETECTED or i == 0 or i == len(points) - 1:
            kept.append(cur)
            continue
        before = max((j for j in detected_idx if j < i), default=None)
        after = min((j for j in detected_idx if j > i), default=None)
        if before is not None and after is not None:
            prev, nxt = points[before], points[after]
        else:
            prev, nxt = points[i - 1], points[i + 1]
        dt_total = nxt.timestamp_sec - prev.timestamp_sec
        if dt_total <= 1e-6:
            kept.append(cur)
            continue
        t_frac = (cur.timestamp_sec - prev.timestamp_sec) / dt_total
        pred_x = prev.center_x + t_frac * (nxt.center_x - prev.center_x)
        pred_y = prev.center_y + t_frac * (nxt.center_y - prev.center_y)
        deviation = ((cur.center_x - pred_x) ** 2 + (cur.center_y - pred_y) ** 2) ** 0.5
        segment_span = ((nxt.center_x - prev.center_x) ** 2 + (nxt.center_y - prev.center_y) ** 2) ** 0.5
        tolerance = max(segment_span * cfg.trajectory_outlier_span_frac, cur.radius_px * cfg.trajectory_outlier_min_radii)
        if deviation > tolerance:
            continue  # drop cur -- an interpolated point inconsistent with a smooth path between the nearest real detections
        kept.append(cur)
    return kept


def _find_apex(points: List[BallObservation]) -> Optional[BallObservation]:
    """The reliable point with the smallest y (highest position)."""
    if not points:
        return None
    return min(points, key=lambda p: p.center_y)


def _interaction_band(hoop: HoopLocation, ball_radius_px: float, cfg) -> float:
    """
    Horizontal tolerance for 'in the rim's vicinity', combining the rim's
    own size with the observed ball's apparent radius -- a bigger apparent
    ball (closer to camera / more zoomed) carries proportionally more
    pixel-position uncertainty, so its tolerance should scale with it too,
    not just with the rim's fixed apparent size. This is an image-space
    heuristic, not a claim of precise 3D geometry (monocular video can't
    give us that) -- see docs/METHODOLOGY.md.
    """
    return hoop.rim_radius_px * cfg.horizontal_margin_frac_of_rim_radius + ball_radius_px


def _wide_zone(hoop: HoopLocation, ball_radius_px: float, cfg) -> float:
    return hoop.rim_radius_px * cfg.wide_zone_frac_of_rim_radius + ball_radius_px


def _in_band(p: BallObservation, hoop: HoopLocation, band: float) -> bool:
    return abs(p.center_x - hoop.rim_center_x) <= band


def _above_rim(p: BallObservation, hoop: HoopLocation) -> bool:
    return p.center_y < hoop.rim_top_y


def _below_rim(p: BallObservation, hoop: HoopLocation) -> bool:
    return p.center_y > hoop.rim_bottom_y


def _near_rim_height(p: BallObservation, hoop: HoopLocation, cfg) -> bool:
    tol = hoop.rim_radius_px * cfg.near_rim_height_frac_of_rim_radius
    return abs(p.center_y - hoop.rim_center_y) <= tol


def _occlusion_dip_ratio(crossing_span: List[BallObservation], all_points: List[BallObservation]) -> float:
    """
    A single static camera cannot see depth, so the only proxy this
    pipeline has for "did the ball actually pass through the rim opening"
    (as opposed to sailing past it at a different, unobservable depth) is
    occlusion: a ball genuinely passing through the opening is partially
    hidden by the front rim/net from the camera's view for at least a
    moment, and that should show up as either a confidence dip on a point
    that was still detected, or a frame where nothing usable was detected
    at all (a true gap in the raw per-frame log, or an explicit
    UNAVAILABLE reading) -- as opposed to a point that exists but was
    later outlier-rejected as an inconsistent, wrong-object association,
    which is contaminated data, not occlusion evidence. Returns the ratio
    of the lowest confidence found to the crossing's bracketing
    confidence; a full raw-frame gap counts as a ratio of 0.0 (the
    strongest possible occlusion signal).
    """
    a, b = crossing_span[0], crossing_span[-1]
    baseline_conf = max(a.confidence, b.confidence)
    if baseline_conf <= 0:
        return 1.0
    covered_frames = {p.frame_index for p in all_points
                       if a.frame_index < p.frame_index < b.frame_index
                       and p.source != DataSource.UNAVAILABLE and p.confidence > 0}
    expected_frames = set(range(a.frame_index + 1, b.frame_index))
    if expected_frames - covered_frames:
        return 0.0
    min_conf = min(p.confidence for p in crossing_span)
    return min_conf / baseline_conf


def detect_outcome(trajectory: List[BallObservation], hoop: Optional[HoopLocation],
                    cfg=None) -> OutcomeResult:
    cfg = cfg or CONFIG.outcome

    if hoop is None or hoop.confidence < cfg.min_hoop_confidence_to_attempt:
        return OutcomeResult(ShotOutcome.UNKNOWN, 0.0, "hoop_location_not_reliable")

    points = sorted(trajectory, key=lambda p: p.frame_index)
    reliable = _reliable(points)
    n_before_outlier_rejection = len(reliable)
    reliable = _reject_trajectory_outliers(reliable, cfg)
    n_outliers_rejected = n_before_outlier_rejection - len(reliable)
    n_detected = sum(1 for p in reliable if p.source == DataSource.DETECTED)
    n_interp = sum(1 for p in reliable if p.source == DataSource.INTERPOLATED)
    n_predicted = sum(1 for p in points if p.source == DataSource.PREDICTED)

    # Track-identity stability: what fraction of the surviving trajectory
    # is genuine detection rather than Kalman-bridged guesswork. A track
    # that is mostly interpolated is more exposed to exactly the kind of
    # bad-association bridging that _reject_trajectory_outliers only
    # partially guards against (it can't rescue points with no bracketing
    # detection at all), so outcome confidence should discount for it
    # rather than treating every "reliable" point as equally trustworthy.
    track_stability = (n_detected / len(reliable)) if reliable else 0.0
    stability_factor = 0.5 + 0.5 * track_stability

    evidence = {
        "n_reliable_points": len(reliable), "n_detected": n_detected, "n_interpolated": n_interp,
        "n_predicted_only": n_predicted, "hoop_confidence": hoop.confidence,
        "n_trajectory_outliers_rejected": n_outliers_rejected,
        "track_stability": round(track_stability, 3),
    }

    if len(reliable) < cfg.min_reliable_points_to_attempt:
        evidence["why"] = "too few directly-observed/interpolated ball points to reason about at all"
        return OutcomeResult(ShotOutcome.UNKNOWN, 0.0, "insufficient_ball_trajectory_data", evidence=evidence)

    # --- ASCENT / APEX / DESCENT ---
    apex = _find_apex(reliable)
    apex_is_endpoint = apex is reliable[0] or apex is reliable[-1]
    ascent_pts = [p for p in reliable if p.frame_index <= apex.frame_index]
    descent_pts = [p for p in reliable if p.frame_index >= apex.frame_index]
    evidence["apex_frame"] = apex.frame_index
    evidence["apex_observed_as_endpoint"] = apex_is_endpoint
    evidence["n_ascent_points"] = len(ascent_pts)
    evidence["n_descent_points"] = len(descent_pts)

    if apex_is_endpoint and len(reliable) < cfg.min_reliable_points_when_apex_unconfirmed:
        # The trajectory might be truncated before the true apex (still
        # rising when we lose it) or after it (already falling when we
        # first see it) -- either way we can't confidently reason about
        # ascent-vs-descent with so little data anchored to a guessed apex.
        evidence["why"] = "apex not clearly bracketed by observed points, and too few points to compensate"
        return OutcomeResult(ShotOutcome.UNKNOWN, 0.0, "apex_not_reliably_observed", evidence=evidence)

    if len(descent_pts) < cfg.min_descent_points_to_attempt:
        evidence["why"] = "descent phase has too few observed points to assess rim interaction"
        return OutcomeResult(ShotOutcome.UNKNOWN, 0.0, "insufficient_descent_observation", evidence=evidence)

    avg_radius = sum(p.radius_px for p in reliable) / len(reliable)
    tight_band = _interaction_band(hoop, avg_radius, cfg)
    wide_band = _wide_zone(hoop, avg_radius, cfg)
    evidence["tight_band_px"] = round(tight_band, 1)
    evidence["wide_band_px"] = round(wide_band, 1)

    descent_above_tight = [p for p in descent_pts if _above_rim(p, hoop) and _in_band(p, hoop, tight_band)]
    descent_below_tight = [p for p in descent_pts if _below_rim(p, hoop) and _in_band(p, hoop, tight_band)]

    # ================= MADE =================
    # Require a chronologically-ordered above -> below crossing within the
    # TIGHT band, close together in TIME (not raw frame count -- see
    # max_seconds_through_rim), with the crossing pair itself drifting only
    # a small fraction of the rim's own radius (not the full tight-band
    # tolerance -- see max_crossing_drift_frac_of_rim_radius), and
    # everything observed in between (if anything) staying consistent with
    # a clean pass-through (still within the wide zone, not clearly
    # deflected out to the side). This is checked before any MISS evidence
    # is considered: a genuine earlier crossing must not be overridden by
    # unrelated later motion (the ball bouncing/rolling well after it left
    # the rim's vicinity).
    max_drift = hoop.rim_radius_px * cfg.max_crossing_drift_frac_of_rim_radius
    for a in descent_above_tight:
        later_below = [b for b in descent_below_tight
                        if b.frame_index > a.frame_index
                        and (b.timestamp_sec - a.timestamp_sec) <= cfg.max_seconds_through_rim]
        if not later_below:
            continue
        b = min(later_below, key=lambda x: x.frame_index)
        drift = abs(b.center_x - a.center_x)
        if drift > max_drift:
            continue  # crossed the tolerance zone at an angle, not a clean pass-through
        between = [p for p in reliable if a.frame_index < p.frame_index < b.frame_index]
        deflected_between = any(not _in_band(p, hoop, wide_band) for p in between)
        if deflected_between:
            continue

        crossing_span = [a] + between + [b]
        dip_ratio = _occlusion_dip_ratio(crossing_span, points)
        if dip_ratio > cfg.min_occlusion_dip_frac:
            continue  # no occlusion evidence -- can't rule out a same-depth-plane airball past the rim

        gap = b.frame_index - a.frame_index
        gap_seconds = b.timestamp_sec - a.timestamp_sec
        gap_quality = 1.0 - (gap_seconds / (cfg.max_seconds_through_rim + 1e-6))
        drift_quality = 1.0 - (drift / max_drift) if max_drift > 0 else 0.0
        occlusion_quality = 1.0 - (dip_ratio / cfg.min_occlusion_dip_frac)
        approach_quality = min(1.0, len(descent_above_tight) / max(cfg.min_points_above, 1))
        exit_quality = min(1.0, len(descent_below_tight) / max(cfg.min_points_below, 1))
        source_quality = 1.0 if (a.source == DataSource.DETECTED and b.source == DataSource.DETECTED) else 0.8

        # Drift and occlusion are weighted most heavily: together they are
        # the strongest discriminators found between genuine pass-throughs
        # and (a) rim/backboard deflections that cross the same horizontal
        # tolerance zone at an angle, and (b) same-depth-plane airballs
        # that project through the rim band without ever being occluded by it.
        confidence = (0.12 + 0.20 * drift_quality + 0.20 * occlusion_quality + 0.10 * approach_quality
                       + 0.08 * exit_quality + 0.15 * gap_quality + 0.15 * source_quality
                       ) * (0.5 + 0.5 * hoop.confidence) * stability_factor
        confidence = min(1.0, confidence)

        evidence.update({
            "crossing_above_frame": a.frame_index, "crossing_below_frame": b.frame_index,
            "points_between": len(between), "crossing_drift_px": round(drift, 1),
            "max_crossing_drift_px": round(max_drift, 1), "crossing_gap_seconds": round(gap_seconds, 3),
            "occlusion_dip_ratio": round(dip_ratio, 3),
        })
        # Rough, rim-depth-only estimate -- see biomechanics/rim_calibration.py
        # for exactly why this is the only physical-unit estimate this
        # pipeline attempts, and why it's never extended to the shooter's
        # release (a different, uncalibrated depth from the camera).
        from app.biomechanics.rim_calibration import estimate_speed_near_rim
        entry_speed = estimate_speed_near_rim(a, b, hoop, cfg)
        if entry_speed is not None:
            evidence["rim_entry_speed_mps_estimate"] = round(entry_speed, 2)
        if confidence < cfg.min_outcome_confidence_to_report:
            return OutcomeResult(ShotOutcome.UNKNOWN, round(confidence, 3),
                                   "rim_crossing_observed_but_low_confidence", points_above=len(descent_above_tight),
                                   points_below=len(descent_below_tight), crossing_gap_frames=gap, evidence=evidence)
        return OutcomeResult(
            ShotOutcome.MADE, round(confidence, 3), "ball_crossed_rim_band_top_to_bottom",
            points_above=len(descent_above_tight), points_below=len(descent_below_tight),
            crossing_gap_frames=gap, evidence=evidence,
        )

    # ================= MISS (requires positive evidence) =================
    # Case 1: the ball was reliably observed approaching the rim (wide
    # zone, from above) and a LATER reliable point shows it clearly
    # deflected away (outside the tight band while at/below rim height, or
    # back above ascending again) -- a rim/backboard rejection. The
    # deflection point must occur shortly (max_seconds_deflection_after_
    # approach) after the approach: a point outside the wide zone found
    # much later is not evidence of a rim deflection, it is just the ball
    # having moved on (bounced, rolled, been retrieved) after leaving the
    # rim's vicinity entirely, and using it as "deflection" evidence
    # produced confident false MISS calls on genuine makes that the ball
    # continued past (through the net, to the floor) after already
    # crossing the rim -- crossing evidence the MADE check above did not
    # find within the old, frame-count-bounded gap window.
    descent_near_wide_above = [p for p in descent_pts if _in_band(p, hoop, wide_band) and _above_rim(p, hoop)]
    if descent_near_wide_above:
        last_approach = descent_near_wide_above[-1]
        after = [p for p in reliable if p.frame_index > last_approach.frame_index
                 and (p.timestamp_sec - last_approach.timestamp_sec) <= cfg.max_seconds_deflection_after_approach]
        deflected = [p for p in after if not _in_band(p, hoop, wide_band)]
        if deflected and len(descent_near_wide_above) >= cfg.min_points_above:
            deflection_frame = deflected[0]
            dt = deflection_frame.timestamp_sec - last_approach.timestamp_sec
            promptness_quality = 1.0 - (dt / (cfg.max_seconds_deflection_after_approach + 1e-6))
            evidence.update({
                "approach_points": len(descent_near_wide_above), "deflection_frame": deflection_frame.frame_index,
                "deflection_seconds_after_approach": round(dt, 3),
            })
            approach_quality = min(1.0, len(descent_near_wide_above) / max(cfg.min_points_above, 1))
            confidence = (0.30 + 0.30 * promptness_quality + 0.20 * approach_quality
                          + 0.20 * min(1.0, 0.08 * len(descent_near_wide_above))) * (0.5 + 0.5 * hoop.confidence) * stability_factor
            confidence = min(1.0, confidence)
            if confidence < cfg.min_outcome_confidence_to_report:
                return OutcomeResult(ShotOutcome.UNKNOWN, round(confidence, 3),
                                       "possible_deflection_but_low_confidence", evidence=evidence)
            return OutcomeResult(ShotOutcome.MISSED, round(confidence, 3),
                                   "ball_approached_rim_then_deflected_away",
                                   points_above=len(descent_near_wide_above), evidence=evidence)

    # Case 2: the ball was reliably observed near rim HEIGHT (within a
    # vertical tolerance of the rim) but clearly OUTSIDE even the wide
    # horizontal zone -- passed beside the hoop -- with points both before
    # (above) and confirming it never entered the zone at all. Bounded to
    # shortly after the apex for the same reason Case 1's deflection is
    # time-bounded: an unrelated later point (rebound, retrieval) must not
    # be read as "beside the hoop" evidence about this shot's own flight.
    near_apex_descent = [p for p in descent_pts
                          if (p.timestamp_sec - apex.timestamp_sec) <= cfg.max_seconds_from_apex_for_descent_evidence]
    near_height_pts = [p for p in near_apex_descent if _near_rim_height(p, hoop, cfg)]
    beside = [p for p in near_height_pts if not _in_band(p, hoop, wide_band)]
    if beside and len(descent_pts) >= cfg.min_descent_points_to_attempt:
        confidence = min(1.0, 0.5 + 0.05 * len(beside)) * (0.5 + 0.5 * hoop.confidence) * stability_factor
        evidence["beside_points"] = len(beside)
        if confidence < cfg.min_outcome_confidence_to_report:
            return OutcomeResult(ShotOutcome.UNKNOWN, round(confidence, 3),
                                   "possible_miss_beside_hoop_but_low_confidence", evidence=evidence)
        return OutcomeResult(ShotOutcome.MISSED, round(confidence, 3),
                               "ball_passed_beside_hoop_at_rim_height", evidence=evidence)

    # Case 3: airball / clear miss -- descent points are confidently
    # observed well below rim height while remaining clearly outside the
    # band the whole time (never approached at all), AND at least one
    # point was above/near rim height first (so we know it came from
    # above, not that we simply never tracked it near the hoop).
    far_descent = [p for p in near_apex_descent if _below_rim(p, hoop) and not _in_band(p, hoop, wide_band)]
    had_height_context = any(p.center_y <= hoop.rim_center_y + wide_band for p in ascent_pts + descent_pts)
    if far_descent and had_height_context and len(descent_pts) >= cfg.min_descent_points_to_attempt:
        confidence = min(1.0, 0.4 + 0.05 * len(far_descent)) * (0.5 + 0.5 * hoop.confidence) * stability_factor
        evidence["far_descent_points"] = len(far_descent)
        if confidence < cfg.min_outcome_confidence_to_report:
            return OutcomeResult(ShotOutcome.UNKNOWN, round(confidence, 3),
                                   "trajectory_diverged_but_low_confidence", evidence=evidence)
        return OutcomeResult(ShotOutcome.MISSED, round(confidence, 3),
                               "ball_descended_well_clear_of_hoop", evidence=evidence)

    # ================= UNKNOWN =================
    evidence["why"] = "no phase sequence met the positive-evidence bar for MADE or MISSED"
    return OutcomeResult(ShotOutcome.UNKNOWN, 0.0, "rim_interaction_not_sufficiently_observed", evidence=evidence)
