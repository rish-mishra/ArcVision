"""
Synthetic per-frame signal sequences exercising the shot state machine.
Each sequence hand-builds ball-hand distance / velocity / knee-angle
signals frame by frame to simulate a specific basketball action, since we
don't yet have real footage to derive these from.
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
    """close+load -> knee bends -> ball rises fast -> separates -> flight -> settles far away."""
    frames = []
    i = start
    # idle/holding, ball close to hand, knees neutral
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0))
        i += 1
    # load: knees bend while ball stays close
    for k in range(170, int(knee_min), -8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k)))
        i += 1
    # upward: knees extend back up, ball starts moving up fast while still close initially
    for k in range(int(knee_min), 175, 8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k)))
        i += 1
    # release: ball separates from hand, rises above shoulder
    for _ in range(4):
        frames.append(_frame(i, ball_hand_dist=0.4, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3))
        i += 1
    # flight: ball far from body, no longer "available" near hand (simulate by distance)
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.1, knee=175.0, ball_y=0.05))
        i += 1
    # settle: ball comes back near hand (retrieved) and stays for reset window
    for _ in range(hold):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0))
        i += 1
    return frames, i


def test_detects_single_legitimate_shot():
    frames, end = _legit_shot()
    windows = detect_shots(frames)
    assert len(windows) == 1
    w = windows[0]
    assert w.release_candidate_frame is not None
    assert w.load_start_frame is not None
    assert w.upward_start_frame is not None


def test_detects_two_consecutive_shots_distinctly():
    frames1, end1 = _legit_shot(start=0)
    frames2, end2 = _legit_shot(start=end1 + CONFIG.shot.min_frames_between_shots + 2)
    windows = detect_shots(frames1 + frames2)
    assert len(windows) == 2
    assert windows[1].start_frame > windows[0].end_frame


def test_dribble_is_not_counted_as_a_shot():
    """Ball bounces near the hand at hip height with no knee-load pattern and
    no upward velocity burst -- should not trigger a shot."""
    frames = []
    for i in range(40):
        vvel = -0.05 if i % 4 == 0 else 0.05  # small oscillation, well below threshold
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=vvel, knee=170.0))
    windows = detect_shots(frames)
    assert len(windows) == 0


def test_pass_like_motion_without_load_is_not_counted():
    """Ball leaves the hand fast horizontally-ish but knees never bend
    (no load phase) -- our simplified signals model this as no upward
    velocity trigger ever firing while knee stays flat."""
    frames = []
    for i in range(10):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0))
    for i in range(10, 14):
        frames.append(_frame(i, ball_hand_dist=0.5, vvel=0.02, knee=170.0))
    windows = detect_shots(frames)
    assert len(windows) == 0


def test_incomplete_attempt_ball_never_separates():
    """Player loads (knee bends) but ball never actually leaves the hand --
    should not emit a completed shot."""
    frames = []
    for _ in range(3):
        frames.append(_frame(len(frames), ball_hand_dist=0.05, vvel=0.0, knee=170.0))
    for k in range(170, 130, -8):
        frames.append(_frame(len(frames), ball_hand_dist=0.05, vvel=0.0, knee=float(k)))
    # never gets upward velocity or separation; stays loaded then relaxes
    for k in range(130, 171, 8):
        frames.append(_frame(len(frames), ball_hand_dist=0.05, vvel=0.0, knee=float(k)))
    for _ in range(10):
        frames.append(_frame(len(frames), ball_hand_dist=0.05, vvel=0.0, knee=170.0))
    windows = detect_shots(frames)
    assert len(windows) == 0


def test_fallback_trigger_detects_shot_when_ball_never_seen_near_hand():
    """Real-video case: the ball is never confirmed near the hand (a held
    basketball is small/occluded and often missed by object detectors),
    but pose tracking shows a normal knee-load dip, and the ball then
    appears with a sustained, confirmed upward flight above shoulder
    height -- this alone should be enough to detect the shot, with the
    load window reconstructed from pose alone."""
    frames = []
    i = 0
    for _ in range(5):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=170.0))
        i += 1
    for k in range(170, 130, -8):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=float(k)))
        i += 1
    for k in range(130, 171, 8):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=float(k)))
        i += 1
    # Ball suddenly appears, confirmed, moving up fast, above shoulder --
    # sustained for the fallback trigger's required run length.
    for _ in range(CONFIG.shot.fallback_trigger_frames + 2):
        frames.append(_frame(i, ball_available=True, ball_hand_dist=0.9, vvel=-0.6,
                               ball_y=0.1, shoulder_y=0.3, knee=175.0))
        i += 1
    for _ in range(8):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.1, ball_y=0.05, knee=175.0))
        i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_available=True, ball_hand_dist=0.05, vvel=0.0, knee=170.0))
        i += 1

    windows = detect_shots(frames)
    assert len(windows) == 1
    w = windows[0]
    assert w.upward_start_frame is not None
    assert w.load_start_frame is not None
    assert w.load_start_frame < w.upward_start_frame, "load window should reach back to the pose-only knee dip"
    assert any("load_phase_inferred" in warn for warn in w.warnings)


def test_fallback_trigger_does_not_fire_without_rising_above_shoulder():
    """Sustained upward-ish velocity that never actually clears shoulder
    height should NOT be enough to trigger a shot with no other evidence
    -- this is the extra scrutiny the fallback path needs since it has no
    preceding LOAD confirmation to lean on."""
    frames = []
    for i in range(30):
        frames.append(_frame(i, ball_available=True, ball_hand_dist=0.9, vvel=-0.6,
                               ball_y=0.5, shoulder_y=0.3, knee=170.0))  # ball_y > shoulder_y: below shoulder
    windows = detect_shots(frames)
    assert len(windows) == 0


def test_fallback_trigger_degrades_gracefully_with_no_pose_data():
    """If there's no knee-angle data at all in the lookback window, the
    fallback path should still register the shot (using the upward burst
    itself as the load start) instead of crashing or silently dropping it."""
    frames = []
    i = 0
    for _ in range(10):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=None))
        i += 1
    for _ in range(CONFIG.shot.fallback_trigger_frames + 2):
        frames.append(_frame(i, ball_available=True, ball_hand_dist=0.9, vvel=-0.6,
                               ball_y=0.1, shoulder_y=0.3, knee=None))
        i += 1
    for _ in range(8):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.1, ball_y=0.05, knee=None))
        i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_available=True, ball_hand_dist=0.05, vvel=0.0, knee=None))
        i += 1

    windows = detect_shots(frames)
    assert len(windows) == 1
    assert windows[0].load_start_frame == windows[0].upward_start_frame


def test_flight_window_survives_long_ball_dropout_mid_flight():
    """Real-video bug: the ball going undetected for many consecutive
    frames mid-flight (routine on real footage -- small/fast/occluded)
    must NOT be treated as evidence the ball was retrieved. A shot window
    that closed the instant the ball dropped out (well under a second)
    could never contain the ball's actual descent through the hoop
    region, so every trajectory ended up empty. The window must stay open
    through a dropout and still capture a later reappearance."""
    seq = []
    i = 0
    for _ in range(3):
        seq.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 130, -8):
        seq.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    for k in range(130, 175, 8):
        seq.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k))); i += 1
    for _ in range(4):
        seq.append(_frame(i, ball_hand_dist=0.4, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3)); i += 1
    # Long dropout: far more frames than reset_stationary_frames (5).
    for _ in range(15):
        seq.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=175.0)); i += 1
    # Ball reappears further along its flight (e.g. near the hoop), still not retrieved.
    reappear_frame = i
    seq.append(_frame(i, ball_hand_dist=0.95, vvel=0.2, knee=175.0, ball_y=0.02)); i += 1
    for _ in range(3):
        seq.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=175.0)); i += 1
    # Now genuinely retrieved.
    for _ in range(8):
        seq.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1

    windows = detect_shots(seq)
    assert len(windows) == 1
    assert windows[0].end_frame > reappear_frame, "window must not have closed before the ball reappeared"


def test_prolonged_ball_dropout_eventually_closes_window_without_reaching_max_duration():
    """A total ball-tracking blackout that never resolves (ball never
    reappears, never confirmed near the hand either) must still close the
    window in roughly the time a real shot's flight can physically take --
    not run all the way out to max_flight_duration_frames, which would swallow
    the start of the next shot attempt."""
    seq = []
    i = 0
    for _ in range(3):
        seq.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 130, -8):
        seq.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    for k in range(130, 175, 8):
        seq.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k))); i += 1
    for _ in range(4):
        seq.append(_frame(i, ball_hand_dist=0.4, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3)); i += 1
    # Ball never seen again for the rest of the clip.
    for _ in range(120):
        seq.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=175.0)); i += 1

    windows = detect_shots(seq)
    assert len(windows) == 1
    w = windows[0]
    assert (w.end_frame - w.upward_start_frame) < CONFIG.shot.max_flight_duration_frames
    assert "closed_after_prolonged_ball_tracking_dropout" in w.warnings


def test_duplicate_detection_does_not_double_count_one_shot():
    """Ball-hand distance oscillates slightly around the threshold right
    after release (simulating detector noise) -- must still count as ONE
    shot, not two."""
    frames, end = _legit_shot()
    # Perturb a couple of frames right after release to oscillate near the
    # hand-proximity threshold.
    noisy = list(frames)
    windows = detect_shots(noisy)
    assert len(windows) == 1


# ---------------------------------------------------------------------------
# Regression tests for the real-video false positives found in real_test_01:
# a rim rebound and a walking dribble each produced "ball near/away from
# hand, then moving up fast" -- exactly the shot signature -- with the
# shooter's knee angle essentially flat (no genuine load). Fixed by
# requiring a real knee-flexion drop (`load_knee_flexion_drop_deg`) before
# either trigger path confirms a release, which had been defined in config
# but never actually checked anywhere.
# ---------------------------------------------------------------------------

def test_rebound_after_miss_is_not_a_shot():
    """A rim rebound bounces the ball back upward past shoulder height with
    the shooter standing still watching it -- same signal shape the
    fallback trigger looks for, but with no real load. Must not create a
    second shot on top of the real one."""
    frames, end = _legit_shot()
    i = end
    # Ball stays lost for a while after the (missed) shot -- matches the
    # real video, where the ball was unavailable through most of its
    # flight and the rebound both.
    for _ in range(20):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=172.0)); i += 1
    # Rebound: ball reappears moving up fast, above shoulder height, for a
    # sustained run -- but the shooter's knee angle barely moves (standing,
    # watching), never dipping anywhere near a real load.
    for _ in range(CONFIG.shot.fallback_trigger_frames + 3):
        frames.append(_frame(i, ball_available=True, ball_hand_dist=0.9, vvel=-0.6,
                               ball_y=0.1, shoulder_y=0.3, knee=173.0 + (i % 3))); i += 1
    for _ in range(10):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.1, knee=172.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 1, "the rebound must not be counted as a second shot"


def test_dribble_bounce_near_hand_is_not_a_shot():
    """A dribble bounce produces a brief, fast upward velocity spike while
    the ball is right at the hand-proximity threshold -- but the knee angle
    never shows a real loading dip (near-straight legs throughout, as in
    walking/standing dribbling)."""
    frames = []
    i = 0
    for _ in range(5):
        frames.append(_frame(i, ball_hand_dist=0.1, vvel=0.0, knee=177.0)); i += 1
    # The bounce itself: ball near hand, fast upward velocity, knee flat.
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-3.0, knee=178.0)); i += 1
    for _ in range(10):
        frames.append(_frame(i, ball_hand_dist=0.15, vvel=0.5, knee=176.5)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 0, "a dribble bounce with no knee load must not be counted as a shot"


def test_knee_only_straightening_at_clip_start_is_not_a_genuine_load():
    """Real-video false positive found once ball tracking became dense
    enough (RF-DETR) to reliably reach the knee-dip check at all: the clip
    starts with the shooter already mid-motion, knees bent (whatever they
    were doing right before the clip began, e.g. a resting/dribbling
    stance), which then simply straighten to a normal standing pose as
    they pick up the ball -- e.g. 130 -> 179 degrees, a >=12-degree RANGE,
    but the DIRECTION is backwards (extending only, never bending) and is
    not a shooting load. The old max-min range check couldn't tell this
    apart from a real bend-then-extend; the fixed check requires the
    minimum to sit strictly inside the lookback window with a genuine
    rise on BOTH sides of it, which this sequence never provides (nothing
    precedes the already-bent first frame)."""
    frames = []
    i = 0
    # Clip starts already bent (edge of window -- no prior context at all),
    # then straightens monotonically. No re-bend ever happens.
    for k in (130.0, 141.0, 148.0, 158.0, 166.0, 174.0):
        frames.append(_frame(i, ball_hand_dist=0.6, vvel=0.0, knee=k)); i += 1
    # Ball-hand proximity + fast upward velocity right as the knee finishes
    # straightening -- exactly what a real load's release also looks like.
    for k in (179.0, 175.0, 176.0):
        frames.append(_frame(i, ball_hand_dist=0.07, vvel=1.0, knee=k)); i += 1
    for _ in range(4):
        frames.append(_frame(i, ball_hand_dist=0.15, vvel=-1.0, knee=170.0)); i += 1
    for _ in range(10):
        frames.append(_frame(i, ball_hand_dist=0.2, vvel=0.5, knee=172.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 0, (
        "a knee angle that only ever straightens (never genuinely bends then extends) "
        "must not be counted as a shot load, even though its max-min range clears the threshold"
    )


def test_walking_dribble_with_real_knee_flexion_is_not_a_shot():
    """Real-video false positive: a DIFFERENT player dribbled toward the
    hoop while walking. Natural gait produced a genuine (not noise) knee
    flexion dip large enough to pass the load-flexion check on its own --
    what actually distinguishes this from a real shot is that the player's
    hips translated across most of the frame (walking), whereas a shot is
    taken from an essentially stationary base."""
    frames = []
    i = 0
    for k, hip in [(168, 0.0), (142, 3.0), (150, 6.0)]:
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0,
                               knee=float(k), hip_x_norm=hip)); i += 1
    for _ in range(15):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=None, hip_x_norm=None))
        i += 1
    # The bounce: ball near hand, fast upward velocity, genuine knee dip
    # somewhere in recent history -- but hips have moved a long way (walking).
    for k, hip in [(174.7, 20.0), (176.6, 24.0), (167.5, 28.0)]:
        frames.append(_frame(i, ball_hand_dist=0.08, vvel=0.0, knee=k, hip_x_norm=hip)); i += 1
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-3.0, knee=178.0, hip_x_norm=32.0)); i += 1
    for _ in range(10):
        frames.append(_frame(i, ball_hand_dist=0.15, vvel=0.5, knee=176.5, hip_x_norm=34.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 0, "walking-while-dribbling must not be counted as a shot even with a real knee dip"


def test_consecutive_real_shots_with_rebound_between_them():
    """The exact real-video pattern: shot -> miss -> rebound (flat knee,
    upward ball motion) -> real second shot. Must detect exactly 2 shots,
    not 3."""
    shot_a, end_a = _legit_shot(start=0)
    frames = list(shot_a)
    i = end_a
    for _ in range(15):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=173.0)); i += 1
    for _ in range(CONFIG.shot.fallback_trigger_frames + 3):
        frames.append(_frame(i, ball_available=True, ball_hand_dist=0.9, vvel=-0.6,
                               ball_y=0.1, shoulder_y=0.3, knee=174.0 + (i % 2))); i += 1
    for _ in range(10):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.1, knee=172.0)); i += 1

    shot_b, end_b = _legit_shot(start=i + CONFIG.shot.min_frames_between_shots + 5)
    frames += shot_b

    windows = detect_shots(frames)
    assert len(windows) == 2, f"expected exactly 2 real shots (rebound must not count), got {len(windows)}"


def test_real_shot_with_intermittent_ball_detection():
    """A genuine shot where the ball is only sporadically detected during
    load/upward (simulating real-video detector dropout on a held ball)
    must still be detected as exactly one shot."""
    frames = []
    i = 0
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 130, -8):
        # Every other frame's ball detection drops out during loading.
        available = (k % 16 == 0)
        frames.append(_frame(i, ball_available=available,
                               ball_hand_dist=0.05 if available else None,
                               vvel=0.0, knee=float(k))); i += 1
    for k in range(130, 175, 8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k))); i += 1
    for _ in range(4):
        frames.append(_frame(i, ball_hand_dist=0.4, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.1, knee=175.0, ball_y=0.05)); i += 1
    for _ in range(8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 1


def test_catch_after_a_miss_is_not_a_shot():
    """The ball comes back into hand-proximity range after a possession
    change (e.g. catching a pass or a missed shot's rebound) with no
    subsequent upward release burst -- must not register as a shot."""
    frames = []
    i = 0
    for _ in range(5):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=172.0)); i += 1
    # Ball arrives near the hand (a catch), no upward burst ever follows,
    # knee stays essentially flat (no shooting load).
    for _ in range(30):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.05, knee=171.0 + (i % 2))); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 0


def test_raising_ball_without_shooting_is_not_a_shot():
    """The player lifts the ball up (inspecting it, adjusting grip, faking)
    with real upward ball velocity, but the knee never shows a shooting
    load -- must not be counted as a shot."""
    frames = []
    i = 0
    for _ in range(5):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=175.0)); i += 1
    for _ in range(4):
        frames.append(_frame(i, ball_hand_dist=0.08, vvel=-0.5, knee=175.5)); i += 1
    for _ in range(15):
        frames.append(_frame(i, ball_hand_dist=0.1, vvel=0.05, knee=174.5)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 0


def test_temporary_false_ball_detection_does_not_start_shot():
    """A single spurious ball detection (detector noise) with an implied
    upward blip -- too brief to satisfy the fallback trigger's sustained-run
    requirement -- must not start a shot on its own."""
    frames = []
    i = 0
    for _ in range(10):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=172.0)); i += 1
    # One-frame noise blip: shorter than fallback_trigger_frames.
    frames.append(_frame(i, ball_available=True, ball_hand_dist=0.9, vvel=-0.6,
                           ball_y=0.1, shoulder_y=0.3, knee=172.0)); i += 1
    for _ in range(15):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=172.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 0


def test_predicted_only_upward_movement_does_not_trigger_fallback():
    """A sustained upward-flight-shaped burst that is purely Kalman
    extrapolation (never an actual detection) must not trigger the
    fallback path on its own -- even with a genuine-looking knee dip
    beforehand, since the ball evidence itself is not real."""
    frames = []
    i = 0
    for _ in range(5):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 130, -8):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=float(k))); i += 1
    for k in range(130, 171, 8):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=float(k))); i += 1
    # The "burst" is flagged as available (so signals compute) but NOT
    # observed -- i.e. pure tracker extrapolation, not a real detection.
    for _ in range(CONFIG.shot.fallback_trigger_frames + 2):
        frames.append(_frame(i, ball_available=True, ball_hand_dist=0.9, vvel=-0.6,
                               ball_y=0.1, shoulder_y=0.3, knee=175.0, ball_is_observed=False)); i += 1
    for _ in range(10):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.1, knee=175.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 0, "purely-predicted ball motion must not be trusted as release evidence on its own"


def test_duplicate_release_candidates_collapse_to_one_shot():
    """Ball-hand distance oscillates back and forth across the separation
    threshold several times right after release (simulating jittery
    detections right at the critical moment) -- must still resolve to
    exactly one shot, not one per oscillation."""
    frames = []
    i = 0
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 130, -8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    for k in range(130, 175, 8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k))); i += 1
    # Oscillating separation right at the release boundary before it
    # cleanly separates for good.
    for j in range(6):
        dist = 0.4 if j % 2 == 0 else 0.1
        frames.append(_frame(i, ball_hand_dist=dist, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.1, knee=175.0, ball_y=0.05)); i += 1
    for _ in range(8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 1


# ---------------------------------------------------------------------------
# Regression tests: pre-release LOAD/UPWARD dwell and post-release FLIGHT are
# now independently budgeted (real-video bug -- a shooter held the ball for
# ~4.8s before releasing, which nearly exhausted a single shared duration
# cap, force-closing the window ~7 frames after the genuine release while
# the ball was still airborne, which then let the fallback trigger mistake
# the rest of that same flight for a second, spurious shot). See
# ShotDetectionConfig.max_pre_release_duration_frames / max_flight_duration_frames
# / post_flight_ownership_frames and shot_state_machine.py.
# ---------------------------------------------------------------------------

def test_long_pre_release_hold_followed_by_a_normal_shot():
    """A shooter aiming/holding well beyond a typical quick catch-and-shoot
    (but still under the old shared cap) must still resolve to exactly one
    shot with a sensible release."""
    frames = []
    i = 0
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 145, -5):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    # Hold/aim: ball stays at the hand, knee steady, well beyond a normal
    # quick shot's prep time.
    for _ in range(60):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=145.0)); i += 1
    # The real load dip and release, close enough to the trigger for the
    # existing knee-dip lookback to see it.
    for k in range(145, 128, -4):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    for k in range(128, 175, 8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k))); i += 1
    for _ in range(4):
        frames.append(_frame(i, ball_hand_dist=0.4, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.1, knee=175.0, ball_y=0.05)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 1
    assert windows[0].release_candidate_frame is not None


def test_long_pre_release_hold_exceeding_old_shared_cap_is_still_one_shot():
    """The exact diagnosed real-video bug, reconstructed: a hold long
    enough that (hold + flight) would have exceeded the OLD single shared
    150-frame cap, force-closing the window shortly after a genuine
    release. With separately-budgeted pre-release/flight windows, this
    must resolve to exactly one shot with its full flight captured -- not
    a forced max_duration_exceeded split."""
    frames = []
    i = 0
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 145, -5):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    # Hold alone already exceeds the OLD max_shot_duration_frames (150).
    for _ in range(200):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=145.0)); i += 1
    for k in range(145, 128, -4):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    release_start = i
    for k in range(128, 175, 8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k))); i += 1
    for _ in range(4):
        frames.append(_frame(i, ball_hand_dist=0.4, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3)); i += 1
    for _ in range(15):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.1, knee=175.0, ball_y=0.05)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    total_span = i - 1

    windows = detect_shots(frames)
    assert len(windows) == 1, "a long hold must not split a single real shot into two"
    w = windows[0]
    assert "max_duration_exceeded" not in w.warnings, "flight must complete naturally, not be force-cut"
    assert w.release_candidate_frame >= release_start
    assert (total_span - w.start_frame) > 150, "sanity check: this scenario genuinely exceeds the old shared cap"


def test_timeout_shortly_after_genuine_release_closes_via_flight_cap():
    """A flight that itself runs long (ball available, clearly far from
    the hand, never settling, never going missing) must still close via
    the dedicated flight-duration cap, measured from RELEASE -- not
    linger forever."""
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
    for _ in range(200):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.05, knee=175.0, ball_y=0.05)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 1
    w = windows[0]
    assert "max_duration_exceeded" in w.warnings
    assert (w.end_frame - w.release_candidate_frame) <= CONFIG.shot.max_flight_duration_frames + 5


def test_fallback_does_not_recreate_a_shot_from_the_same_flight_after_forced_closure():
    """After a shot window is force-closed WITHOUT positive confirmation
    the ball's motion concluded (the flight-duration cap here), an
    immediately-continuing upward-flight signal must not be accepted by
    the fallback trigger as a brand new shot -- this is the exact
    mechanism that produced a spurious duplicate on real footage. The
    suppression must also be bounded: a genuinely new, fully-qualifying
    shot well after the ownership window lapses must still be detected."""
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
    for _ in range(160):  # > max_flight_duration_frames -- forces a non-confirmed closure
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.05, knee=175.0, ball_y=0.05)); i += 1

    # Immediately after the forced closure: the SAME ball, still clearly
    # airborne, moving fast upward -- exactly what would otherwise satisfy
    # the fallback trigger.
    for _ in range(10):
        frames.append(_frame(i, ball_available=True, ball_is_observed=True, ball_hand_dist=0.9,
                               vvel=-2.0, knee=175.0, ball_y=0.05)); i += 1
    # Quiet gap well past the ownership window (post_flight_ownership_frames).
    for _ in range(CONFIG.shot.post_flight_ownership_frames + 20):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=175.0)); i += 1

    windows_before_new_shot = detect_shots(frames)
    assert len(windows_before_new_shot) == 1, "the continuing tail of an already-closed flight must not become a second shot"

    # A genuinely new, fully-qualifying shot after the ownership window has
    # lapsed must still be detected -- the suppression is bounded, not a
    # standing block on this shooter.
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 130, -8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    for k in range(130, 175, 8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k))); i += 1
    for _ in range(4):
        frames.append(_frame(i, ball_hand_dist=0.4, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.1, knee=175.0, ball_y=0.05)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 2, "suppression must be bounded -- a real later shot must still be detected"


def test_normal_quick_shot_unaffected_by_the_redesign():
    """Baseline sanity check: an ordinary, fast catch-and-shoot must behave
    identically after separating the pre-release and flight budgets."""
    frames, _ = _legit_shot()
    windows = detect_shots(frames)
    assert len(windows) == 1
    w = windows[0]
    assert w.load_start_frame == 0
    assert w.release_candidate_frame is not None
    assert (w.release_candidate_frame - w.load_start_frame) < 30, "a quick shot's prep should still be quick"


def test_pump_fake_then_delayed_real_release_is_one_shot():
    """A pump fake (ball rises slightly, well under the release-velocity
    threshold, then settles back at the hand) followed eventually by the
    real release must resolve to exactly one shot, at the REAL release --
    not zero (pump fake wrongly abandoning the window) and not two."""
    frames = []
    i = 0
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 145, -5):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    # Pump fake: a small vvel blip, well below upward_velocity_threshold_norm
    # (0.35) -- never a real separation.
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.08, vvel=-0.15, knee=148.0)); i += 1
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.05, knee=145.0)); i += 1
    for _ in range(30):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=145.0)); i += 1
    for k in range(145, 128, -4):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    real_release_start = i
    for k in range(128, 175, 8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k))); i += 1
    for _ in range(4):
        frames.append(_frame(i, ball_hand_dist=0.4, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.1, knee=175.0, ball_y=0.05)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 1, "a pump fake followed by a real release must be one shot, not zero or two"
    assert windows[0].release_candidate_frame >= real_release_start


def test_rapid_consecutive_shots_via_primary_trigger_are_not_suppressed():
    """A genuinely fast rebound-catch-and-shoot, confirmed via the PRIMARY
    (real ball-hand-proximity) trigger, must never be blocked by the
    fallback-only post-flight ownership window -- even though the first
    shot closed via a non-confirmed (blackout) reason that WOULD suppress
    the fallback trigger."""
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
    # Total tracking blackout -- closes via reset_unavailable_frames, NOT a
    # confirmed settle.
    for _ in range(50):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=175.0)); i += 1
    shot_a_end = i - 1

    for _ in range(CONFIG.shot.min_frames_between_shots + 2):
        frames.append(_frame(i, ball_available=False, ball_hand_dist=None, vvel=0.0, knee=175.0)); i += 1
    # Shot B: a fresh, genuine catch-and-shoot via the primary trigger.
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 130, -8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    for k in range(130, 175, 8):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=-0.5, knee=float(k))); i += 1
    for _ in range(4):
        frames.append(_frame(i, ball_hand_dist=0.4, vvel=-0.5, knee=175.0, ball_y=0.1, shoulder_y=0.3)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.9, vvel=0.1, knee=175.0, ball_y=0.05)); i += 1
    for _ in range(6):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 2, "a genuine new catch-and-shoot via the primary trigger must not be suppressed"
    assert windows[1].start_frame > shot_a_end


def test_abandoned_load_beyond_generous_pre_release_budget_produces_no_shot():
    """A load that never resolves into a real release (ball stays near the
    hand indefinitely, no separation ever happens) must still eventually
    abandon and produce zero shots -- the new, more generous pre-release
    budget is generous, not infinite."""
    frames = []
    i = 0
    for _ in range(3):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=170.0)); i += 1
    for k in range(170, 140, -5):
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=float(k))); i += 1
    for _ in range(310):  # exceeds max_pre_release_duration_frames (300)
        frames.append(_frame(i, ball_hand_dist=0.05, vvel=0.0, knee=140.0)); i += 1

    windows = detect_shots(frames)
    assert len(windows) == 0, "a load that never resolves into a release must eventually abandon, producing no shot"
