"""
Adversarial synthetic tests for pose_at_arm_corroboration.py (Architecture
C, Experiment 2: bounded pose-at-arm tiering). Confirms this is purely
additive evidence about a single lookback window, never a possession
state machine, and never disqualifies a candidate on its own.
"""
from app.config import CONFIG
from app.events.pose_at_arm_corroboration import corroborate
from app.events.shot_state_machine import FrameSignals
from app.events.trajectory_shot_detector import detect_shot_attempts
from app.vision.types import DataSource

FPS = 30.0
TORSO = 100.0
CF = CONFIG.release_event.consecutive_frames


def _f(i, x, y, left_wrist=None, right_wrist=None):
    return FrameSignals(
        frame_index=i, timestamp_sec=i / FPS, ball_available=True,
        ball_x=x, ball_y=y, ball_hand_dist_norm=None, ball_vertical_velocity_norm=None,
        knee_angle_deg=170.0, shoulder_y=300.0, pose_confidence=0.9,
        ball_is_observed=True, hip_x_norm=5.0,
        left_wrist_xy=left_wrist, right_wrist_xy=right_wrist, ball_source=DataSource.DETECTED,
    )


def _rise_then_fall(n_rise=14, n_fall=5, x=500.0, y0=600.0, wrist_fn=None):
    frames = []
    for k in range(n_rise):
        y = y0 - 6.0 * k
        wrist = wrist_fn(k, x, y) if wrist_fn else None
        frames.append(_f(k, x, y, left_wrist=wrist))
    last = frames[-1]
    for k in range(n_fall):
        frames.append(_f(n_rise + k, x, last.ball_y + 6.0 * (k + 1)))
    return frames


def _one_confirmed(frames):
    events = [c for c in detect_shot_attempts(frames, torso_scale_px=TORSO) if c.confirmed]
    assert len(events) == 1
    return events[0]


def test_wrist_near_ball_at_arm_frame_is_corroborated():
    frames = _rise_then_fall(wrist_fn=lambda k, x, y: (x, y + 5.0))
    candidate = _one_confirmed(frames)
    result = corroborate(candidate, frames, TORSO)
    assert result.tier == "pose_corroborated"


def test_wrist_near_ball_a_few_frames_before_arm_still_corroborates():
    """The lookback window, not just the exact arm frame, matters -- a
    wrist near the ball one or two frames before the streak's own start
    should still corroborate the resulting arm."""
    def wrist_fn(k, x, y):
        return (x, y + 5.0) if k < 2 else None
    frames = _rise_then_fall(wrist_fn=wrist_fn)
    candidate = _one_confirmed(frames)
    result = corroborate(candidate, frames, TORSO)
    assert result.tier == "pose_corroborated"


def test_wrist_far_from_ball_throughout_is_no_pose_evidence():
    frames = _rise_then_fall(wrist_fn=lambda k, x, y: (x + 500.0, y + 500.0))
    candidate = _one_confirmed(frames)
    result = corroborate(candidate, frames, TORSO)
    assert result.tier == "no_pose_evidence"


def test_no_wrist_data_at_all_is_no_pose_data_not_disqualifying():
    frames = _rise_then_fall(wrist_fn=None)
    candidate = _one_confirmed(frames)
    result = corroborate(candidate, frames, TORSO)
    assert result.tier == "no_pose_data"
    # Corroboration must never retroactively touch confirmation.
    assert candidate.confirmed is True


def test_wrist_near_ball_only_well_before_the_lookback_window_is_not_corroborated():
    """A wrist that was near the ball far earlier in an unrelated moment
    (well outside the bounded lookback window) must not corroborate --
    otherwise this stops being a bounded, single-moment check. A held,
    stationary lead-in (wrist glued to the ball, well under the strong
    velocity floor so it never joins the arm streak) precedes the rise by
    more than consecutive_frames trusted frames, then the wrist disappears
    entirely before the rise begins."""
    hold = [_f(k, 500.0, 600.0, left_wrist=(500.0, 605.0) if k < 3 else None) for k in range(10)]
    rise_and_fall = _rise_then_fall(x=500.0, y0=600.0, wrist_fn=None)
    frames = hold + [_f(10 + f.frame_index, f.ball_x, f.ball_y) for f in rise_and_fall]
    candidate = _one_confirmed(frames)
    result = corroborate(candidate, frames, TORSO)
    assert result.tier in ("no_pose_evidence", "no_pose_data")
