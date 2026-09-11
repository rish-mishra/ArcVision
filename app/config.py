"""
Central configuration for FormAI Basketball.

Every tunable threshold used anywhere in the pipeline lives here so behavior
can be audited and adjusted in one place instead of being scattered as magic
numbers through the codebase. Values are grouped by pipeline stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
JOBS_DIR = DATA_DIR / "jobs"
OUTPUTS_DIR = DATA_DIR / "outputs"
DB_PATH = DATA_DIR / "db" / "formai.sqlite3"
MODELS_DIR = PROJECT_ROOT / "models"

for _d in (UPLOADS_DIR, JOBS_DIR, OUTPUTS_DIR, DB_PATH.parent, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class VideoConfig:
    allowed_extensions: tuple = (".mp4", ".mov", ".m4v", ".avi")
    max_file_size_mb: int = 500
    max_duration_sec: float = 300.0
    min_duration_sec: float = 1.5
    min_width: int = 320
    min_height: int = 240
    # Frames are analyzed at this max resolution (longer side, px) to keep
    # detector inference fast; original video is only re-read for annotation.
    analysis_max_dim: int = 960
    # Cap analysis frame rate; footage shot at 60/120fps is subsampled to
    # this rate for detection/pose (still enough to catch a release event).
    analysis_target_fps: float = 30.0


@dataclass(frozen=True)
class PersonDetectorConfig:
    model_name: str = "yolov8n.pt"
    confidence_threshold: float = 0.35
    iou_threshold: float = 0.45
    # Of all detected persons, the "primary shooter" is chosen as the one
    # with the largest bounding-box area averaged over a short window,
    # unless ball-proximity strongly indicates a different person.
    min_track_frames_for_primary: int = 5


@dataclass(frozen=True)
class PoseConfig:
    model_complexity: int = 1  # mediapipe BlazePose: 0=lite,1=full,2=heavy
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    landmark_visibility_threshold: float = 0.5
    # Smoothing: exponential moving average alpha applied to landmark
    # coordinates, disabled inside +/- this many frames of a candidate
    # release event to avoid lagging the most important moment.
    smoothing_alpha: float = 0.35
    smoothing_freeze_window_frames: int = 3
    # A standing/shooting basketball player's knee (hip-knee-ankle) angle
    # essentially never goes below this while upright -- a reading lower
    # than this is far more likely a pose-estimation error (a real video
    # showed occasional single-frame readings around 50-80 degrees during
    # a person-overlap moment, which fed a spurious "genuine load" signal
    # into shot detection) than an actual squat-depth knee bend. Landmark
    # visibility passing its own threshold does not guarantee a physically
    # plausible joint configuration, so this is a second, independent check.
    min_plausible_knee_angle_deg: float = 90.0


@dataclass(frozen=True)
class BallDetectorConfig:
    model_name: str = "yolov8n.pt"
    confidence_threshold: float = 0.25
    iou_threshold: float = 0.45
    coco_sports_ball_class_id: int = 32
    # Basketball color validation (HSV) — orange/brown leather under normal
    # lighting. Used to re-rank/validate generic "sports ball" detections.
    hsv_lower_1: tuple = (5, 80, 60)
    hsv_upper_1: tuple = (22, 255, 255)
    min_circularity: float = 0.55
    max_relative_size: float = 0.35  # ball bbox shouldn't exceed this fraction of frame height
    min_relative_size: float = 0.01

    # Learned candidate source: YOLO-World open-vocabulary detection,
    # prompted directly as "basketball" rather than COCO's generic "sports
    # ball" class. On real footage (a real basketball, held and partially
    # occluded by the shooter's hand at typical recreational-court camera
    # distance) COCO's sports-ball class recalled the ball in under 10% of
    # frames even at an increased inference resolution; the same frames
    # against the same YOLO-World prompt recalled it in ~37% of frames --
    # still imperfect (that's what the Kalman tracker's gap-bridging and the
    # shot state machine's fallback trigger are for), but a large enough
    # improvement to use as a primary source, not just a color/shape filter
    # on top of a COCO class. Reuses the same yolov8s-worldv2.pt weights as
    # the learned hoop detector (see HoopDetectorConfig) via a SEPARATE
    # model instance, so either can be swapped independently later.
    use_learned_detector: bool = True
    learned_model_name: str = "yolov8s-worldv2.pt"
    learned_confidence_floor: float = 0.05
    learned_prompts: tuple = ("basketball",)


@dataclass(frozen=True)
class HoopDetectorConfig:
    # Classical CV: orange rim color mask + Hough circle transform,
    # aggregated over a sample of frames from a (assumed) mostly-static camera.
    # Kept as one candidate SOURCE (cheap, and still useful for the common
    # case of a bright-orange indoor/outdoor rim), but NOT relied on alone --
    # see learned_* below. A real backyard hoop with a dark/weathered rim
    # against a bright sky produced zero color-mask pixels for an entire
    # session, which is why this is no longer the only source.
    sample_frame_count: int = 40
    hough_dp: float = 1.5
    hough_min_dist_frac: float = 0.15  # fraction of frame height
    hough_param1: float = 80
    hough_param2: float = 25
    hough_min_radius_frac: float = 0.015
    hough_max_radius_frac: float = 0.09
    cluster_distance_px: float = 40.0
    min_votes_for_confidence: int = 4
    min_confidence_to_auto_accept: float = 0.4

    # Learned candidate source: YOLO-World open-vocabulary detection
    # ("basketball hoop" / "rim" / "backboard" / "net" as text prompts).
    # Unlike the color mask, this has no assumption about rim color/material,
    # which is what makes it work on hoops the classical detector can't see
    # at all. Zero-shot confidence on a single frame is low by design (a
    # generic vision-language model, not a hoop-specialized one) -- it is
    # only trustworthy in aggregate, via the same cross-frame clustering
    # used for the classical candidates.
    use_learned_detector: bool = True
    learned_model_name: str = "yolov8s-worldv2.pt"
    learned_confidence_floor: float = 0.01
    learned_prompts: tuple = ("basketball hoop", "basketball rim", "basketball backboard", "basketball net")


@dataclass(frozen=True)
class BallRimDetectorConfig:
    # Basketball-specific detector, fine-tuned from RF-DETR-Small on the
    # University of Arizona "Basketball Shooting Robot" dataset (Roboflow
    # Universe, CC BY 4.0) -- see docs/METHODOLOGY.md "Detector
    # architecture" for the full story and scripts/train_ball_rim_detector.py
    # for how the checkpoint was produced. A/B benchmarked against the
    # combined YOLOv8+YOLO-World+classical-CV stack on real footage and
    # found dramatically better on every measured axis: ball coverage
    # 23%->81% of frames (near-rim coverage ~0%->~90%+, the specific gap
    # this whole detector upgrade exists to close), rim coverage 71%->99%
    # with ~6.6x tighter positional stability, mean ball-detection
    # confidence 0.31->0.69, and FASTER (38.9 vs 28.0 fps) despite being
    # one model instead of four. See data/diagnostics/detector_benchmark/
    # for the full report and visual comparisons this decision was based on.
    #
    # One forward pass yields BOTH classes, so this REPLACES the ball
    # detectors (YOLOv8 sports_ball + validate_ball_candidates + YOLO-World
    # "basketball") and hoop detectors (classical color/Hough + YOLO-World
    # hoop prompts) as the primary source when enabled -- those older
    # detectors are kept in the codebase (not deleted) as an automatic
    # fallback if the checkpoint is missing, and as standalone diagnostic/
    # comparison tooling (see scripts/benchmark_ball_rim_detectors.py,
    # scripts/visual_benchmark_frames.py).
    enabled: bool = True
    checkpoint_name: str = "rfdetr_ball_rim_v1.pth"
    confidence_floor: float = 0.3


@dataclass(frozen=True)
class TrackerConfig:
    max_age_frames: int = 12  # bridge gaps up to this many frames
    min_hits_to_confirm: int = 2
    iou_match_threshold: float = 0.15
    max_center_jump_px_per_frame: float = 140.0
    # Above this many consecutively-missed frames, position is reported as
    # UNAVAILABLE rather than silently extrapolated forever.
    max_extrapolation_frames: int = 6


@dataclass(frozen=True)
class ShotDetectionConfig:
    # State machine thresholds, in normalized units where noted.
    hand_proximity_threshold_norm: float = 0.18  # ball-wrist dist / torso length
    load_knee_flexion_drop_deg: float = 12.0
    upward_velocity_threshold_norm: float = 0.35  # ball vertical speed, body-heights/sec
    release_separation_frames: int = 2
    min_shot_duration_frames: int = 6
    # Real-video finding: a single "total window duration" cap measured
    # from the start of LOAD conflates two physically unrelated things --
    # how long a shooter dwells before releasing (which can legitimately
    # run several seconds: aiming, a hold, a pump fake) and how long the
    # ball is actually in the air after release (which cannot -- a real
    # shot's flight is well under ~2s). A real video's shooter held the
    # ball for ~4.8s before releasing, which nearly exhausted a single
    # shared 150-frame/~5s budget, so the window was force-closed only
    # ~7 frames after the genuine release -- while the ball was still
    # unambiguously airborne -- and the remaining flight was then
    # re-detected as a spurious second shot. These are now two
    # independent budgets, each measured from its own natural anchor
    # (LOAD start / RELEASE), so a long hold never eats into the flight
    # budget and vice versa.
    max_pre_release_duration_frames: int = 300
    max_flight_duration_frames: int = 150
    min_frames_between_shots: int = 10
    reset_stationary_frames: int = 5
    # A ball that goes completely undetected (not merely far from the
    # hand) for a while is NOT itself evidence the shot ended -- see
    # shot_state_machine.py's FLIGHT-phase handling -- but an unresolved
    # total blackout still has to close out eventually. This bounds that
    # wait to roughly how long a real shot's flight can physically take
    # (release to rim is well under ~1.5-2s for a realistic shot), which
    # is much shorter than max_flight_duration_frames' full safety cap, so a
    # long tracking blackout doesn't run the window into the next shot.
    reset_unavailable_frames: int = 45
    # After a shot window is force-closed for a reason that does NOT
    # positively confirm the ball's motion actually concluded (the flight
    # duration cap above, or a prolonged tracking blackout -- as opposed to
    # a CONFIRMED settle back near the hand, which is real evidence the
    # shot is over), the ball may well still be the same one continuing its
    # flight. Suppress the FALLBACK trigger specifically (never the primary,
    # ball-hand-proximity trigger -- a genuinely fast rebound-catch-shoot
    # has real evidence of its own new catch and must not be blocked) for
    # this many frames afterward, so an immediately-continuing upward-flight
    # signal is not mistaken for a brand new release. Deliberately NOT a
    # long fixed cooldown on all shot detection -- only the specific,
    # evidence-free trigger path that caused the real duplicate.
    post_flight_ownership_frames: int = 90

    # Fallback trigger: on real footage the ball is frequently undetected
    # while held (small, occluded by fingers/hand) even though its FLIGHT
    # away from the shooter is usually well detected (larger, unoccluded,
    # high contrast). Requiring continuous ball-hand tracking to ever
    # enter LOAD meant a real session with imperfect held-ball detection
    # produced zero detected shots even though every shot's release/flight
    # was directly observed. This fallback recognizes a sustained, confirmed
    # upward ball flight as a release-in-progress even without a directly
    # observed preceding LOAD phase, and infers the load window from the
    # pose-only knee-angle trace just before it (see shot_state_machine.py).
    fallback_trigger_frames: int = 3
    load_lookback_max_frames: int = 45
    # A jump shot is taken from an essentially stationary base -- a real
    # video's false positive turned out to be a different player DRIBBLING
    # WHILE WALKING, whose natural gait produced a real (not noise), if
    # incidental, knee-flexion dip large enough to pass the check above.
    # What actually distinguished it was gross horizontal translation: the
    # walker's hips crossed nearly the full frame width during the
    # window, versus a fraction of one torso-length for every genuine
    # shot checked. Expressed in torso-lengths (not raw pixels) so it
    # holds regardless of camera distance/zoom.
    max_load_hip_translation_norm: float = 4.0


@dataclass(frozen=True)
class ReleaseConfig:
    search_window_frames: int = 8
    hand_ball_distance_norm_threshold: float = 0.22
    min_upward_velocity_norm: float = 0.15
    confidence_window_frames: int = 2


@dataclass(frozen=True)
class ReleaseEventConfig:
    """
    Ball-centric release-EVENT detector (migration-plan Phase 1, see
    app/events/release_event_detector.py): evaluates every frame
    independently for a genuine release, using ball vertical velocity as
    the PRIMARY signal and wrist separation as a corroborating veto/
    extension -- the inverse emphasis from the existing shot_state_machine
    (which gates LOAD entry on pose -- hand proximity + knee flexion --
    first, and only confirms with ball velocity). Modeled on a reference
    basketball-shot-tracking project's state machine (inspected at the
    source level, not just its marketing description), adapted to this
    pipeline's existing normalized (torso-length-relative) unit system
    rather than that project's rim-depth-calibrated m/s: this pipeline's
    OWN rim_calibration.py already documents, for an independent and
    unrelated reason, that a rim-diameter-derived pixels-per-meter ratio is
    only valid for objects at the rim's own depth from the camera -- a
    single-camera, uncalibrated setup cannot extend it to the shooter's
    release point (a different depth) without silently mixing in
    unaccounted-for perspective error. Applying that same calibration to
    a release-velocity threshold, as the reference project does, would
    violate a boundary this codebase already treats as load-bearing
    elsewhere, so normalized units are used here instead.

    Runs in SHADOW MODE ONLY at this stage: an isolated, independently
    testable module that does not feed the production shot_state_machine
    or any pipeline output. See docs/METHODOLOGY.md or the migration report
    for the full comparison and the reasoning behind each threshold below.
    """
    # A release must show qualifying upward velocity for this many
    # CONSECUTIVE observed frames before it counts -- not a single frame
    # crossing a threshold, which a single hard dribble bounce can do just
    # as easily as a real launch. Matches the reference project's own
    # release_consecutive_frames=3 (a small, physically-motivated frame
    # count, not a tuned float).
    consecutive_frames: int = 3
    # PRIMARY ("strong") path: qualifies on velocity alone, regardless of
    # pose. Set equal to the existing FSM's upward_velocity_threshold_norm
    # (0.35 torso-lengths/sec) -- an already-independently-validated
    # constant from the Video 1/2 real-footage work, not a new number
    # invented for this module, and specifically NOT reverse-engineered
    # from Video 3.
    strong_upward_velocity_norm: float = 0.35
    # SOFT path: available only when the ball is genuinely separated from
    # AND above BOTH wrists (never available for an in-hand or
    # below-the-hands rise, which is what keeps this from reopening the
    # pump-fake/dribble hole) -- extends arming down to a lower floor for
    # a slow, soft-arc release. Derived from strong_upward_velocity_norm
    # scaled by the reference project's own documented strong:soft ratio
    # (2.0 m/s : 1.2 m/s = 1.667), not an independently chosen constant.
    soft_upward_velocity_norm: float = 0.21
    # Wrist-separation threshold for the veto/soft-path check. Set equal
    # to the existing FSM's hand_proximity_threshold_norm (0.18
    # torso-lengths) for the same reason as strong_upward_velocity_norm
    # above -- reuse an already-validated constant rather than invent one.
    separation_threshold_norm: float = 0.18
    # A wrist keypoint confidently glued to a fast-rising ball (separated
    # is False) vetoes arming -- but only for this many consecutive
    # strong-qualifying frames, so a stuck/misassociated keypoint can never
    # permanently suppress a real release. Matches the reference project's
    # release_separation_veto_frames=8.
    veto_override_frames: int = 8

    # ---- CONTROLLED-state precondition (diagnostic follow-up: a hard
    # dribble bounce satisfies velocity + wrist-separation just as well as
    # a genuine release, because separation alone doesn't prove the ascent
    # originated from the shooting hand -- a bounce's "separation" is just
    # "the ball was never near a hand in the first place"). Frame-by-frame
    # inspection of three genuine releases (two videos) and one hard
    # dribble found the discriminator: every genuine release was preceded
    # by a sustained span of the ball at low ball-wrist distance AND low
    # ball/wrist relative velocity (the ball being carried, not yet
    # released); the dribble showed neither, anywhere in its window --
    # the bounce originates at the floor, nowhere near a hand. A
    # qualifying streak may now only BEGIN at a frame with such a state
    # somewhere in its recent history.
    #
    # Proximity threshold: reuses separation_threshold_norm (0.18) --
    # the same already-validated constant used for the veto, not a new
    # number.
    #
    # Relative-velocity threshold: NEW. Set to half of
    # strong_upward_velocity_norm (0.35 -> 0.175) -- during genuine
    # control the ball must be moving with the wrist at well under
    # release speed, and half the release floor is a principled,
    # derived-not-invented way to express "clearly not yet separating"
    # without introducing an independent tuned constant.
    controlled_max_relative_velocity_norm: float = 0.175
    # Lookback window for "was there a controlled state recently":
    # REUSES ShotDetectionConfig.load_lookback_max_frames (45, ~1.5s at
    # 30fps) -- the existing FSM's own already-validated bound for "how
    # far back a genuine pre-release load can be found" -- rather than
    # inventing a second, competing constant for the same physical idea.
    # (Read directly from CONFIG.shot at call time, not duplicated here.)

    # ---- Trusted-observation continuity (diagnostic follow-up: a single
    # spurious DETECTED point mid-ascent corrupted one genuine release's
    # streak, since the original filter never rejected DETECTED points at
    # all; separately, correctly-rejected phantom-interpolated frames
    # between two real detections hard-reset the streak on raw frame-index
    # adjacency, fragmenting two other genuine releases that had dense,
    # clean, real evidence just a couple of frames apart). Two changes:
    # DETECTED points are now also subject to the same two-sided
    # (previous-and-next real-detection) consistency check interpolated
    # points already used -- continuity, never a confidence cutoff, so a
    # genuinely difficult but consistent low-confidence detection is never
    # penalized. And the streak is now defined over consecutive TRUSTED
    # observations tolerant of a short, bounded gap of rejected/absent
    # frames between them, rather than consecutive raw frame indices.
    #
    # NEW. ~4-5 frames at a typical ~30fps analysis rate -- long enough to
    # bridge the 1-3-frame phantom-interpolation gaps observed on real
    # footage between two genuine detections, nowhere near long enough to
    # bridge an actual tracking blackout or connect two physically
    # unrelated pieces of motion (the outcome detector's own analogous
    # occlusion-tolerance reasoning uses a similar small-multiple-of-a-
    # frame-period argument, just for a different signal).
    max_gap_seconds_within_streak: float = 0.15


@dataclass(frozen=True)
class OutcomeConfig:
    # Ball must be observed above the rim line and then below it, within a
    # horizontal band around the rim, with a downward-crossing direction.
    # This "tight band" is what a MADE determination requires.
    horizontal_margin_frac_of_rim_radius: float = 1.6
    min_points_above: int = 2
    min_points_below: int = 2
    # Time (not raw frame count) allowed between the last above-rim point
    # and the first below-rim point of a candidate crossing. Real footage
    # can legitimately drop several consecutive frames right at the rim --
    # partial occlusion by the rim/net during a genuine pass-through, or an
    # unrelated false-positive detection interleaving with the real ball
    # track for a few frames -- so bounding this in frame-index units
    # penalizes exactly the moment a made shot is hardest to track cleanly.
    # 0.75s is generous relative to observed rim-entry speeds (~2-4 m/s,
    # i.e. well under 0.3s to cross the rim's own vertical span even with
    # some occlusion), while still ruling out a "crossing" built from two
    # points separated by a second or more of unrelated later motion.
    max_seconds_through_rim: float = 0.75
    # How far the ball may drift horizontally between the above-rim and
    # below-rim crossing points and still count as a genuine pass-through,
    # expressed as a fraction of the rim's own radius (i.e. the physical
    # scale of the opening itself) rather than the much more permissive
    # tight/wide interaction bands. A ball that drifts more than about one
    # rim-radius sideways while falling through a rim-radius-wide opening
    # did not fall straight through it -- it crossed the same generous
    # horizontal tolerance zone at an angle, which is the signature of a
    # rim/backboard deflection, not a clean make.
    max_crossing_drift_frac_of_rim_radius: float = 1.0
    # A single static camera cannot observe depth: a ball that sails past
    # the rim in front of or behind its actual plane (never touching iron)
    # projects to the same small-drift, gravity-smooth 2D crossing as a
    # clean swish. The one depth proxy available from a plain bbox
    # detector is occlusion -- a ball genuinely passing THROUGH the rim
    # opening is partially obscured by the front rim/net from the camera's
    # view, so its detection confidence should dip during the crossing;
    # a ball passing cleanly in front of the rim plane, fully unobstructed,
    # should not show that dip. Diagnosed on real footage: four confirmed
    # makes all showed confidence dropping to 36-73% of the crossing's
    # bracketing confidence, while two false-positive "makes" (confirmed
    # misses whose 2D trajectory nonetheless looked like a clean
    # pass-through) never dropped below 77%. A crossing without this dip
    # is treated as insufficient MADE evidence -- not converted into a
    # MISS call, since absence of an occlusion cue is not positive
    # evidence of a miss, just absence of support for a make.
    min_occlusion_dip_frac: float = 0.75
    # Time bound for MISS "approached then deflected away" evidence: the
    # deflection point must occur shortly after the approach, not at an
    # arbitrary later point in the trajectory (e.g. the ball already on
    # the ground and rolling/bouncing well after any real rim interaction).
    max_seconds_deflection_after_approach: float = 0.75
    # Same "don't use stale, physically-disconnected evidence" principle,
    # applied to the beside-the-hoop and clear-airball MISS cases: a point
    # found long after the apex is more likely a later, unrelated event
    # within the same (possibly extended) shot window -- a rebound,
    # retrieval, or bounce -- than genuine evidence about where THIS shot
    # went. 2s is generous relative to a normal apex-to-landing descent
    # (typically well under 1s on the real footage this was diagnosed
    # against) while still ruling out multi-second-later motion.
    max_seconds_from_apex_for_descent_evidence: float = 2.0
    min_outcome_confidence_to_report: float = 0.45

    # A looser "wide zone" used only for MISS evidence (approached the rim
    # then deflected away, or passed beside it) -- deliberately more
    # generous than the tight band, since a near-miss still needs to count
    # as "got close" without requiring the same precision a MADE call does.
    wide_zone_frac_of_rim_radius: float = 3.0
    # Vertical tolerance (as a fraction of rim radius) for "at rim height",
    # used to detect a trajectory passing beside the hoop at the relevant
    # height without ever entering the horizontal zone.
    near_rim_height_frac_of_rim_radius: float = 2.5

    # Minimum reliable (DETECTED/INTERPOLATED, never PREDICTED-only) points
    # required anywhere in the trajectory before attempting to reason
    # about outcome at all.
    min_reliable_points_to_attempt: int = 3
    # If the trajectory's apex is one of its own endpoints (i.e. we may
    # have missed the true highest point because the track starts already
    # descending or ends still ascending), require at least this many
    # reliable points total before trusting the ascent/descent split anyway.
    min_reliable_points_when_apex_unconfirmed: int = 6
    # Minimum reliable points specifically in the post-apex (descent)
    # portion of the trajectory -- this is where rim interaction has to be
    # observed, so a trajectory with plenty of ascent data but almost no
    # descent data still can't support a MADE/MISSED call.
    min_descent_points_to_attempt: int = 3
    # Below this hoop-location confidence, don't attempt outcome at all.
    min_hoop_confidence_to_attempt: float = 0.3

    # Trajectory-smoothness outlier rejection (see
    # outcome_detector._reject_trajectory_outliers): a point is dropped if
    # its deviation from a straight line between its neighbors exceeds
    # this fraction of that segment's own length, OR this many ball radii
    # -- whichever tolerance is larger. Diagnosed on a real video: a
    # tracking-hijack artifact deviated by ~194% of its local segment
    # length within ~100ms, far beyond normal parabolic curvature over
    # such a short gap.
    trajectory_outlier_span_frac: float = 0.6
    trajectory_outlier_min_radii: float = 3.0


@dataclass(frozen=True)
class AnalyticsConfig:
    min_shots_for_makes_vs_misses: int = 4
    min_makes_for_comparison: int = 2
    min_misses_for_comparison: int = 2
    min_shots_for_trend_analysis: int = 6
    trend_split_thirds: bool = True
    effect_size_small: float = 0.2
    effect_size_medium: float = 0.5
    effect_size_large: float = 0.8


@dataclass(frozen=True)
class AppConfig:
    video: VideoConfig = field(default_factory=VideoConfig)
    person: PersonDetectorConfig = field(default_factory=PersonDetectorConfig)
    pose: PoseConfig = field(default_factory=PoseConfig)
    ball: BallDetectorConfig = field(default_factory=BallDetectorConfig)
    hoop: HoopDetectorConfig = field(default_factory=HoopDetectorConfig)
    ball_rim_rfdetr: BallRimDetectorConfig = field(default_factory=BallRimDetectorConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    shot: ShotDetectionConfig = field(default_factory=ShotDetectionConfig)
    release: ReleaseConfig = field(default_factory=ReleaseConfig)
    release_event: ReleaseEventConfig = field(default_factory=ReleaseEventConfig)
    outcome: OutcomeConfig = field(default_factory=OutcomeConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)


CONFIG = AppConfig()
