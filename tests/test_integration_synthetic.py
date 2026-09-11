"""
End-to-end integration test of everything downstream of detection: given
synthetic pose/ball/hoop data (no real video, no ML models), verify that
shot segmentation, release estimation, biomechanics, outcome detection,
and session analytics all compose correctly -- multiple shots are kept
distinct, outcomes/metrics attach to the right shot, and analytics/
feedback only use real computed values.
"""
from dataclasses import replace

from app.analytics.consistency import compute_consistency
from app.analytics.feedback import generate_makes_vs_misses_findings
from app.analytics.makes_vs_misses import compute_makes_vs_misses
from app.analytics.session_summary import compute_session_summary
from app.events.outcome_detector import ShotOutcome
from app.events.shot_state_machine import FrameSignals, detect_shots
from app.pipeline.orchestrator import build_shot_from_window
from app.vision.types import BallObservation, DataSource, HoopLocation, Landmark, PoseFrame

W, H = 640, 360
FPS = 30.0
HOOP = HoopLocation(rim_center_x=500.0, rim_center_y=80.0, rim_radius_px=18.0,
                     confidence=0.75, votes=8, method="hough_color")


def _pose_frame(i, wrist_xy_norm, knee_y_norm, shoulder_y_norm=0.35, hip_y_norm=0.55,
                 elbow_y_norm=None):
    elbow_y_norm = elbow_y_norm if elbow_y_norm is not None else (shoulder_y_norm + wrist_xy_norm[1]) / 2
    landmarks = {
        "left_shoulder": Landmark(0.28, shoulder_y_norm, 0, 0.9),
        "right_shoulder": Landmark(0.34, shoulder_y_norm, 0, 0.9),
        "left_hip": Landmark(0.28, hip_y_norm, 0, 0.9),
        "right_hip": Landmark(0.34, hip_y_norm, 0, 0.9),
        "right_elbow": Landmark(0.4, elbow_y_norm, 0, 0.9),
        "right_wrist": Landmark(wrist_xy_norm[0], wrist_xy_norm[1], 0, 0.9),
        "left_elbow": Landmark(0.22, elbow_y_norm, 0, 0.3),
        "left_wrist": Landmark(0.18, elbow_y_norm, 0, 0.3),
        # Knees are offset in x from the hip/ankle line so varying
        # knee_y_norm actually changes the hip-knee-ankle angle (a purely
        # vertical knee point would stay collinear -- always 180 degrees).
        "right_knee": Landmark(0.34 + 0.06, knee_y_norm, 0, 0.9),
        "right_ankle": Landmark(0.34, 0.95, 0, 0.9),
        "left_knee": Landmark(0.28 + 0.06, knee_y_norm, 0, 0.9),
        "left_ankle": Landmark(0.28, 0.95, 0, 0.9),
    }
    return PoseFrame(i, i / FPS, detected=True, landmarks=landmarks, pose_confidence=0.9)


def _ball(i, x, y, source=DataSource.DETECTED, conf=0.85):
    return BallObservation(i, i / FPS, x, y, 10.0, conf, source)


def _build_made_shot(start_idx, hoop_x=500.0):
    """Ball held near hand -> knee load -> rises up and over to the hoop,
    passing cleanly through the rim band."""
    pose, ball = [], []
    i = start_idx
    hand_x, hand_y = 0.36 * W, 0.42 * H

    for _ in range(3):
        pose.append(_pose_frame(i, (0.36, 0.42), knee_y_norm=0.75))
        ball.append(_ball(i, hand_x, hand_y))
        i += 1
    for ky in [0.78, 0.84, 0.90, 0.84, 0.78]:
        pose.append(_pose_frame(i, (0.36, 0.42), knee_y_norm=ky))
        ball.append(_ball(i, hand_x, hand_y))
        i += 1
    for _ in range(4):
        pose.append(_pose_frame(i, (0.36, 0.30), knee_y_norm=0.7))
        ball.append(_ball(i, hand_x, hand_y - 15))
        i += 1
    # release + flight toward the hoop, arcing up then down through the rim band
    flight_xy = [
        (hand_x + 20, hand_y - 60), (hand_x + 80, hand_y - 140), (hoop_x - 60, hoop_x * 0 + 40),
        (hoop_x - 10, 70), (hoop_x, 80), (hoop_x + 5, 100),
    ]
    for j, (x, y) in enumerate(flight_xy):
        pose.append(_pose_frame(i, (0.36, 0.30), knee_y_norm=0.7))
        # The point sitting inside the rim band gets a lower confidence,
        # simulating the partial occlusion by the front rim/net a genuine
        # pass-through produces -- the only depth proxy this pipeline has
        # for "went through" vs. "sailed past at an unobservable depth".
        conf = 0.35 if j == 4 else 0.85
        ball.append(_ball(i, x, y, conf=conf))
        i += 1
    for _ in range(8):
        pose.append(_pose_frame(i, (0.36, 0.42), knee_y_norm=0.75))
        ball.append(_ball(i, hand_x, hand_y))
        i += 1
    return pose, ball, i


def _build_missed_shot(start_idx, hoop_x=500.0):
    """Same pattern but shallower knee load, and the ball clangs off the
    rim and bounces away instead of passing through."""
    pose, ball = [], []
    i = start_idx
    hand_x, hand_y = 0.36 * W, 0.42 * H

    for _ in range(3):
        pose.append(_pose_frame(i, (0.36, 0.42), knee_y_norm=0.75))
        ball.append(_ball(i, hand_x, hand_y))
        i += 1
    for ky in [0.77, 0.82, 0.87, 0.82, 0.77]:  # shallower load than the made shot, but still a genuine dip
        pose.append(_pose_frame(i, (0.36, 0.42), knee_y_norm=ky))
        ball.append(_ball(i, hand_x, hand_y))
        i += 1
    for _ in range(4):
        pose.append(_pose_frame(i, (0.34, 0.32), knee_y_norm=0.72))
        ball.append(_ball(i, hand_x, hand_y - 15))
        i += 1
    flight_xy = [
        (hand_x + 20, hand_y - 50), (hand_x + 70, hand_y - 120),
        (hoop_x - 40, 90), (hoop_x + 70, 110), (hoop_x + 150, 160), (hoop_x + 220, 220),
    ]
    for (x, y) in flight_xy:
        pose.append(_pose_frame(i, (0.34, 0.32), knee_y_norm=0.72))
        ball.append(_ball(i, x, y))
        i += 1
    for _ in range(8):
        pose.append(_pose_frame(i, (0.36, 0.42), knee_y_norm=0.75))
        ball.append(_ball(i, hand_x, hand_y))
        i += 1
    return pose, ball, i


def _to_frame_signals(pose_frames, ball_observations):
    torso_scale = 0.20 * H  # matches the synthetic shoulder/hip y gap above
    signals = []
    ball_by_frame = {b.frame_index: b for b in ball_observations}
    prev = None
    for pf in pose_frames:
        obs = ball_by_frame[pf.frame_index]
        ball_available = obs.source != DataSource.UNAVAILABLE
        hand_dist_norm, vvel_norm, shoulder_y = None, None, None
        if ball_available:
            rw = pf.landmark("right_wrist")
            wrist_px = (rw.x * W, rw.y * H)
            ball_px = (obs.center_x, obs.center_y)
            d = ((wrist_px[0] - ball_px[0]) ** 2 + (wrist_px[1] - ball_px[1]) ** 2) ** 0.5
            hand_dist_norm = d / torso_scale
            if prev is not None:
                dt = pf.timestamp_sec - prev[1]
                if dt > 1e-6:
                    vvel_norm = ((obs.center_y - prev[0][1]) / dt) / torso_scale
            ls, rs = pf.landmark("left_shoulder"), pf.landmark("right_shoulder")
            shoulder_y = ((ls.y + rs.y) / 2.0) * H
        angles = []
        for side in ("left", "right"):
            hip, knee, ankle = pf.landmark(f"{side}_hip"), pf.landmark(f"{side}_knee"), pf.landmark(f"{side}_ankle")
            from app.biomechanics.geometry import knee_angle
            a = knee_angle((hip.x, hip.y), (knee.x, knee.y), (ankle.x, ankle.y))
            if a is not None:
                angles.append(a)
        knee_mean = sum(angles) / len(angles) if angles else None

        signals.append(FrameSignals(
            frame_index=pf.frame_index, timestamp_sec=pf.timestamp_sec, ball_available=ball_available,
            ball_x=obs.center_x if ball_available else None, ball_y=obs.center_y if ball_available else None,
            ball_hand_dist_norm=hand_dist_norm, ball_vertical_velocity_norm=vvel_norm,
            knee_angle_deg=knee_mean, shoulder_y=shoulder_y, pose_confidence=pf.pose_confidence,
        ))
        prev = ((obs.center_x, obs.center_y) if ball_available else None, pf.timestamp_sec)
    return signals


def test_full_synthetic_session_two_shots_made_and_missed():
    made_pose, made_ball, next_idx = _build_made_shot(0)
    gap = 15
    missed_pose, missed_ball, _ = _build_missed_shot(next_idx + gap)

    pose_frames = made_pose + missed_pose
    ball_observations = made_ball + missed_ball
    frame_signals = _to_frame_signals(pose_frames, ball_observations)

    windows = detect_shots(frame_signals)
    assert len(windows) == 2, f"expected 2 shots, got {len(windows)}"

    shots = [
        build_shot_from_window(w, frame_signals, pose_frames, ball_observations, HOOP, W, H)
        for w in windows
    ]

    # Outcomes attach to the correct shot.
    assert shots[0].outcome == ShotOutcome.MADE
    assert shots[1].outcome == ShotOutcome.MISSED

    # Metrics attach to the correct shot (made shot had deeper knee load).
    assert shots[0].mechanics.knee_angle_at_load_deg is not None
    assert shots[1].mechanics.knee_angle_at_load_deg is not None
    assert shots[0].mechanics.knee_angle_at_load_deg < shots[1].mechanics.knee_angle_at_load_deg

    # Session analytics run without error on this small but valid session.
    consistency = compute_consistency(shots)
    mvm = compute_makes_vs_misses(shots)
    summary = compute_session_summary(shots, consistency, mvm)
    assert summary.made == 1
    assert summary.missed == 1
    assert summary.shooting_percentage == 50.0

    # With only 1 make + 1 miss, makes-vs-misses must honestly refuse to
    # draw conclusions (below the configured minimum sample size).
    assert not mvm.eligible
    findings = generate_makes_vs_misses_findings(mvm)
    assert len(findings) >= 1
    assert "Insufficient" in findings[0].evidence or "Not enough" in findings[0].evidence


def test_unknown_outcome_when_hoop_missing_propagates_correctly():
    made_pose, made_ball, _ = _build_made_shot(0)
    frame_signals = _to_frame_signals(made_pose, made_ball)
    windows = detect_shots(frame_signals)
    assert len(windows) == 1

    shot = build_shot_from_window(windows[0], frame_signals, made_pose, made_ball, None, W, H)
    assert shot.outcome == ShotOutcome.UNKNOWN
    assert shot.hoop_confidence == 0.0


def test_repeated_shots_produce_independent_ball_track_quality():
    made_pose, made_ball, next_idx = _build_made_shot(0)
    missed_pose, missed_ball, _ = _build_missed_shot(next_idx + 15)
    pose_frames = made_pose + missed_pose
    ball_observations = made_ball + missed_ball
    frame_signals = _to_frame_signals(pose_frames, ball_observations)
    windows = detect_shots(frame_signals)
    shots = [build_shot_from_window(w, frame_signals, pose_frames, ball_observations, HOOP, W, H)
             for w in windows]
    for s in shots:
        assert 0.0 <= s.ball_track_quality <= 1.0


def test_enriched_flight_points_beyond_window_end_frame_reach_outcome_detection():
    """
    Regression test for the enrich_near_hoop() <-> build_shot_from_window()
    contract. enrich_near_hoop()'s own docstring/comments describe its
    return value as spanning up to window.end_frame + a margin (~0.5s,
    bounded only by the next shot's start) -- deliberately re-reading past
    a forced-early window close to recover rim-adjacent evidence. Simulates
    exactly that: a window truncated one frame before the shot's below-rim
    crossing point, with the crossing point still present in the ball
    observations a real detection pass would have produced.
    """
    made_pose, made_ball, _ = _build_made_shot(0)
    frame_signals = _to_frame_signals(made_pose, made_ball)
    windows = detect_shots(frame_signals)
    assert len(windows) == 1
    window = windows[0]

    below_rim_frame = 17  # first point below the rim band in _build_made_shot's flight path
    assert any(o.frame_index == below_rim_frame for o in made_ball)
    truncated_window = replace(window, end_frame=below_rim_frame - 1)

    # Without the below-rim point, the crossing can't be confirmed at all.
    shot_unenriched = build_shot_from_window(
        truncated_window, frame_signals, made_pose, made_ball, HOOP, W, H)
    assert shot_unenriched.outcome != ShotOutcome.MADE

    # enrich_near_hoop's actual output for this shot would include frame 17
    # (within its end_frame + margin_sec window) -- reproduced directly
    # here as the full made_ball list, since only build_shot_from_window's
    # *consumption* of that contract is under test.
    shot_enriched = build_shot_from_window(
        truncated_window, frame_signals, made_pose, made_ball, HOOP, W, H,
        enriched_flight_points=list(made_ball))
    assert shot_enriched.outcome == ShotOutcome.MADE, (
        "enrich_near_hoop() fetches evidence past window.end_frame by design, but "
        "build_shot_from_window discarded it via a redundant re-clamp to window.end_frame"
    )


def test_apex_height_norm_uses_bilateral_visibility_gated_torso_not_single_side():
    """
    Regression test for the apex_height_norm torso-length inconsistency:
    orchestrator.py's own torso-length computation for apex_height_norm
    used to pick a single side's shoulder/hip landmarks (left, if present)
    with no visibility check, independently of
    app.biomechanics.metrics.torso_points's bilateral, visibility-gated
    reference (already used for release_height_norm). A degenerate single
    landmark could blow up apex_height_norm even while the true, bilateral
    torso length is completely normal.
    """
    made_pose, made_ball, _ = _build_made_shot(0)
    frame_signals = _to_frame_signals(made_pose, made_ball)
    windows = detect_shots(frame_signals)
    assert len(windows) == 1
    window = windows[0]

    # Degenerate LEFT shoulder/hip (near-zero separation) at full
    # visibility, applied to every frame so this is robust to exactly
    # which frame release refinement lands on -- the old sp[0]/hp[0] logic
    # picks left first and had no visibility gate, so this alone would
    # collapse its torso length to near zero. The RIGHT side (and so the
    # bilateral average) is untouched on every frame.
    patched_pose = []
    for pf in made_pose:
        degenerate_landmarks = dict(pf.landmarks)
        degenerate_landmarks["left_shoulder"] = Landmark(0.28, 0.50, 0, 0.9)
        degenerate_landmarks["left_hip"] = Landmark(0.28, 0.505, 0, 0.9)
        patched_pose.append(replace(pf, landmarks=degenerate_landmarks))

    shot = build_shot_from_window(window, frame_signals, patched_pose, made_ball, HOOP, W, H)

    # The bilateral, visibility-gated torso reference keeps apex_height_norm
    # in a physically sane range -- a single-side computation anchored to
    # the near-zero-length degenerate left side would blow this up by
    # roughly two orders of magnitude instead.
    assert shot.trajectory.apex_height_norm is not None
    assert shot.trajectory.apex_height_norm < 5.0


def test_apex_height_norm_abstains_when_torso_visibility_is_too_low():
    """Both shoulders/hips present but below the visibility floor -- the
    canonical torso_points() reference abstains (returns None) rather than
    trusting low-confidence landmarks, and apex_height_norm must honestly
    follow suit (None + a warning) instead of fabricating a number from
    untrustworthy positions."""
    made_pose, made_ball, _ = _build_made_shot(0)
    frame_signals = _to_frame_signals(made_pose, made_ball)
    windows = detect_shots(frame_signals)
    window = windows[0]

    # Low visibility on every frame's torso landmarks, robust to exactly
    # which frame release refinement lands on.
    patched_pose = []
    for pf in made_pose:
        low_vis_landmarks = dict(pf.landmarks)
        for name in ("left_shoulder", "right_shoulder", "left_hip", "right_hip"):
            lm = low_vis_landmarks[name]
            low_vis_landmarks[name] = replace(lm, visibility=0.1)
        patched_pose.append(replace(pf, landmarks=low_vis_landmarks))

    shot = build_shot_from_window(window, frame_signals, patched_pose, made_ball, HOOP, W, H)
    assert shot.trajectory.apex_height_norm is None
    assert "apex_height_unavailable" in shot.trajectory.warnings
