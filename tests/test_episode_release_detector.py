"""
Synthetic per-frame sequences exercising the shadow-only temporal
possession-EPISODE prototype (app/events/episode_release_detector.py).

This is a SECOND, independent shadow detector next to
release_event_detector.py's TRANSITION baseline -- not a replacement.  It
reuses that module's trust filter, geometry, and ascent-qualification
primitives verbatim, so most of the existing baseline scenarios (clean
release, dribble rejection, gap handling, phantom-interpolated rejection)
are expected to behave the same way here; several are reused directly
below as parity checks. What's new here are the episode-specific
adversarial cases: local-minimum confirmation shape, round-trip (dribble
bounce) rejection, and the catch->settle->shot pattern with a multi-frame
noisy settle that the reverted windowed-median patch could not survive.

TORSO scales ball/wrist pixel positions: 100px == 1 torso-length, matching
release_event_detector's test conventions.
"""
from app.config import CONFIG
from app.events.episode_release_detector import detect_release_events_episode
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
    velocity throughout, which confirms POSSESSION almost immediately
    (the local-minimum check is trivially satisfied at zero)."""
    return [_f(start_i + k, x, y, left_wrist=(x, y + wrist_offset)) for k in range(n)]


def _release(start_i, x, y0, n, wrist_offset=5.0, dy=-6.0, source=DataSource.DETECTED):
    """n frames of the ball rising away from a FIXED wrist."""
    wrist = (x, y0 + wrist_offset)
    return [_f(start_i + k, x, y0 + dy * k, left_wrist=wrist, source=source) for k in range(n)]


def _events(frames):
    return detect_release_events_episode(frames, torso_scale_px=TORSO)


# ================= parity checks (reused from the TRANSITION baseline's suite) =================
# Same frame constructions as release_event_detector's tests -- since
# _control/_release naturally produce a clean local-minimum confirm (zero
# relative velocity) and a clean ascent streak, these are expected to
# behave identically under the episode model.

def test_clean_release_fires_as_strong():
    frames = _control(0, 500, 500, 10) + _release(10, 500, 500, 8)
    events = _events(frames)
    assert len(events) == 1
    assert events[0].path == "strong"


def test_pass_does_not_fire():
    frames = [_f(i, 500 + i * 40, 500, left_wrist=(500, 500)) for i in range(6)]
    assert _events(frames) == []


def test_true_hard_dribble_bounce_rejected_never_reaches_proximity():
    wrist = (900.0, 900.0)  # far from the ball for the entire sequence
    frames = (
        [_f(k, 500, 200 + 30.0 * k, left_wrist=wrist) for k in range(6)]
        + [_f(6 + k, 500, 380 - 2.0 * k, left_wrist=wrist) for k in range(8)]
    )
    assert _events(frames) == []


def test_hard_dribble_matched_velocity_magnitude_still_rejected():
    """A dribble bounce reaching the same ascent velocity magnitude as a
    genuine release -- isolates that the discriminator is provenance
    (never entered proximity, so no episode ever opened), not speed."""
    wrist = (900.0, 900.0)
    frames = (
        [_f(k, 500, 200 + 25.0 * k, left_wrist=wrist) for k in range(8)]
        + [_f(8 + k, 500, 400 + (-7.0 * (k + 1)), left_wrist=wrist) for k in range(8)]
    )
    assert _events(frames) == []


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


def test_rebound_catch_immediate_release_two_independent_episodes():
    frames = []
    frames += _control(0, 500, 500, 6)
    frames += _release(6, 500, 500, 8)
    last_y = frames[-1].ball_y
    frames += _control(14, 500, last_y, 6)
    frames += _release(20, 500, last_y, 8)
    events = _events(frames)
    assert len(events) == 2
    assert events[1].release_frame - events[0].release_frame < CONFIG.shot.max_flight_duration_frames


def test_pump_fake_glued_rise_then_settle_no_release():
    """A small rise that never leaves proximity (never separates), then
    settles back down -- POSSESSION persists through it trivially (proximity
    never breaks), so no release, and the episode remains usable after."""
    frames = (
        _control(0, 500, 500, 5, wrist_offset=3.0)
        + [_f(5 + k, 500, 500 - 3.0 * k, left_wrist=(500, 500 - 3.0 * k + 3.0)) for k in range(4)]
        + [_f(9 + k, 500, 488 + 3.0 * k, left_wrist=(500, 488 + 3.0 * k + 3.0)) for k in range(4)]
    )
    assert _events(frames) == []


def test_genuine_release_after_a_pump_fake():
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


# ================= episode-specific: local-minimum confirmation shape =================

def test_approach_that_never_bottoms_out_before_leaving_proximity_does_not_confirm():
    """Relative velocity is STILL decreasing (still converging, no local
    minimum reached) when proximity is lost -- POSSESSION must never be
    confirmed, so nothing protects the subsequent motion; this is the
    mechanism that rejects a fast graze that never actually settles."""
    wrist = (500.0, 503.0)
    frames = (
        [_f(0, 500, 560, left_wrist=wrist)]
        + [_f(1, 500, 519, left_wrist=wrist)]   # within proximity (16px), rel vel still large
        + [_f(2, 500, 508, left_wrist=wrist)]   # closer, rel vel smaller (still decreasing)
        + [_f(3, 500, 480, left_wrist=(900.0, 900.0))]  # yanked away before ever bottoming out
        + [_f(4 + k, 500, 480 - 30.0 * k, left_wrist=(900.0, 900.0)) for k in range(8)]  # unrelated fast ascent, far from any wrist
    )
    assert _events(frames) == []


def test_two_frame_plateau_at_wrist_confirms_possession_then_release_fires():
    """A minimal, explicit local-minimum shape: relative velocity strictly
    decreasing over several frames, then a two-frame plateau (delta stops
    shrinking) right at the wrist -- confirms POSSESSION, after which a
    real separating release must fire exactly once."""
    wrist = (500.0, 503.0)
    approach = [
        _f(0, 500, 560, left_wrist=wrist),
        _f(1, 500, 519, left_wrist=wrist),   # delta 41
        _f(2, 500, 505, left_wrist=wrist),   # delta 14
        _f(3, 500, 503, left_wrist=wrist),   # delta 2
        _f(4, 500, 503, left_wrist=wrist),   # delta 0
        _f(5, 500, 503, left_wrist=wrist),   # delta 0 -- plateau vs previous delta: confirms here
    ]
    release = _release(6, 500, 503, 8, wrist_offset=0.0)
    events = _events(approach + release)
    assert len(events) == 1
    assert events[0].path == "strong"


# ================= episode-specific: catch -> settle -> shot =================

def test_catch_settle_shot_survives_multi_frame_noisy_settle():
    """The exact pattern that broke the reverted windowed-median patch: a
    genuine catch (decelerating approach, local minimum reached) followed
    by SEVERAL consecutive frames of small, noisy in-proximity motion (no
    net direction, unlike a clean hold) before the real shot. A fixed-width
    rolling median lagged/couldn't bridge this; POSSESSION has no window at
    all, so it must survive unconditionally as long as proximity holds."""
    wrist = (700.0, 505.0)
    approach = [
        _f(0, 700, 560, left_wrist=wrist),
        _f(1, 700, 519, left_wrist=wrist),   # delta 41
        _f(2, 700, 505, left_wrist=wrist),   # delta 14
        _f(3, 700, 501, left_wrist=wrist),   # delta 4
        _f(4, 700, 499, left_wrist=wrist),   # delta 2
        _f(5, 700, 499, left_wrist=wrist),   # delta 0 -- plateau: confirms here
    ]
    # Noisy settle: small, non-monotonic wobble, all within the 18px band,
    # mirroring the traced real-video run of consecutive small positive
    # (net-downward-looking) samples that defeated a size-3 window.
    settle = [
        _f(6, 700, 500.0, left_wrist=wrist),
        _f(7, 700, 502.0, left_wrist=wrist),
        _f(8, 700, 501.0, left_wrist=wrist),
        _f(9, 700, 503.5, left_wrist=wrist),
        _f(10, 700, 502.5, left_wrist=wrist),
    ]
    release = _release(11, 700, 502.5, 8, wrist_offset=2.5)
    events = _events(approach + settle + release)
    assert len(events) == 1
    assert events[0].path == "strong"
    assert events[0].release_frame >= 11


# ================= episode-specific: round-trip (dribble bounce) rejection =================

def test_repeated_dribble_round_trip_rejected():
    """Same construction as release_event_detector's central repeated-
    dribble regression test: two independent bounce cycles, each with its
    own brief close approach. Under the episode model, a completed
    round-trip (separate then re-approach without ever qualifying as an
    ascent) discards provenance the same way an unambiguous fall does."""
    wrist = (900.0, 900.0)
    frames = []
    frames += _control(0, 500, 500, 4, wrist_offset=3.0)
    frames += [_f(4 + k, 500, 500 + 40.0 * k, left_wrist=(500, 503.0)) for k in range(5)]
    frames += [_f(9 + k, 500, 660 - 30.0 * k, left_wrist=wrist) for k in range(5)]
    frames += [_f(14 + k, 500, 350 + 30.0 * k, left_wrist=wrist) for k in range(4)]
    frames += [_f(18 + k, 500, 470 - 30.0 * k, left_wrist=wrist) for k in range(6)]
    assert _events(frames) == []


def test_false_local_min_at_dribble_touch_bottom_does_not_enable_unrelated_bounce_ascent():
    """Adversarial worst case for this architecture: POSSESSION IS
    confirmed at the bottom of an ordinary dribble touch (the ball
    momentarily stops relative to the hand, exactly the shape a genuine
    catch has), immediately followed by a hard push-away, floor bounce, and
    a fast rebound that -- in isolation -- would satisfy the strong ascent
    path for several consecutive frames. The ascent streak must break
    during the (unrelated-to-the-wrist) downward push, discarding
    provenance before the rebound leg ever has a chance to build a false
    streak -- the same continuous-episode invariant the TRANSITION baseline
    relies on, applied at the SEPARATED->ascent-streak boundary."""
    wrist = (500.0, 503.0)
    touch = [
        _f(0, 500, 560, left_wrist=wrist),
        _f(1, 500, 519, left_wrist=wrist),   # delta 41
        _f(2, 500, 505, left_wrist=wrist),   # delta 14
        _f(3, 500, 503, left_wrist=wrist),   # delta 2
        _f(4, 500, 503, left_wrist=wrist),   # delta 0 -- plateau: POSSESSION confirms here
    ]
    push_down = [_f(5 + k, 500, 503 + 40.0 * (k + 1), left_wrist=wrist) for k in range(4)]  # hard push, still nominally near wrist x/y offset but separating fast and downward
    far = (900.0, 900.0)
    rebound_up = [_f(9 + k, 500, 663 - 30.0 * (k + 1), left_wrist=far) for k in range(8)]   # floor bounce, fast rebound, far from any wrist
    events = _events(touch + push_down + rebound_up)
    assert events == []


def test_round_trip_then_fresh_possession_and_real_release_fires_once():
    """The ball separates from a confirmed POSSESSION without ever
    qualifying as an ascent, and returns (a round trip) -- provenance is
    discarded, but the FRESH approach that follows must still be able to
    confirm its own POSSESSION and authorize a later, genuinely separate
    release."""
    wrist = (500.0, 505.0)
    control = _control(0, 500, 500, 6, wrist_offset=5.0)
    # Drifts sideways-and-slightly-down, never qualifying (small positive
    # vvel, well under any ascent threshold), then returns.
    drift_away = [
        _f(6, 530, 505, left_wrist=wrist),   # separated (30px horizontal), vvel modest
        _f(7, 545, 508, left_wrist=wrist),   # still separated, still not ascending
    ]
    drift_back = [
        _f(8, 515, 505, left_wrist=wrist),   # returning
        _f(9, 500, 503, left_wrist=wrist),   # back within proximity -- round trip complete
        _f(10, 500, 503, left_wrist=wrist),  # plateau -- fresh POSSESSION confirms
    ]
    real = _release(11, 500, 503, 8, wrist_offset=2.0)
    events = _events(control + drift_away + drift_back + real)
    assert len(events) == 1
    assert events[0].path == "strong"
    assert events[0].release_frame >= 11


# ================= episode-specific: dribble -> gather -> shot =================

def test_dribble_gather_shot_fires_once_on_real_shot_not_on_dribbles():
    """Two ordinary dribble bounces (round trips, far from the wrist for
    most of each cycle) followed by a genuine gather (settle into
    POSSESSION) and a real shot -- exactly one candidate, on the shot."""
    wrist = (900.0, 900.0)
    frames = []
    frames += _control(0, 500, 500, 4, wrist_offset=3.0)
    frames += [_f(4 + k, 500, 500 + 40.0 * k, left_wrist=(500, 503.0)) for k in range(5)]
    frames += [_f(9 + k, 500, 660 - 30.0 * k, left_wrist=wrist) for k in range(5)]
    frames += [_f(14 + k, 500, 350 + 30.0 * k, left_wrist=wrist) for k in range(4)]
    frames += [_f(18 + k, 500, 470 - 30.0 * k, left_wrist=wrist) for k in range(6)]
    last_y = frames[-1].ball_y
    gather = _control(24, 500, last_y, 8, wrist_offset=4.0)
    shot = _release(32, 500, last_y, 8, wrist_offset=4.0)
    events = _events(frames + gather + shot)
    assert len(events) == 1
    assert events[0].path == "strong"
    assert events[0].release_frame >= 32


def test_genuine_sustained_fall_no_return_no_candidate():
    """A real drop -- the ball separates from a confirmed POSSESSION,
    falls away, and never returns to proximity and never qualifies as an
    ascent. No candidate."""
    wrist = (500.0, 404.0)
    control = _control(0, 500, 400, 6, wrist_offset=4.0)
    fall = [_f(6 + k, 500, 400 + 25.0 * (k + 1), left_wrist=wrist) for k in range(6)]
    assert _events(control + fall) == []
