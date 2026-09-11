"""
Synthetic per-frame sequences exercising the shadow-only, trajectory-
primary shot-attempt detector (app/events/trajectory_shot_detector.py,
migration-plan Architecture C). Independent of both the TRANSITION
baseline and the episode prototype -- no possession/CONTROLLED/episode
state is exercised or assumed here.

TORSO scales ball/wrist pixel positions: 100px == 1 torso-length, matching
the existing release-detector test conventions. Ball positions are
DETECTED unless a test specifically constructs an INTERPOLATED sequence.
"""
from app.config import CONFIG
from app.events.shot_state_machine import FrameSignals
from app.events.trajectory_shot_detector import detect_shot_attempts
from app.vision.types import DataSource

FPS = 30.0
TORSO = 100.0


def _f(i, x, y, left_wrist=None, right_wrist=None, source=DataSource.DETECTED):
    return FrameSignals(
        frame_index=i, timestamp_sec=i / FPS, ball_available=True,
        ball_x=x, ball_y=y, ball_hand_dist_norm=None, ball_vertical_velocity_norm=None,
        knee_angle_deg=170.0, shoulder_y=300.0, pose_confidence=0.9,
        ball_is_observed=True, hip_x_norm=5.0,
        left_wrist_xy=left_wrist, right_wrist_xy=right_wrist, ball_source=source,
    )


def _hold(start_i, x, y, n):
    """n stationary frames -- no motion, no wrists: a baseline lead-in."""
    return [_f(start_i + k, x, y) for k in range(n)]


def _rise(start_i, x, y0, n, dy=-6.0, wrist_offset=None):
    """n frames rising at a constant rate. wrist_offset=None -> no pose at
    all (tests the strong path's pose independence); a number -> a wrist
    glued that many px below the ball each frame (separated=False)."""
    out = []
    for k in range(n):
        y = y0 + dy * k
        wrist = (x, y + wrist_offset) if wrist_offset is not None else None
        out.append(_f(start_i + k, x, y, left_wrist=wrist))
    return out


def _fall(start_i, x, y0, n, dy=6.0):
    """n frames descending from y0 -- k=0 is already one step BELOW y0
    (y0 itself is the apex/last-rise point, already emitted by the
    caller), so every emitted frame is a genuine descent step."""
    return [_f(start_i + k, x, y0 + dy * (k + 1)) for k in range(n)]


def _events(frames):
    return detect_shot_attempts(frames, torso_scale_px=TORSO)


def _confirmed(frames):
    return [c for c in _events(frames) if c.confirmed]


CF = CONFIG.release_event.consecutive_frames
VOF = CONFIG.release_event.veto_override_frames


# ================= normal shots =================

def test_normal_shot_confirmed_with_no_pose_at_all():
    """Strong arm must fire and confirm using ball velocity alone -- zero
    wrist/pose data anywhere in the sequence."""
    frames = _rise(0, 500, 600, 14) + _fall(14, 500, 600 + (-6.0) * 13, 5)
    events = _confirmed(frames)
    assert len(events) == 1
    assert events[0].arm_path == "strong"
    assert events[0].rise_steps >= 2 * CF


def test_soft_floater_confirmed_with_pose():
    """A slower rise, too slow for the strong path, confirms via the soft
    path when both wrists are tracked, separated, and above the ball."""
    wrist = (500.0, 700.0)  # far below, fixed: always separated, always below the ball
    rise = [_f(k, 500, 600 - 0.9 * k, left_wrist=wrist, right_wrist=wrist) for k in range(14)]
    last_y = rise[-1].ball_y
    fall = [_f(14 + k, 500, last_y + 3.0 * (k + 1)) for k in range(5)]
    events = _confirmed(rise + fall)
    assert len(events) == 1
    assert events[0].arm_path == "soft"


def test_soft_floater_without_pose_never_arms():
    """The same slow rise WITHOUT any wrist data never arms at all -- soft
    requires pose, and the velocity never reaches the strong floor."""
    frames = [_f(k, 500, 600 - 0.9 * k) for k in range(14)]
    assert _events(frames) == []


def test_airball_shaped_flight_confirmed_no_hoop_needed():
    """A real rise-then-fall shape drifting far sideways (nowhere near any
    hoop) -- this module has no hoop input at all, so this must confirm
    exactly like any other shot, demonstrating hoop-independence."""
    frames = []
    x = 200.0
    y = 600.0
    for k in range(14):
        frames.append(_f(k, x + 40.0 * k, y - 6.0 * k))
    last = frames[-1]
    for k in range(5):
        frames.append(_f(14 + k, last.ball_x + 40.0 * (k + 1), last.ball_y + 6.0 * (k + 1)))
    events = _confirmed(frames)
    assert len(events) == 1


def test_consecutive_shots_each_detected_independently():
    frames = []
    frames += _rise(0, 500, 600, 14)
    frames += _fall(14, 500, 600 + (-6.0) * 13, 5)
    last = frames[-1]
    frames += _hold(19, last.ball_x, last.ball_y, 4)
    frames += _rise(23, 500, last.ball_y, 14)
    tail = frames[-1]
    frames += _fall(37, 500, tail.ball_y, 5)
    events = _confirmed(frames)
    assert len(events) == 2
    assert events[1].arm_frame > events[0].apex_frame


# ================= dribbles / pump fakes =================

def test_short_dribble_bounce_not_confirmed():
    """A short rise (well under 2*consecutive_frames total) followed by an
    immediate fall -- the classic dribble rebound shape -- must not
    confirm."""
    frames = _rise(0, 500, 600, 4) + _fall(4, 500, 600 - 6.0 * 3, 6)
    assert _confirmed(frames) == []


def test_repeated_dribble_bounces_none_confirmed():
    frames = []
    y = 600.0
    fi = 0
    for _ in range(3):
        frames += [_f(fi + k, 500, y - 6.0 * k) for k in range(4)]
        y = y - 6.0 * 3
        fi += 4
        frames += [_f(fi + k, 500, y + 6.0 * k) for k in range(4)]
        y = y + 6.0 * 3
        fi += 4
    assert _confirmed(frames) == []


def test_short_pump_fake_glued_to_wrist_never_arms():
    """A fast in-hand raise (strong velocity) with the wrist glued to the
    ball the whole time, well short of the veto-override window -- must
    never arm at all."""
    frames = _rise(0, 500, 600, 4, wrist_offset=5.0)
    last = frames[-1]
    frames += [_f(4 + k, 500, last.ball_y, left_wrist=(500, last.ball_y + 5.0)) for k in range(3)]
    assert _events(frames) == []


def test_sustained_glued_raise_arms_via_override_then_confirms():
    """A wrist keypoint confidently (and wrongly) glued to the ball for
    longer than veto_override_frames, riding what is actually a genuine
    fast launch -- must eventually arm via the override path and, since
    the rise and a real descent follow, confirm as a shot."""
    n_rise = VOF + CF + CF + 2  # comfortably past veto + streak + confirm margin
    frames = _rise(0, 500, 700, n_rise, wrist_offset=5.0)
    last = frames[-1]
    frames += _fall(n_rise, 500, last.ball_y, 5)
    events = _confirmed(frames)
    assert len(events) == 1
    assert events[0].arm_path == "strong_veto_override"


def test_catch_and_hold_no_motion_never_arms():
    frames = _hold(0, 500, 500, 10)
    assert _events(frames) == []


# ================= the documented known limitation =================

def test_rise_that_never_shows_a_descent_is_discarded():
    """A long, genuine-looking rise whose tracking simply ends (the ball
    leaves the frame near its apex) -- rise_steps clears the bar but no
    descent step is ever observed. Must be discarded, not confirmed --
    this is the module's documented, accepted failure mode, not a bug."""
    frames = _rise(0, 500, 700, 14)
    events = _events(frames)
    assert len(events) == 1
    assert events[0].confirmed is False
    assert events[0].discard_reason == "no_descent_observed"


def test_rise_phase_too_short_is_discarded_with_correct_reason():
    """Arms, rises for a couple more steps beyond the arm streak, then a
    gap too large to trust breaks the rise phase before it reaches
    2*consecutive_frames -- discarded for the OTHER documented reason."""
    frames = _rise(0, 500, 700, CF + 1)
    last = frames[-1]
    # A large timestamp jump (bridging gap too big to trust) right after.
    frames.append(_f(last.frame_index + 20, 500, last.ball_y - 60.0))
    events = _events(frames)
    assert len(events) == 1
    assert events[0].confirmed is False
    assert events[0].discard_reason == "rise_phase_too_short"


# ================= trust-filter reuse =================

def test_phantom_interpolated_spike_does_not_fabricate_a_shot():
    hold = _hold(0, 500, 500, 4)
    frames = hold + [
        _f(4, 500, 498, source=DataSource.DETECTED),
        _f(5, 500, 496, source=DataSource.DETECTED),
        _f(6, 500, 50, source=DataSource.INTERPOLATED),
        _f(7, 500, 700, source=DataSource.INTERPOLATED),
        _f(8, 500, 493, source=DataSource.DETECTED),
        _f(9, 500, 491, source=DataSource.DETECTED),
    ]
    assert _confirmed(frames) == []
