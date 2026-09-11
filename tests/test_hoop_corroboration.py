"""
Adversarial synthetic tests for hoop_corroboration.py (Architecture C,
Experiment 1: downstream hoop-proximity tiering). Confirms the tiering is
purely additive evidence -- never changes whether trajectory_shot_detector
confirms a candidate, only how it's labeled afterward.
"""
from app.config import CONFIG
from app.events.hoop_corroboration import corroborate
from app.events.shot_state_machine import FrameSignals
from app.events.trajectory_shot_detector import detect_shot_attempts
from app.vision.types import DataSource, HoopLocation

FPS = 30.0
TORSO = 100.0


def _f(i, x, y):
    return FrameSignals(
        frame_index=i, timestamp_sec=i / FPS, ball_available=True,
        ball_x=x, ball_y=y, ball_hand_dist_norm=None, ball_vertical_velocity_norm=None,
        knee_angle_deg=170.0, shoulder_y=300.0, pose_confidence=0.9,
        ball_is_observed=True, hip_x_norm=5.0,
        left_wrist_xy=None, right_wrist_xy=None, ball_source=DataSource.DETECTED,
    )


def _shot_toward(x0, y0, hoop_x, hoop_y, n=14, n_fall=5):
    """A rise-then-fall flight arcing from (x0,y0) toward the hoop."""
    frames = []
    dx = (hoop_x - x0) / n
    for k in range(n):
        frames.append(_f(k, x0 + dx * k, y0 - 6.0 * k))
    last = frames[-1]
    for k in range(n_fall):
        frames.append(_f(n + k, last.ball_x + dx * (k + 1), last.ball_y + 6.0 * (k + 1)))
    return frames


def _one_confirmed(frames):
    events = [c for c in detect_shot_attempts(frames, torso_scale_px=TORSO) if c.confirmed]
    assert len(events) == 1, f"expected exactly one confirmed candidate, got {len(events)}"
    return events[0]


def test_flight_through_hoop_vicinity_is_corroborated():
    # Place the hoop right at this toy trajectory's own apex (x=500+300*13/14,
    # y=600-6*13) rather than assuming an unrealistic arc height -- the point
    # under test is the distance check itself, not a physically tuned arc.
    frames = _shot_toward(500.0, 600.0, 800.0, 600.0)
    apex_x = 500.0 + (300.0 / 14.0) * 13
    apex_y = 600.0 - 6.0 * 13
    hoop = HoopLocation(rim_center_x=apex_x, rim_center_y=apex_y, rim_radius_px=30.0,
                          confidence=0.9, votes=5, method="manual")
    candidate = _one_confirmed(frames)
    result = corroborate(candidate, frames, hoop)
    assert result.tier == "hoop_corroborated"


def test_flight_far_from_hoop_is_not_corroborated():
    hoop = HoopLocation(rim_center_x=3000.0, rim_center_y=200.0, rim_radius_px=30.0,
                          confidence=0.9, votes=5, method="manual")
    frames = _shot_toward(500.0, 600.0, 520.0, 600.0)  # rises in place, nowhere near the hoop
    candidate = _one_confirmed(frames)
    result = corroborate(candidate, frames, hoop)
    assert result.tier == "no_hoop_evidence"


def test_no_hoop_location_reports_that_explicitly():
    frames = _shot_toward(500.0, 600.0, 520.0, 600.0)
    candidate = _one_confirmed(frames)
    result = corroborate(candidate, frames, None)
    assert result.tier == "no_hoop_location"


def test_low_confidence_hoop_treated_as_no_hoop_location():
    hoop = HoopLocation(rim_center_x=520.0, rim_center_y=200.0, rim_radius_px=30.0,
                          confidence=0.05, votes=1, method="hough_color")
    frames = _shot_toward(500.0, 600.0, 520.0, 600.0)
    candidate = _one_confirmed(frames)
    result = corroborate(candidate, frames, hoop)
    assert result.tier == "no_hoop_location"


def test_airball_shape_still_confirms_upstream_but_gets_no_hoop_evidence_tier():
    """Corroboration must never retroactively un-confirm a candidate --
    an airball drifting away from the hoop is still a confirmed shot
    attempt at the trajectory_shot_detector layer; it simply won't carry
    the hoop-corroborated tier. Preserving this distinction is the whole
    point of keeping hoop proximity non-required."""
    hoop = HoopLocation(rim_center_x=4000.0, rim_center_y=200.0, rim_radius_px=30.0,
                          confidence=0.9, votes=5, method="manual")
    frames = _shot_toward(200.0, 600.0, 260.0, 600.0)  # drifts slightly, nowhere near the distant hoop
    candidate = _one_confirmed(frames)
    assert candidate.confirmed is True
    result = corroborate(candidate, frames, hoop)
    assert result.tier == "no_hoop_evidence"
