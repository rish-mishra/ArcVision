"""
Regression tests for the false-shot-segmentation bug documented in
docs/SHOWCASE_SEGMENTATION_FIX.md: a momentary, noisy ball-hand touch --
riding on (a) a real knee-flexion dip that actually belongs to an earlier,
unrelated moment (borrowed via the existing lookback window) and/or (b) a
"separation" confirmed purely by the ball briefly dropping out of tracking
rather than any genuine confirmed distance -- can complete an entire
LOAD->UPWARD->RELEASE->FLIGHT cycle in a single frame and be counted as its
own phantom shot, even though no real shooting attempt happened at that
moment. All fixtures are synthetic (no showcase timestamps/filenames/session
IDs) and constructed to isolate this general class of failure, distinct from
(and already covered independently by) the pre-existing fixtures in
tests/test_shot_state_machine.py for rebounds, dribbles, and rapid
legitimate catch-and-shoot sequences -- those are included here too (as
A-F) purely to confirm the fix under test doesn't regress them.
"""
from app.config import CONFIG
from app.events.shot_state_machine import FrameSignals, detect_shots

FPS = 30.0


def _frame(i, ball_available=True, ball_hand_dist=0.05, vvel=0.0, knee=170.0, shoulder_y=0.3, ball_y=0.5,
            ball_is_observed=True, hip_x_norm=5.0):
    return FrameSignals(
        frame_index=i, timestamp_sec=i / FPS, ball_available=ball_available,
        ball_x=0.5, ball_y=ball_y, ball_hand_dist_norm=ball_hand_dist,
        ball_vertical_velocity_norm=vvel, knee_angle_deg=knee, shoulder_y=shoulder_y,
        pose_confidence=0.9, ball_is_observed=ball_is_observed, hip_x_norm=hip_x_norm,
    )


def _legit_shot(start=0, knee_min=130.0, hold=6):
    """close+load -> knee bends -> ball rises fast, confirmed FAR and above
    shoulder -> flight -> settles far away. Matches the helper in
    tests/test_shot_state_machine.py."""
    frames = []
    i = start
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, int(knee_min), -8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    for k in range(int(knee_min), 175, 8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k))); i += 1
    for _ in range(4):
        frames.append(_frame(i, ball_hand_dist=0.4, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.1, knee=175.0, ball_y=0.05)); i += 1
    for _ in range(hold):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    return frames, i


# ---------------------------------------------------------------------------
# A-F: the general failure categories named in docs/SHOWCASE_SEGMENTATION_FIX.md,
# Step 3 -- each already independently covered in tests/test_shot_state_machine.py
# (test_rebound_after_miss_is_not_a_shot, test_rapid_consecutive_shots_via_
# primary_trigger_are_not_suppressed, test_dribble_bounce_near_hand_is_not_a_shot,
# test_detects_single_legitimate_shot, test_normal_quick_shot_unaffected_by_the_
# redesign, test_fallback_does_not_recreate_a_shot_from_the_same_flight_after_
# forced_closure respectively). Included here as fresh, self-contained fixtures
# so this file stands alone as the record for this investigation.
# ---------------------------------------------------------------------------

def test_a_rebound_after_shot_is_not_a_second_shot():
    frames, end = _legit_shot()
    i = end
    for _ in range(20):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=172.0)); i += 1
    for _ in range(CONFIG.shot.fallback_trigger_frames + 3):
        frames.append(_frame(i, ball_available=True, ball_hand_dist=0.9, vvel=-0.6,
                               ball_y=0.1, shoulder_y=0.3, knee=173.0 + (i % 3))); i += 1
    for _ in range(10):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.1, knee=172.0)); i += 1
    windows = detect_shots(frames)
    assert len(windows) == 1, "a rebound must not be counted as a second shot"


def test_b_immediate_real_catch_and_shoot_is_allowed():
    frames, end = _legit_shot(start=0)
    i = end
    for _ in range(CONFIG.shot.min_frames_between_shots + 2):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=175.0)); i += 1
    frames2, end2 = _legit_shot(start=i)
    frames += frames2
    windows = detect_shots(frames)
    assert len(windows) == 2, "a genuine, fast rebound-catch-and-shoot must not be suppressed"


def test_c_dribble_bounce_near_hand_is_not_a_shot():
    frames = []
    i = 0
    for _ in range(5):
        frames.append(_frame(i, ball_hand_dist=0.1, vvel=0.0, knee=177.0)); i += 1
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-3.0, knee=178.0)); i += 1
    for _ in range(10):
        frames.append(_frame(i, ball_hand_dist=0.15, vvel=0.5, knee=176.5)); i += 1
    windows = detect_shots(frames)
    assert len(windows) == 0, "a dribble bounce with no knee load must not be counted as a shot"


def test_d_ordinary_genuine_shot_remains_detected():
    frames, end = _legit_shot()
    windows = detect_shots(frames)
    assert len(windows) == 1
    assert windows[0].release_candidate_frame is not None


def test_e_quick_genuine_release_remains_detected():
    """A real shot whose LOAD->UPWARD gap is very short (the common,
    already-relied-upon case of late ball-hand-proximity confirmation --
    see shot_state_machine.py's own module docstring) must still be
    detected, and via genuine confirmed-far separation evidence."""
    frames, end = _legit_shot(knee_min=150.0)  # shallower dip -> fewer LOAD frames
    windows = detect_shots(frames)
    assert len(windows) == 1
    assert windows[0].release_candidate_frame is not None


def test_f_rearm_after_completed_possession_works():
    frames = []
    i = 0
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 130, -8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    for k in range(130, 175, 8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k))); i += 1
    for _ in range(4):
        frames.append(_frame(i, ball_hand_dist=0.4, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3)); i += 1
    for _ in range(160):  # forces a non-confirmed closure (> max_flight_duration_frames)
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.05, knee=175.0, ball_y=0.05)); i += 1
    for _ in range(CONFIG.shot.post_flight_ownership_frames + 20):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=175.0)); i += 1
    frames2, end2 = _legit_shot(start=i)
    frames += frames2
    windows = detect_shots(frames)
    assert len(windows) == 2, "a genuine new shot must still be detected once the ownership window lapses"


# ---------------------------------------------------------------------------
# G: the actual architectural bug found in the showcase video's two false
# events. A real knee-flexion dip happens while the ball is clearly away
# from the hand (e.g. the shooter settling/repositioning) -- not a load.
# Well afterward but still inside the existing knee-dip lookback window, the
# ball grazes the hand for a single frame with a coincidental velocity blip;
# LOAD->UPWARD fires in that same 1-2 frame span, "confirmed" only by the
# earlier, unrelated dip. "Separation" then completes not through any
# confirmed-far ball position but purely because the ball drops out of
# tracking for a couple of frames immediately after. This must not count as
# a shot distinct from the genuine ones on either side of it.
# ---------------------------------------------------------------------------

def test_g_noisy_momentary_hand_touch_with_stale_knee_dip_is_not_a_phantom_shot():
    frames = []
    shot_a, i = _legit_shot(start=0)
    frames += shot_a

    # Settle: ball away from the hand, knee neutral.
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.0, knee=170.0)); i += 1

    # A real knee dip happens here -- but the ball stays clearly AWAY from
    # the hand throughout, so this is not a shooting load; it's incidental
    # motion (e.g. resettling after the previous shot).
    for k in range(170, 145, -5):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.0, knee=float(k))); i += 1
    for k in range(145, 172, 5):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.0, knee=float(k))); i += 1

    # Padding: ball still away, knee back to a flat baseline -- well inside
    # load_lookback_max_frames (45) of the trigger below.
    for _ in range(8):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.0, knee=172.0)); i += 1

    # The phantom trigger: a single frame where the ball is suddenly close
    # to the hand, immediately followed by one frame of upward velocity --
    # LOAD is entered and, one frame later, "confirmed" only via the stale
    # dip above, with no real gather happening at this moment at all.
    frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    frames.append(_frame(i, ball_hand_dist=0.06, vvel=-0.5, knee=170.5)); i += 1

    # "Separation" achieved purely via a couple of dropped-tracking frames --
    # never a single confirmed-far, above-shoulder ball position.
    frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=None, knee=171.0)); i += 1
    frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=None, knee=171.0)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.0, knee=172.0)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1

    # Shot B: a real second shot, well after, via the primary trigger with a
    # genuine, sustained dwell.
    shot_b, i = _legit_shot(start=i + CONFIG.shot.min_frames_between_shots + 5)
    frames += shot_b

    windows = detect_shots(frames)
    assert len(windows) == 2, (
        f"expected exactly 2 genuine shots (the momentary noisy touch must not "
        f"count as a third), got {len(windows)}"
    )
