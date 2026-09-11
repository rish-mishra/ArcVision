"""
SHADOW-ONLY research module. Not imported by production (app/pipeline,
app/events, app/api, or anything reachable from run_pipeline()). See
docs/POST_CONTACT_REVERSAL_SHADOW.md.

Detects a single physical event -- RIM ENTRY -> POST-CONTACT REVERSAL / ESCAPE
-- from an existing ball trajectory + hoop location, as a diagnostic episode,
not an outcome. This exists to test one hypothesis from the visual audit
(docs/OUTCOME_VISUAL_INFORMATION_AUDIT.md): a genuine rim rattle shows the
ball descending into the rim's interaction zone, then reversing direction and
leaving the zone again within a few frames -- a temporal, multi-point pattern
the production MADE logic's single (a, b) crossing-pair check cannot see,
because it only asks "was there SOME above point and SOME later below point
that align," never "did the ball's own depth ever go back down after
climbing back up."

Deliberately reuses, unmodified, the same normalized geometry the production
outcome detector already computes (app.events.outcome_detector): the tight/
wide interaction bands (rim-radius-relative), the reliable-point filter and
outlier rejection, the apex/descent split, "near rim height," the existing
max_seconds_from_apex_for_descent_evidence time bound (to find the wide-band
interaction window itself), and -- as of the contact-relative-scoping
correction described in docs/POST_CONTACT_REVERSAL_SHADOW.md -- the existing
max_seconds_through_rim bound (0.75s, already used by production to say how
long a single rim-crossing event may plausibly span) to decide how long
after CONTACT a reversal/escape may still be attributed to that same rim
interaction, rather than to unrelated later motion (the ball already on the
floor, rolling, retrieved). No new pixel-magnitude threshold is introduced
anywhere in this module -- every
comparison is either a strict ordinal (>, <) comparison against the
trajectory's own achieved values, or a point-COUNT requirement reusing the
existing cfg.min_points_below value (already used in outcome_detector.py as
"how many points are needed before an exit-direction claim is trusted" --
see its exit_quality/approach_quality use there). If this investigation had
required a genuinely new fitted constant, it would have stopped instead of
inventing one; it did not need to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.config import CONFIG
from app.events import outcome_detector as od
from app.vision.types import BallObservation, DataSource, HoopLocation


@dataclass
class ReversalEpisode:
    reason: str
    evidence_quality: str  # "insufficient" | "weak" | "strong"

    interaction_start_frame: Optional[int] = None
    interaction_end_frame: Optional[int] = None

    contact_frame: Optional[int] = None
    contact_timestamp_sec: Optional[float] = None
    pre_contact_descending: Optional[bool] = None
    pre_contact_n_points: int = 0

    reversal_detected: bool = False
    reversal_timestamp_sec: Optional[float] = None
    reversal_confirm_frames: List[int] = field(default_factory=list)
    max_depth_frame: Optional[int] = None

    escape_detected: bool = False
    escape_direction: Optional[str] = None  # "lateral" | "upward" | "lateral_and_upward" | None

    n_detected_support: int = 0
    n_interpolated_support: int = 0

    evidence: dict = field(default_factory=dict)


def analyze_post_contact_reversal(trajectory: List[BallObservation],
                                    hoop: Optional[HoopLocation], cfg=None) -> ReversalEpisode:
    cfg = cfg or CONFIG.outcome

    if hoop is None or hoop.confidence < cfg.min_hoop_confidence_to_attempt:
        return ReversalEpisode("hoop_location_not_reliable", "insufficient")

    points = sorted(trajectory, key=lambda p: p.frame_index)
    reliable = od._reliable(points)
    reliable = od._reject_trajectory_outliers(reliable, cfg)
    if len(reliable) < cfg.min_reliable_points_to_attempt:
        return ReversalEpisode("insufficient_ball_trajectory_data", "insufficient")

    apex = od._find_apex(reliable)
    descent_pts = [p for p in reliable if p.frame_index >= apex.frame_index]
    if len(descent_pts) < cfg.min_descent_points_to_attempt:
        return ReversalEpisode("insufficient_descent_observation", "insufficient")

    avg_radius = sum(p.radius_px for p in reliable) / len(reliable)
    tight_band = od._interaction_band(hoop, avg_radius, cfg)
    wide_band = od._wide_zone(hoop, avg_radius, cfg)

    # Same time bound production already uses for "is this later point still
    # plausibly about THIS shot's rim interaction" (far_descent/beside checks).
    near_apex_descent = [p for p in descent_pts
                          if (p.timestamp_sec - apex.timestamp_sec) <= cfg.max_seconds_from_apex_for_descent_evidence]

    # Wide-band membership only decides WHEN the ball first plausibly enters
    # the hoop's vicinity (and, via contact_pts below, when it's genuinely
    # at rim height) -- once inside that window, later points must NOT be
    # filtered back out for having left the band again, or the very escape
    # this module looks for would be discarded before ever being scanned.
    wide_band_pts = [p for p in near_apex_descent if od._in_band(p, hoop, wide_band)]
    if not wide_band_pts:
        return ReversalEpisode("no_rim_interaction_region_observed", "insufficient")

    interaction_start = wide_band_pts[0].frame_index
    episode_pts = [p for p in near_apex_descent if p.frame_index >= interaction_start]

    ep = ReversalEpisode("", "insufficient",
                           interaction_start_frame=interaction_start,
                           interaction_end_frame=episode_pts[-1].frame_index)

    contact_pts = [p for p in wide_band_pts
                    if od._in_band(p, hoop, tight_band) and od._near_rim_height(p, hoop, cfg)]
    if not contact_pts:
        ep.reason = "no_contact_level_proximity_observed"
        return ep

    contact = contact_pts[0]
    ep.contact_frame = contact.frame_index
    ep.contact_timestamp_sec = contact.timestamp_sec

    pre_contact = [p for p in episode_pts if p.frame_index < contact.frame_index]
    # Reversal/escape evidence is only trusted within max_seconds_through_rim
    # of CONTACT -- the existing constant production already uses to bound
    # how long a single rim-crossing event may plausibly span (previously
    # this module used max_seconds_from_apex_for_descent_evidence, a 2.0s
    # bound designed for a different, already-known-unreliable-as-standalone
    # check, measured from apex rather than contact -- see
    # docs/POST_CONTACT_REVERSAL_SHADOW.md's account of why that let ordinary
    # post-make/post-miss aftermath motion masquerade as a rim-contact
    # reversal on every shot). No new constant: this is a straight
    # substitution of the already-existing, more semantically appropriate
    # bound for the one mistakenly reused.
    post_contact = [p for p in episode_pts
                     if contact.frame_index <= p.frame_index
                     and (p.timestamp_sec - contact.timestamp_sec) <= cfg.max_seconds_through_rim]
    ep.pre_contact_n_points = len(pre_contact)
    if len(pre_contact) >= 2:
        ep.pre_contact_descending = pre_contact[-1].center_y > pre_contact[0].center_y

    if len(post_contact) < 2:
        ep.reason = "insufficient_post_contact_observation"
        return ep

    # Running max-depth (max center_y = deepest/lowest apparent position)
    # scan. A point strictly above the max-so-far (smaller y) is a reversal
    # candidate; reaching a NEW max resets any in-progress candidate run,
    # since that means the ball went back down past its earlier wobble --
    # not a sustained reversal (this is what makes test F/G -- a tiny bounce
    # that still continues downward -- correctly NOT flag). A reversal is
    # only CONFIRMED once cfg.min_points_below such points have accumulated
    # without being reset -- the same existing point-count already used in
    # outcome_detector.py to decide when an exit-direction claim is trusted.
    max_y_so_far = post_contact[0].center_y
    max_y_frame = post_contact[0].frame_index
    confirm_pts: List[BallObservation] = []
    for p in post_contact[1:]:
        if p.center_y > max_y_so_far:
            max_y_so_far = p.center_y
            max_y_frame = p.frame_index
            confirm_pts = []
        elif p.center_y < max_y_so_far:
            confirm_pts.append(p)
        # equal y: neither confirms nor resets

    ep.max_depth_frame = max_y_frame
    ep.reversal_detected = len(confirm_pts) >= cfg.min_points_below
    if not ep.reversal_detected:
        if not confirm_pts:
            # The ball never once sat above its own running maximum depth
            # after contact -- a clean, monotonic continuation. This is a
            # confident NEGATIVE result (strong evidence of no reversal),
            # not a lack of evidence -- single-frame jitter or a tiny bounce
            # that the ball's own later, deeper points supersede (test D/F/G)
            # lands here too, by construction of the reset-on-new-max scan.
            ep.reason = "no_reversal_clean_continuation"
            ep.evidence_quality = "strong"
        else:
            ep.reason = "reversal_candidate_not_sustained"
            ep.evidence_quality = "weak"
            ep.evidence["confirm_points_short_of_requirement"] = len(confirm_pts)
        return ep

    ep.reversal_confirm_frames = [p.frame_index for p in confirm_pts]
    ep.reversal_timestamp_sec = confirm_pts[0].timestamp_sec
    ep.n_detected_support = sum(1 for p in confirm_pts if p.source == DataSource.DETECTED)
    ep.n_interpolated_support = sum(1 for p in confirm_pts if p.source == DataSource.INTERPOLATED)

    if ep.n_detected_support == 0:
        # Confirmed structurally, but entirely by Kalman-bridged points --
        # the same "never trust interpolated-only for a strong claim"
        # philosophy production already applies elsewhere in this file.
        ep.reason = "reversal_structurally_present_but_interpolated_only"
        ep.evidence_quality = "insufficient"
        return ep

    left_wide_band = any(not od._in_band(p, hoop, wide_band) for p in confirm_pts)
    left_upward = any(od._above_rim(p, hoop) for p in confirm_pts)
    ep.escape_detected = left_wide_band or left_upward
    if left_wide_band and left_upward:
        ep.escape_direction = "lateral_and_upward"
    elif left_wide_band:
        ep.escape_direction = "lateral"
    elif left_upward:
        ep.escape_direction = "upward"

    if ep.escape_detected:
        ep.reason = "post_contact_reversal_with_escape"
        ep.evidence_quality = "strong"
    else:
        ep.reason = "post_contact_reversal_without_confirmed_escape"
        ep.evidence_quality = "weak"

    return ep
