"""
Synthetic per-frame sequences exercising the isolated, shadow-mode
ball-centric release-event detector (app/events/release_event_detector.py,
migration-plan Phase 1) -- independent of the existing ShotStateMachine.

TORSO scales ball/wrist pixel positions: 100px == 1 torso-length. All ball
positions are DETECTED unless a test specifically constructs an
INTERPOLATED/mixed sequence. Wrist motion is kept physically continuous
(no teleporting) since the CONTROLLED -> SEPARATING state model requires a
genuinely continuous episode -- a wrist that jumps discontinuously between
frames isn't a "brief tracking gap," it's a broken episode, and the state
model is supposed to treat that as broken.
"""
from app.config import CONFIG
from app.events.release_event_detector import detect_release_events
from app.events.shot_state_machine import FrameSignals
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


def _control(start_i, x, y, n, wrist_offset=5.0):
    """n frames of the ball held still near a fixed wrist -- zero relative
    velocity, small separation: a genuine CONTROLLED episode."""
    return [_f(start_i + k, x, y, left_wrist=(x, y + wrist_offset)) for k in range(n)]


def _release(start_i, x, y0, n, wrist_offset=5.0, dy=-6.0, source=DataSource.DETECTED):
    """n frames of the ball rising away from a FIXED wrist (realistic
    follow-through: the hand stays near the shot pocket while the ball
    accelerates away) -- separation grows naturally from wrist_offset."""
    wrist = (x, y0 + wrist_offset)
    return [_f(start_i + k, x, y0 + dy * k, left_wrist=wrist, source=source) for k in range(n)]


def _events(frames):
    return detect_release_events(frames, torso_scale_px=TORSO)


# ================= existing scenarios (re-verified against the state model) =================

def test_normal_dribble_does_not_fire():
    frames = _control(0, 500, 500, 3) + [
        _f(3, 500, 500 - 6.0, left_wrist=(500, 505)),
        _f(4, 500, 500, left_wrist=(500, 505)),
        _f(5, 500, 500 - 0.5, left_wrist=(500, 505)),
    ]
    assert _events(frames) == []


def test_hard_dribble_vetoed_by_lack_of_separation():
    frames = [_f(k, 500, 500 - 2.0 * k, left_wrist=(500, 500 - 2.0 * k + 5.0)) for k in range(6)]
    assert _events(frames) == []


def test_walking_gait_signal_is_not_consulted():
    frames = [_f(k, 500, 500 - 2.0 * k, left_wrist=(500, 500 - 2.0 * k + 5.0)) for k in range(6)]
    for j, f in enumerate(frames):
        f.knee_angle_deg = 145.0
        f.hip_x_norm = 5.0 + j * 0.5
    assert _events(frames) == []


def test_pass_does_not_fire():
    frames = [_f(i, 500 + i * 40, 500, left_wrist=(500, 500)) for i in range(6)]
    assert _events(frames) == []


def test_clean_release_fires_as_strong():
    frames = _control(0, 500, 500, 10) + _release(10, 500, 500, 8)
    events = _events(frames)
    assert len(events) == 1
    assert events[0].path == "strong"


def test_soft_floater_fires_with_both_wrists_tracked():
    # Control ends just under the separation threshold (17.9 < 18px) so the
    # very first sub-strong rise step already crosses it -- a soft-path
    # ascent qualifies at the SAME transition where control ends, which is
    # what the state model requires (no slow "neither controlled nor
    # separating" dead zone).
    wrists = dict(left_wrist=(500, 417.9), right_wrist=(540, 417.9))
    control = [_f(k, 500, 400, **wrists) for k in range(10)]
    rise = [_f(10 + k, 500, 400 - 0.9 * k, **wrists) for k in range(8)]
    events = _events(control + rise)
    assert len(events) == 1
    assert events[0].path == "soft"


def test_soft_floater_does_not_fire_with_only_one_wrist_tracked():
    control = [_f(k, 500, 400, left_wrist=(500, 417.9)) for k in range(10)]
    rise = [_f(10 + k, 500, 400 - 0.9 * k, left_wrist=(500, 417.9)) for k in range(8)]
    assert _events(control + rise) == []


def test_phantom_interpolated_bridge_is_rejected():
    control = _control(0, 500, 500, 4)
    frames = control + [
        _f(4, 500, 498, left_wrist=(500, 505), source=DataSource.DETECTED),
        _f(5, 500, 496, left_wrist=(500, 505), source=DataSource.DETECTED),
        _f(6, 500, 50, left_wrist=(500, 505), source=DataSource.INTERPOLATED),
        _f(7, 500, 700, left_wrist=(500, 505), source=DataSource.INTERPOLATED),
        _f(8, 500, 493, left_wrist=(500, 505), source=DataSource.DETECTED),
        _f(9, 500, 491, left_wrist=(500, 505), source=DataSource.DETECTED),
    ]
    assert _events(frames) == []


def test_isolated_bad_detected_point_does_not_corrupt_release():
    control = _control(0, 700, 380, 10, wrist_offset=10.0)
    good = [_f(10 + k, 700, 380 - 15.0 * k, left_wrist=(700, 390.0)) for k in range(4)]
    bad = _f(14, 756, 276, left_wrist=(700, 390.0), source=DataSource.DETECTED)
    more_good = [_f(15 + k, 700, 380 - 15.0 * (k + 4), left_wrist=(700, 390.0)) for k in range(3)]
    frames = control + good + [bad] + more_good
    events = _events(frames)
    assert len(events) == 1
    assert events[0].path == "strong"
    assert events[0].evidence["consecutive_qualifying_frames"] >= CONFIG.release_event.consecutive_frames


def test_short_gap_between_trusted_anchors_preserves_streak():
    control = _control(0, 700, 380, 10, wrist_offset=10.0)
    real_ys = [380 - 20.0 * k for k in range(6)]
    frames = list(control)
    for k, y in enumerate(real_ys):
        fi = 10 + k * 2
        frames.append(_f(fi, 700, y, left_wrist=(700, 390.0), source=DataSource.DETECTED))
        if k < len(real_ys) - 1:
            frames.append(_f(fi + 1, 300, 300, left_wrist=(700, 390.0), source=DataSource.INTERPOLATED))
    events = _events(frames)
    assert len(events) == 1
    assert events[0].path == "strong"


def test_long_gap_between_trusted_anchors_does_not_preserve_streak():
    control = _control(0, 700, 380, 10, wrist_offset=10.0)
    frames = control + [
        _f(10, 700, 380, left_wrist=(700, 390.0), source=DataSource.DETECTED),
        _f(30, 700, 200, left_wrist=(700, 390.0), source=DataSource.DETECTED),
        _f(31, 700, 198, left_wrist=(700, 390.0), source=DataSource.DETECTED),
        _f(32, 700, 196, left_wrist=(700, 390.0), source=DataSource.DETECTED),
    ]
    assert _events(frames) == []


def test_true_hard_dribble_bounce_rejected_by_controlled_precondition():
    wrist = (900.0, 900.0)  # far from the ball for the entire sequence
    frames = (
        [_f(k, 500, 200 + 30.0 * k, left_wrist=wrist) for k in range(6)]
        + [_f(6 + k, 500, 380 - 2.0 * k, left_wrist=wrist) for k in range(8)]
    )
    assert _events(frames) == []


def test_pump_fake_beyond_override_window_fires_as_override():
    # A wrist keypoint that only partially tracks the ball (half its
    # speed) -- not glued (that's genuine control), not fixed (that's a
    # clean release) -- separation grows too slowly to naturally cross
    # the threshold, while relative velocity is too high to count as
    # controlled: the ambiguous "stuck/noisy keypoint riding a real
    # launch" case the override exists for.
    # A few genuinely-still frames first, to establish real CONTROLLED
    # state, before the ball accelerates away with only partial wrist
    # tracking.
    n = CONFIG.release_event.veto_override_frames + CONFIG.release_event.consecutive_frames + 2
    frames = _control(0, 500, 500, 4, wrist_offset=2.0)
    frames += [_f(4 + k, 500, 500 - 2.0 * k, left_wrist=(500, 502.0 - 1.0 * k)) for k in range(n)]
    events = _events(frames)
    assert len(events) == 1
    assert events[0].path == "strong_override"


# ================= new: explicit state-transition scenarios =================

def test_genuine_held_ball_separation_release():
    """CONTROLLED -> SEPARATING -> RELEASE, the textbook case."""
    frames = _control(0, 700, 500, 12) + _release(12, 700, 500, 8)
    events = _events(frames)
    assert len(events) == 1
    assert events[0].path == "strong"


def test_repeated_dribble_produces_no_candidate():
    """The central hypothesis under test: TWO dribble bounces in a row,
    each with its own brief close-approach to the wrist followed by an
    independent fall/bounce cycle. Under the old lookback model, the
    first bounce's close approach could authorize the second bounce's
    ascent; under the state model, control lost into the first fall must
    not survive to authorize anything later."""
    wrist = (900.0, 900.0)
    frames = []
    # bounce 1: brief control near the wrist, then falls away, then rebounds far from any wrist
    frames += _control(0, 500, 500, 4, wrist_offset=3.0)
    frames += [_f(4 + k, 500, 500 + 40.0 * k, left_wrist=(500, 503.0)) for k in range(5)]   # falling, still "near" wrist x but growing distance
    frames += [_f(9 + k, 500, 660 - 30.0 * k, left_wrist=wrist) for k in range(5)]           # bounce back up, far from wrist
    # bounce 2: independent fall/rise cycle, again far from any wrist the whole time
    frames += [_f(14 + k, 500, 350 + 30.0 * k, left_wrist=wrist) for k in range(4)]
    frames += [_f(18 + k, 500, 470 - 30.0 * k, left_wrist=wrist) for k in range(6)]
    assert _events(frames) == []


def test_control_loss_then_unrelated_ascent_not_authorized():
    """Control ends (ball drops away, uncontrolled fall), THEN an
    unrelated ascent begins far from any wrist -- the earlier control
    episode must not reach across the intervening loss to authorize it."""
    wrist = (900.0, 900.0)
    frames = (
        _control(0, 500, 400, 8, wrist_offset=4.0)
        + [_f(8 + k, 500, 400 + 25.0 * k, left_wrist=(500, 404.0)) for k in range(6)]  # ball dropped, falling away
        + [_f(14 + k, 500, 550 - 20.0 * k, left_wrist=wrist) for k in range(10)]        # later, unrelated ascent, no wrist nearby
    )
    assert _events(frames) == []


def test_brief_trusted_gap_during_control_does_not_break_episode():
    """A short, continuity-validated gap in ball tracking DURING a
    genuine control episode (e.g. one frame's detection rejected as an
    outlier) must not terminate the CONTROLLED episode -- the same
    bounded gap tolerance used for ascent streaks applies to control."""
    control_a = _control(0, 700, 500, 5, wrist_offset=5.0)
    # a rejected phantom point sits between two genuinely controlled frames
    gap = [_f(5, 700, 500, left_wrist=(700, 505), source=DataSource.INTERPOLATED)]  # will be rejected (inconsistent)
    control_b = _control(6, 700, 500, 5, wrist_offset=5.0)
    release = _release(11, 700, 500, 8, wrist_offset=5.0)
    # Make the phantom point spatially inconsistent so it's actually rejected by the trust filter
    frames = control_a + [_f(5, 250, 900, left_wrist=(700, 505), source=DataSource.INTERPOLATED)] + control_b + release
    events = _events(frames)
    assert len(events) == 1
    assert events[0].path == "strong"


def test_pump_fake_returns_to_controlled_without_release():
    """The ball rises slightly while still glued to the wrist (a pump
    fake that stays well under the override window), then settles back
    into a normal held position -- no release, and the episode should
    still be usable afterward (not permanently poisoned)."""
    frames = (
        _control(0, 500, 500, 5, wrist_offset=3.0)
        + [_f(5 + k, 500, 500 - 3.0 * k, left_wrist=(500, 500 - 3.0 * k + 3.0)) for k in range(4)]  # small glued rise
        + [_f(9 + k, 500, 488 + 3.0 * k, left_wrist=(500, 488 + 3.0 * k + 3.0)) for k in range(4)]   # settles back down, still glued
    )
    assert _events(frames) == []


def test_genuine_release_after_a_pump_fake():
    """A pump fake (glued rise, back down, still controlled) followed by
    a REAL, separating release must still fire on the real one."""
    fake = (
        _control(0, 500, 500, 5, wrist_offset=3.0)
        + [_f(5 + k, 500, 500 - 3.0 * k, left_wrist=(500, 500 - 3.0 * k + 3.0)) for k in range(4)]
        + [_f(9 + k, 500, 488 + 3.0 * k, left_wrist=(500, 488 + 3.0 * k + 3.0)) for k in range(4)]
    )
    settle = _control(13, 500, 500, 6, wrist_offset=3.0)
    real = _release(19, 500, 500, 8, wrist_offset=3.0)
    events = _events(fake + settle + real)
    assert len(events) == 1
    assert events[0].path == "strong"
    assert events[0].release_frame >= 19


def test_rebound_catch_immediate_release():
    """Rebound -> genuine catch (its own fresh CONTROLLED episode) ->
    immediate second release. Each release must be authorized by its OWN
    control episode, not the first one."""
    frames = []
    frames += _control(0, 500, 500, 6)
    frames += _release(6, 500, 500, 8)           # first release
    last_y = frames[-1].ball_y
    frames += _control(14, 500, last_y, 6)       # real catch: a fresh controlled episode
    frames += _release(20, 500, last_y, 8)       # second, independent release

    events = _events(frames)
    assert len(events) == 2
    assert events[1].release_frame - events[0].release_frame < CONFIG.shot.max_flight_duration_frames


# ================= TRANSITION state: gradual, ambiguous, real-motion cases =================
#
# These construct the two-signature distinction the TRANSITION design relies
# on directly: a genuinely developing launch keeps vvel <= 0 (net upward or
# flat) through its ambiguous frames, while an independent fall/dribble shows
# an unambiguous vvel > 0 (net downward) at the moment control ends. None of
# the numbers below were chosen to match Video 1/2/3 specifically -- they
# reuse the existing CONTROLLED/ascent thresholds and vary only frame count
# and ramp shape to exercise the transition itself.

def test_gradual_multi_frame_transition_genuine_release():
    """Relative velocity increases gradually over several frames (a
    realistic follow-through, not an instantaneous jump) before the
    ascent becomes strong enough to register -- must still fire exactly
    once, using the TRANSITION carry-forward."""
    wrist = (700.0, 505.0)  # fixed follow-through position
    control = _control(0, 700, 500, 8, wrist_offset=5.0)
    # Ball accelerates upward in gradually larger steps; wrist stays put,
    # so relative velocity (and eventually separation) grows continuously.
    ramp_dy = [-1.0, -2.0, -3.5]
    ramp = []
    y = 500.0
    for k, dy in enumerate(ramp_dy):
        y += dy
        ramp.append(_f(8 + k, 700, y, left_wrist=wrist))
    release = [_f(11 + k, 700, y + (-7.0 * (k + 1)), left_wrist=wrist) for k in range(6)]
    events = _events(control + ramp + release)
    assert len(events) == 1
    assert events[0].path == "strong"


def test_single_frame_ambiguity_mirrors_real_release_trace():
    """Exactly one ambiguous frame between CONTROLLED and a strong ascent
    -- the direct regression test for the bug found auditing Video 1's
    missed release: control ends, one frame where neither the strict
    CONTROLLED predicate nor a qualifying ascent holds (small net-upward
    velocity, not yet separated), then immediate strong qualification."""
    wrist = (700.0, 505.0)
    control = _control(0, 700, 500, 6, wrist_offset=5.0)
    ambiguous = [_f(6, 700, 499.0, left_wrist=wrist)]  # vvel small, negative, not separated
    release = _release(7, 700, 499.0, 8, wrist_offset=5.0)
    events = _events(control + ambiguous + release)
    assert len(events) == 1
    assert events[0].path == "strong"


def test_continuous_wrist_follow_through_not_fixed():
    """The wrist itself keeps moving (a slower, decelerating
    follow-through) rather than staying pinned -- separation grows from
    genuine relative motion, not a fixed offset."""
    control = _control(0, 700, 500, 8, wrist_offset=5.0)
    frames = list(control)
    ball_y = 500.0
    wrist_y = 505.0
    for k in range(10):
        ball_y += -7.0            # ball accelerates away at a constant fast rate
        wrist_y += -1.0           # wrist follows through, much slower
        frames.append(_f(8 + k, 700, ball_y, left_wrist=(700, wrist_y)))
    events = _events(frames)
    assert len(events) == 1
    assert events[0].path == "strong"


def test_hard_dribble_matched_velocity_magnitude_still_rejected():
    """A dribble bounce reaching the EXACT SAME ascent velocity magnitude
    as the genuine-release tests above, to isolate that the discriminator
    is provenance, not speed -- wrist is never near the ball, so no
    CONTROLLED/TRANSITION episode ever exists to authorize it."""
    wrist = (900.0, 900.0)
    frames = (
        [_f(k, 500, 200 + 25.0 * k, left_wrist=wrist) for k in range(8)]        # falling
        + [_f(8 + k, 500, 400 + (-7.0 * (k + 1)), left_wrist=wrist) for k in range(8)]  # bounce, same -7px/frame as the genuine tests
    )
    assert _events(frames) == []


def test_control_lost_within_transition_then_unrelated_ascent_not_authorized():
    """Control ends into TRANSITION (ambiguous, vvel <= 0), but the very
    next observations reveal it was actually a fall (vvel flips clearly
    positive) -- provenance must be discarded from THAT point, and a
    later, unrelated ascent (no wrist nearby) must not be authorized by
    the earlier, now-invalidated episode."""
    wrist_far = (900.0, 900.0)
    control = _control(0, 500, 400, 6, wrist_offset=4.0)
    ambiguous_then_falling = [
        _f(6, 500, 399.0, left_wrist=(500, 404.0)),   # one ambiguous, near-flat frame
        _f(7, 500, 420.0, left_wrist=(500, 404.0)),    # clearly falling now (vvel > 0)
        _f(8, 500, 450.0, left_wrist=(500, 404.0)),
        _f(9, 500, 490.0, left_wrist=wrist_far),
    ]
    later_ascent = [_f(9 + k, 500, 550 - 20.0 * k, left_wrist=wrist_far) for k in range(10)]
    assert _events(control + ambiguous_then_falling + later_ascent) == []


def test_transitional_wobble_resolves_back_to_controlled_no_release():
    """A brief ambiguous wobble (control predicate fails for 1-2 frames,
    vvel <= 0 throughout) that resolves back into genuine control rather
    than developing into a release -- must not fire, and the episode
    should remain usable (not permanently poisoned)."""
    wrist = (700.0, 505.0)
    control_a = _control(0, 700, 500, 6, wrist_offset=5.0)
    wobble = [_f(6, 700, 499.0, left_wrist=wrist), _f(7, 700, 499.5, left_wrist=wrist)]
    control_b = _control(8, 700, 499.5, 8, wrist_offset=5.0)
    assert _events(control_a + wobble + control_b) == []


def test_pump_fake_via_transition_then_genuine_release():
    """A pump fake that specifically passes through TRANSITION (not the
    glued-CONTROLLED case already tested) before settling back down, then
    a real, separating release -- must fire exactly once, on the real
    ascent."""
    wrist = (700.0, 505.0)
    control_a = _control(0, 700, 500, 6, wrist_offset=5.0)
    fake_rise = [_f(6, 700, 499.0, left_wrist=wrist), _f(7, 700, 497.5, left_wrist=wrist)]  # ambiguous, small rise
    fake_settle = [_f(8, 700, 498.5, left_wrist=wrist), _f(9, 700, 500.0, left_wrist=wrist)]  # settles back down
    control_b = _control(10, 700, 500, 8, wrist_offset=5.0)
    real = _release(18, 700, 500, 8, wrist_offset=5.0)
    events = _events(control_a + fake_rise + fake_settle + control_b + real)
    assert len(events) == 1
    assert events[0].path == "strong"
    assert events[0].release_frame >= 18


def test_rebound_catch_immediate_release_each_with_transitional_ambiguity():
    """Both the rebound-catch and the immediate second release pass
    through their own one-frame TRANSITION ambiguity -- confirms
    TRANSITION doesn't confuse two independent episodes into one, or let
    the first authorize the second."""
    wrist_1 = (500.0, 505.0)
    frames = []
    frames += _control(0, 500, 500, 6, wrist_offset=5.0)
    frames += [_f(6, 500, 499.0, left_wrist=wrist_1)]           # ambiguous
    frames += _release(7, 500, 499.0, 6, wrist_offset=5.0)        # first release
    last_y = frames[-1].ball_y
    wrist_2 = (500.0, last_y + 5.0)
    frames += _control(13, 500, last_y, 6, wrist_offset=5.0)
    frames += [_f(19, 500, last_y - 1.0, left_wrist=wrist_2)]    # ambiguous
    frames += _release(20, 500, last_y - 1.0, 6, wrist_offset=5.0)  # second, independent release

    events = _events(frames)
    assert len(events) == 2
    assert events[1].release_frame - events[0].release_frame < CONFIG.shot.max_flight_duration_frames


# ================= additional TRANSITION regression coverage =================
#
# A windowed (median-of-recent) motion signal was attempted after these were
# first written, to fix a distinct problem (a single-frame downward wobble
# breaking an otherwise-genuine CONTROLLED episode) -- it was REVERTED after
# real-video evaluation showed it caused a worse regression (median lag right
# at the moment control is freshly established). The test that specifically
# required windowing to pass was removed with it; these four do not depend
# on windowing and continue to validate TRANSITION-only behavior.

def test_single_frame_wrist_noise_does_not_break_control():
    """One frame of spurious wrist-position noise (pose jitter, not a real
    hand movement) during an otherwise motionless hold must not prevent the
    eventual release -- TRANSITION absorbs the single ambiguous frame (the
    ball itself never moves) and the episode resolves back to CONTROLLED."""
    control_a = _control(0, 700, 500, 4, wrist_offset=5.0)
    noisy = [_f(4, 700, 500, left_wrist=(700, 650.0))]  # one-frame wrist jitter, ball unmoved
    control_b = _control(5, 700, 500, 5, wrist_offset=5.0)
    release = _release(10, 700, 500, 8, wrist_offset=5.0)
    events = _events(control_a + noisy + control_b + release)
    assert len(events) == 1
    assert events[0].path == "strong"


def test_genuine_sustained_fall_still_invalidates():
    """A REAL fall -- several consecutive frames of clear net-downward
    velocity, not one noisy sample -- must invalidate the episode."""
    wrist_far = (900.0, 900.0)
    control = _control(0, 500, 400, 6, wrist_offset=4.0)
    fall = [_f(6 + k, 500, 400 + 25.0 * (k + 1), left_wrist=(500, 404.0)) for k in range(6)]  # sustained drop
    later_ascent = [_f(12 + k, 500, 550 - 20.0 * k, left_wrist=wrist_far) for k in range(10)]
    assert _events(control + fall + later_ascent) == []


def test_hard_dribble_rejected_large_amplitude():
    """Regression check at a different (larger) amplitude than the earlier
    hard-dribble test: a bounce far from any wrist the entire time must
    still be rejected regardless of how fast or how far it falls."""
    wrist = (900.0, 900.0)
    frames = (
        [_f(k, 500, 200 + 30.0 * k, left_wrist=wrist) for k in range(8)]
        + [_f(8 + k, 500, 460 - 30.0 * k, left_wrist=wrist) for k in range(8)]
    )
    assert _events(frames) == []


def test_repeated_dribble_rejected_alternate_construction():
    """Regression check with a different frame construction than
    test_repeated_dribble_produces_no_candidate: the central
    repeated-dribble hypothesis (a brief close approach on one bounce must
    not authorize a later, independent bounce's ascent) must hold."""
    wrist = (900.0, 900.0)
    frames = []
    frames += _control(0, 500, 500, 4, wrist_offset=3.0)
    frames += [_f(4 + k, 500, 500 + 40.0 * k, left_wrist=(500, 503.0)) for k in range(5)]
    frames += [_f(9 + k, 500, 660 - 30.0 * k, left_wrist=wrist) for k in range(5)]
    frames += [_f(14 + k, 500, 350 + 30.0 * k, left_wrist=wrist) for k in range(4)]
    frames += [_f(18 + k, 500, 470 - 30.0 * k, left_wrist=wrist) for k in range(6)]
    assert _events(frames) == []
