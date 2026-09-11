"""
Ties the whole pipeline together for a single uploaded video: frame
reading -> detection -> tracking -> shot segmentation -> release -> outcome
-> biomechanics -> session analytics. This is the only module that knows
about the full sequence of stages; every stage it calls is independently
testable and replaceable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.analytics.coaching import build_coaching_summary
from app.analytics.consistency import compute_consistency
from app.analytics.feedback import Finding, generate_makes_vs_misses_findings, generate_trend_findings
from app.analytics.makes_vs_misses import compute_makes_vs_misses
from app.analytics.session_summary import compute_session_summary
from app.analytics.shot_record import ShotRecord, build_shot_record
from app.analytics.trends import compute_trends
from app.biomechanics.geometry import distance, midpoint, torso_length
from app.biomechanics.metrics import compute_shot_mechanics, torso_points
from app.biomechanics.shooting_side import determine_shooting_side
from app.config import CONFIG, MODELS_DIR
from app.events.outcome_detector import detect_outcome
from app.events.release_detector import estimate_release
from app.events.shot_state_machine import FrameSignals, detect_shots
from app.logging_config import get_logger
from app.pipeline.video_io import FrameReader, VideoMeta, validate_video
from app.tracking.ball_tracker import BallTracker
from app.tracking.hoop_aggregator import aggregate_hoop_candidates
from app.vision.detection.ball_detector import validate_ball_candidates
from app.vision.detection.ball_detector_learned import LearnedBallDetector
from app.vision.detection.ball_rim_detector_rfdetr import RFDETRBallRimDetector
from app.vision.detection.hoop_detector import detect_hoop_candidates
from app.vision.detection.hoop_detector_learned import LearnedHoopDetector
from app.vision.detection.near_hoop_enrichment import enrich_near_hoop
from app.vision.detection.person_selector import PrimaryShooterSelector
from app.vision.detection.yolo_detector import YoloMultiDetector
from app.vision.pose.pose_estimator import PoseEstimator
from app.vision.types import BallObservation, DataSource, HoopLocation, PoseFrame

log = get_logger("pipeline.orchestrator")

ProgressCallback = Callable[[str, float], None]


@dataclass
class SessionResult:
    video_meta: VideoMeta
    shots: List[ShotRecord]
    hoop: Optional[HoopLocation]
    session_summary: object
    consistency: list
    makes_vs_misses: object
    trends: object
    findings: List[Finding]
    coaching: object = None
    warnings: List[str] = field(default_factory=list)
    pose_frames: List[PoseFrame] = field(default_factory=list)
    ball_observations: List[BallObservation] = field(default_factory=list)
    analysis_fps: float = 0.0
    analysis_size: tuple = (0, 0)


def _noop_progress(stage: str, pct: float) -> None:
    pass


def _lm_px(pf: PoseFrame, name: str, w: int, h: int):
    lm = pf.landmark(name)
    if lm is None:
        return None
    return (lm.x * w, lm.y * h)


def _nearest_wrist_distance_px(pf: PoseFrame, ball_xy, w: int, h: int) -> Optional[float]:
    if not pf.detected or ball_xy is None:
        return None
    dists = []
    for side in ("left", "right"):
        wp = _lm_px(pf, f"{side}_wrist", w, h)
        if wp is not None:
            dists.append(distance(wp, ball_xy))
    return min(dists) if dists else None


def _mean_knee_angle(pf: PoseFrame) -> Optional[float]:
    from app.biomechanics.geometry import knee_angle
    angles = []
    for side in ("left", "right"):
        hip, knee, ankle = pf.landmark(f"{side}_hip"), pf.landmark(f"{side}_knee"), pf.landmark(f"{side}_ankle")
        if hip and knee and ankle and min(hip.visibility, knee.visibility, ankle.visibility) >= 0.4:
            a = knee_angle((hip.x, hip.y), (knee.x, knee.y), (ankle.x, ankle.y))
            # Landmark visibility passing its own threshold does not
            # guarantee a physically plausible joint configuration -- a
            # real video showed occasional single-frame ~50-80 degree
            # readings during a person-overlap moment that were almost
            # certainly pose-estimation noise, not a real squat-depth
            # bend, and that noise was enough to feed a spurious "genuine
            # load" signal into shot detection. Drop implausible readings
            # rather than trust them.
            if a is not None and a >= CONFIG.pose.min_plausible_knee_angle_deg:
                angles.append(a)
    return sum(angles) / len(angles) if angles else None


def _mean_shoulder_y_px(pf: PoseFrame, h: int) -> Optional[float]:
    ls, rs = pf.landmark("left_shoulder"), pf.landmark("right_shoulder")
    if ls and rs:
        return ((ls.y + rs.y) / 2.0) * h
    return None


def _mean_hip_x_px(pf: PoseFrame, w: int) -> Optional[float]:
    lh, rh = pf.landmark("left_hip"), pf.landmark("right_hip")
    if lh and rh:
        return ((lh.x + rh.x) / 2.0) * w
    return None


def _estimate_global_torso_scale_px(pose_frames: List[PoseFrame], w: int, h: int) -> float:
    lengths = []
    for pf in pose_frames:
        if not pf.detected:
            continue
        shoulder_pts = [_lm_px(pf, "left_shoulder", w, h), _lm_px(pf, "right_shoulder", w, h)]
        hip_pts = [_lm_px(pf, "left_hip", w, h), _lm_px(pf, "right_hip", w, h)]
        shoulder_pts = [p for p in shoulder_pts if p is not None]
        hip_pts = [p for p in hip_pts if p is not None]
        if shoulder_pts and hip_pts:
            sm = midpoint(shoulder_pts[0], shoulder_pts[-1]) if len(shoulder_pts) == 2 else shoulder_pts[0]
            hm = midpoint(hip_pts[0], hip_pts[-1]) if len(hip_pts) == 2 else hip_pts[0]
            lengths.append(torso_length(sm, hm))
    if not lengths:
        return max(h * 0.22, 1.0)  # rough fallback: torso ~ a fifth of frame height
    lengths.sort()
    return lengths[len(lengths) // 2]  # median, robust to outlier frames


def build_frame_signals(frames_list, pose_frames: List[PoseFrame], ball_observations: List[BallObservation],
                          w: int, h: int) -> List[FrameSignals]:
    """
    Turns raw per-frame pose + ball-tracking output into the normalized
    signal sequence the shot state machine consumes (ball-hand distance,
    vertical velocity, knee angle, shoulder height -- all body-relative).
    Kept as a standalone function (rather than inline in run_pipeline) so
    a diagnostic script can reconstruct the EXACT same signals a real
    pipeline run used, instead of a parallel implementation that could
    subtly diverge from what actually ran.
    """
    global_torso_px = _estimate_global_torso_scale_px(pose_frames, w, h)
    ball_by_frame = {o.frame_index: o for o in ball_observations}
    pose_by_frame = {p.frame_index: p for p in pose_frames}

    frame_signals: List[FrameSignals] = []
    prev_ball = None
    for af in frames_list:
        obs = ball_by_frame[af.frame_index]
        pf = pose_by_frame[af.frame_index]
        ball_available = obs.source != DataSource.UNAVAILABLE
        ball_xy = (obs.center_x, obs.center_y) if ball_available else None

        hand_dist_norm = None
        vvel_norm = None
        shoulder_y_px = None
        if ball_available:
            hd_px = _nearest_wrist_distance_px(pf, ball_xy, w, h)
            if hd_px is not None:
                hand_dist_norm = hd_px / global_torso_px
            if prev_ball is not None and prev_ball[0] is not None:
                dt = af.timestamp_sec - prev_ball[1]
                if dt > 1e-6:
                    vvel_px = (obs.center_y - prev_ball[0][1]) / dt
                    vvel_norm = vvel_px / global_torso_px  # torso-lengths per second
            shoulder_y_px = _mean_shoulder_y_px(pf, h)

        hip_x_norm = None
        if pf.detected:
            hip_x_px = _mean_hip_x_px(pf, w)
            if hip_x_px is not None:
                hip_x_norm = hip_x_px / global_torso_px

        left_wrist_xy = _lm_px(pf, "left_wrist", w, h) if pf.detected else None
        right_wrist_xy = _lm_px(pf, "right_wrist", w, h) if pf.detected else None

        frame_signals.append(FrameSignals(
            frame_index=af.frame_index, timestamp_sec=af.timestamp_sec,
            ball_available=ball_available,
            ball_x=obs.center_x if ball_available else None,
            ball_y=obs.center_y if ball_available else None,
            ball_hand_dist_norm=hand_dist_norm,
            ball_vertical_velocity_norm=vvel_norm,
            knee_angle_deg=_mean_knee_angle(pf) if pf.detected else None,
            shoulder_y=shoulder_y_px,
            pose_confidence=pf.pose_confidence,
            ball_is_observed=obs.source in (DataSource.DETECTED, DataSource.INTERPOLATED),
            hip_x_norm=hip_x_norm,
            left_wrist_xy=left_wrist_xy,
            right_wrist_xy=right_wrist_xy,
            ball_source=obs.source,
        ))
        prev_ball = ((obs.center_x, obs.center_y) if ball_available else None, af.timestamp_sec)

    return frame_signals


def build_shot_from_window(window, frame_signals: List[FrameSignals], pose_frames: List[PoseFrame],
                            ball_observations: List[BallObservation], hoop: Optional[HoopLocation],
                            w: int, h: int, enriched_flight_points: Optional[List[BallObservation]] = None
                            ) -> ShotRecord:
    """
    Turns one detected shot window into a fully-populated ShotRecord:
    shooting-side detection, release refinement, biomechanics, outcome,
    and trajectory quality. Kept as a standalone function (rather than
    inline in run_pipeline's loop) so it can be exercised directly in
    tests with synthetic pose/ball data, without needing an actual video
    or the detection models.
    """
    from app.biomechanics.geometry import elbow_angle as _elbow_angle_fn

    pose_by_frame = {p.frame_index: p for p in pose_frames}
    ball_by_frame = {o.frame_index: o for o in ball_observations}
    ball_positions_by_frame = {
        o.frame_index: (o.center_x, o.center_y) for o in ball_observations
        if o.source != DataSource.UNAVAILABLE
    }

    shooting_side = determine_shooting_side(pose_frames, ball_positions_by_frame,
                                               window.start_frame, window.end_frame)

    elbow_angles: Dict[int, float] = {}
    if shooting_side:
        for pf in pose_frames:
            if not (window.start_frame <= pf.frame_index <= window.end_frame) or not pf.detected:
                continue
            shoulder = pf.landmark(f"{shooting_side}_shoulder")
            elbow = pf.landmark(f"{shooting_side}_elbow")
            wrist = pf.landmark(f"{shooting_side}_wrist")
            if shoulder and elbow and wrist:
                a = _elbow_angle_fn((shoulder.x, shoulder.y), (elbow.x, elbow.y), (wrist.x, wrist.y))
                if a is not None:
                    elbow_angles[pf.frame_index] = a

    release = estimate_release(window, frame_signals, elbow_angles)
    release_frame = release.release_frame if release else window.release_candidate_frame

    mechanics = compute_shot_mechanics(pose_frames, shooting_side, window.load_start_frame,
                                         window.upward_start_frame, release_frame)

    flight_start = release_frame if release_frame is not None else window.upward_start_frame or window.start_frame
    if enriched_flight_points is not None:
        # Near-hoop-enriched trajectory (see near_hoop_enrichment.py) --
        # denser evidence specifically around the rim, used ONLY for
        # outcome detection. Shot segmentation, biomechanics, and
        # ball_track_quality below all still use the original,
        # un-enriched global trajectory, unaffected by this. No upper
        # clamp to window.end_frame here: enrich_near_hoop() already
        # deliberately re-reads up to ~0.5s past a forced-early window
        # close (bounded by the next shot's own start, see its own
        # margin_sec/ranges logic), specifically to recover rim-adjacent
        # evidence a truncated window would otherwise cut off. Reclamping
        # here silently discarded exactly that recovered evidence.
        flight_points = [o for o in enriched_flight_points if o.frame_index >= flight_start]
    else:
        flight_points = [o for o in ball_observations if flight_start <= o.frame_index <= window.end_frame]
    outcome = detect_outcome(flight_points, hoop)

    shot_ball_points = [o for o in ball_observations if window.start_frame <= o.frame_index <= window.end_frame]
    reliable = [o for o in shot_ball_points if o.source in (DataSource.DETECTED, DataSource.INTERPOLATED)]
    ball_track_quality = len(reliable) / len(shot_ball_points) if shot_ball_points else 0.0

    release_pf = pose_by_frame.get(release_frame) if release_frame is not None else None
    torso_px_at_release = None
    if release_pf and release_pf.detected:
        # Canonical torso reference (app.biomechanics.metrics.torso_points):
        # bilateral (both shoulders, both hips averaged) and abstains
        # (returns None) below the same visibility floor
        # compute_shot_mechanics already uses for release_height_norm --
        # not a single, visibility-unchecked side, which apex_height_norm
        # used to compute independently and could blow up on one noisy
        # landmark. torso_points() returns normalized (0-1) coordinates;
        # converted to pixels here since apex_px below is pixel-based.
        torso_pts = torso_points(release_pf)
        if torso_pts:
            shoulder_mid_norm, hip_mid_norm = torso_pts
            shoulder_px = (shoulder_mid_norm[0] * w, shoulder_mid_norm[1] * h)
            hip_px = (hip_mid_norm[0] * w, hip_mid_norm[1] * h)
            torso_px_at_release = torso_length(shoulder_px, hip_px)

    release_ball_point = ball_by_frame.get(release_frame) if release_frame is not None else None

    start_time = next((fs.timestamp_sec for fs in frame_signals if fs.frame_index == window.start_frame),
                        frame_signals[0].timestamp_sec)
    end_time = next((fs.timestamp_sec for fs in frame_signals if fs.frame_index == window.end_frame), start_time)

    return build_shot_record(
        shot_index=window.shot_index, window=window, release=release, outcome=outcome,
        mechanics=mechanics, shooting_side=shooting_side, ball_track_quality=ball_track_quality,
        hoop_confidence=hoop.confidence if hoop else 0.0, flight_points=flight_points,
        release_ball_point=release_ball_point, torso_length_px_at_release=torso_px_at_release,
        start_time_sec=start_time, end_time_sec=end_time,
    )


def run_pipeline(video_path: Path, progress_cb: Optional[ProgressCallback] = None) -> SessionResult:
    progress_cb = progress_cb or _noop_progress
    warnings: List[str] = []

    progress_cb("validating_video", 0.02)
    meta = validate_video(video_path)

    reader = FrameReader(meta)
    w, h = reader.analysis_width, reader.analysis_height
    log.info("Analyzing '%s' at %dx%d, %.1f analysis fps (source %dx%d @ %.1ffps, %d frames)",
              video_path.name, w, h, reader.effective_fps, meta.width, meta.height, meta.fps, meta.frame_count)

    detector = YoloMultiDetector.get()  # still needed for "person" (shooter) detection regardless
    detector.warmup()

    rf_ball_rim_detector = None
    rfdetr_checkpoint = MODELS_DIR / CONFIG.ball_rim_rfdetr.checkpoint_name
    if CONFIG.ball_rim_rfdetr.enabled and rfdetr_checkpoint.exists():
        rf_ball_rim_detector = RFDETRBallRimDetector(str(rfdetr_checkpoint), CONFIG.ball_rim_rfdetr.confidence_floor)
        rf_ball_rim_detector.warmup()
        log.info("Using fine-tuned RF-DETR ball/rim detector as the primary vision source.")
    else:
        if CONFIG.ball_rim_rfdetr.enabled:
            log.warning("RF-DETR ball/rim checkpoint not found at %s; falling back to the generic "
                         "YOLOv8/YOLO-World/classical-CV detector stack.", rfdetr_checkpoint)
            warnings.append("The fine-tuned basketball/rim detector was unavailable for this session; "
                              "fell back to the generic detector stack, which has lower recall near the hoop.")

    learned_hoop_detector = None
    learned_ball_detector = None
    if rf_ball_rim_detector is None:
        if CONFIG.hoop.use_learned_detector:
            learned_hoop_detector = LearnedHoopDetector.get()
            learned_hoop_detector.warmup()
        if CONFIG.ball.use_learned_detector:
            learned_ball_detector = LearnedBallDetector.get()
            learned_ball_detector.warmup()
    pose_estimator = PoseEstimator()
    shooter_selector = PrimaryShooterSelector(min_track_frames=CONFIG.person.min_track_frames_for_primary)
    ball_tracker = BallTracker()

    pose_frames: List[PoseFrame] = []
    ball_observations: List[BallObservation] = []
    hoop_candidates = []

    frames_list = list(reader)
    total = len(frames_list)
    if total == 0:
        raise ValueError("No analyzable frames were extracted from this video.")

    hoop_sample_stride = max(1, total // CONFIG.hoop.sample_frame_count)

    for i, af in enumerate(frames_list):
        progress_cb("analyzing_player_and_ball", 0.05 + 0.55 * (i / total))
        dets = detector.detect(af.image, af.frame_index, af.timestamp_sec)

        primary_person = shooter_selector.select(dets["person"])
        if primary_person is not None:
            pf = pose_estimator.process_crop(af.image, (primary_person.x1, primary_person.y1,
                                                          primary_person.x2, primary_person.y2),
                                               af.frame_index, af.timestamp_sec)
        else:
            pf = PoseFrame(af.frame_index, af.timestamp_sec, detected=False)
        pose_frames.append(pf)

        if rf_ball_rim_detector is not None:
            rf_raw = rf_ball_rim_detector.predict_raw(af.image)
            validated_balls = rf_ball_rim_detector.extract_ball_detections(rf_raw, af.frame_index, af.timestamp_sec)
        else:
            validated_balls = validate_ball_candidates(af.image, dets["ball_candidate"])
            if learned_ball_detector is not None:
                validated_balls = validated_balls + learned_ball_detector.detect(
                    af.image, af.frame_index, af.timestamp_sec
                )
        obs = ball_tracker.step(af.frame_index, af.timestamp_sec, validated_balls)
        ball_observations.append(obs)

        if i % hoop_sample_stride == 0:
            if rf_ball_rim_detector is not None:
                hoop_candidates.extend(
                    (af.frame_index, x, y, r, conf, "rfdetr")
                    for (x, y, r, conf) in rf_ball_rim_detector.extract_rim_candidates(rf_raw)
                )
            else:
                hoop_candidates.extend(
                    (af.frame_index, x, y, r, conf, "classical")
                    for (x, y, r, conf) in detect_hoop_candidates(af.image)
                )
                if learned_hoop_detector is not None:
                    hoop_candidates.extend(
                        (af.frame_index, x, y, r, conf, "learned")
                        for (x, y, r, conf) in learned_hoop_detector.detect(af.image)
                    )

    progress_cb("locating_hoop", 0.62)
    hoop = aggregate_hoop_candidates(hoop_candidates)
    if hoop is None:
        warnings.append("Hoop could not be located automatically. Shooting mechanics were analyzed, "
                          "but makes/misses are unavailable for this session.")
    elif hoop.confidence < CONFIG.hoop.min_confidence_to_auto_accept:
        warnings.append("Hoop location confidence was low; make/miss detection may be unreliable this session.")

    progress_cb("detecting_shots", 0.68)
    frame_signals = build_frame_signals(frames_list, pose_frames, ball_observations, w, h)
    windows = detect_shots(frame_signals)
    log.info("Detected %d candidate shot attempt(s)", len(windows))

    progress_cb("locating_ball_near_hoop", 0.72)
    enriched_by_shot: Dict[int, List[BallObservation]] = {}
    # This pass exists to recover near-hoop ball evidence the GLOBAL
    # detector otherwise misses -- with RF-DETR as the primary source that
    # gap is already closed directly (benchmarked near-rim coverage went
    # from ~0% to ~90%+, see BallRimDetectorConfig), so re-reading and
    # re-running a secondary ROI detector over each shot's flight window
    # would be redundant compute chasing a problem that no longer exists.
    if windows and rf_ball_rim_detector is None:
        try:
            enriched_by_shot = enrich_near_hoop(video_path, meta, windows, ball_observations, hoop, w, h)
        except Exception:
            log.exception("Near-hoop ball enrichment failed; outcome detection will use the un-enriched trajectory.")
            enriched_by_shot = {}

    progress_cb("analyzing_mechanics", 0.75)
    shots: List[ShotRecord] = [
        build_shot_from_window(window, frame_signals, pose_frames, ball_observations, hoop, w, h,
                                 enriched_flight_points=enriched_by_shot.get(window.shot_index))
        for window in windows
    ]

    progress_cb("comparing_attempts", 0.88)
    consistency = compute_consistency(shots)
    mvm = compute_makes_vs_misses(shots)
    trends = compute_trends(shots)
    summary = compute_session_summary(shots, consistency, mvm)

    findings = generate_makes_vs_misses_findings(mvm) + generate_trend_findings(trends)
    warnings.extend(summary.warnings)

    # Presentation-layer synthesis only -- reads the already-computed
    # consistency/makes-vs-misses/session-summary results above and
    # decides which are strong enough to present as coaching. Computes no
    # new measurement of its own; see app/analytics/coaching.py.
    coaching = build_coaching_summary(shots, summary, consistency, mvm)

    pose_estimator.close()
    progress_cb("finalizing", 0.95)

    return SessionResult(
        video_meta=meta, shots=shots, hoop=hoop, session_summary=summary,
        consistency=consistency, makes_vs_misses=mvm, trends=trends, findings=findings,
        coaching=coaching,
        warnings=warnings, pose_frames=pose_frames, ball_observations=ball_observations,
        analysis_fps=reader.effective_fps, analysis_size=(w, h),
    )
