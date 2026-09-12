"""Regression tests for app.biomechanics.shooting_side.determine_shooting_side.

Covers the visibility-weighting fix: previously a handful of barely-passing
low-visibility samples on one side could outvote many high-visibility
samples on the other side whenever they happened to average out closer to
the ball, causing the same shooter's shooting_side to flip inconsistently
across shots (observed in the frozen demo session: one wrist tracked at
~0.85-0.98 visibility throughout, the other at ~0.16-0.54, yet the old
unweighted mean sometimes still picked the poorly-tracked side).
"""
from app.biomechanics.shooting_side import determine_shooting_side
from app.vision.types import Landmark, PoseFrame


def _pf(frame_index, left_wrist=None, right_wrist=None):
    landmarks = {}
    if left_wrist is not None:
        x, y, vis = left_wrist
        landmarks["left_wrist"] = Landmark(x=x, y=y, z=0.0, visibility=vis)
    if right_wrist is not None:
        x, y, vis = right_wrist
        landmarks["right_wrist"] = Landmark(x=x, y=y, z=0.0, visibility=vis)
    return PoseFrame(frame_index=frame_index, timestamp_sec=frame_index / 30.0, detected=True, landmarks=landmarks)


def test_no_data_returns_none():
    assert determine_shooting_side([], {}, 0, 10) is None


def test_only_low_visibility_data_on_both_sides_still_resolves_to_closer_side():
    # Both sides just barely clear the 0.4 floor -- equal weighting, so this
    # is just an ordinary unweighted comparison; confirms the floor/branch
    # logic still works when there's no confidence asymmetry to exploit.
    frames = [_pf(0, left_wrist=(0.1, 0.1, 0.4), right_wrist=(0.9, 0.9, 0.4))]
    ball = {0: (0.15, 0.15)}
    assert determine_shooting_side(frames, ball, 0, 0) == "left"


def test_low_visibility_outlier_no_longer_drags_its_own_side_off_its_true_value():
    """The failure mode this fix addresses: one side (left) is tracked at
    high visibility (0.9) across most of the window with a genuinely larger
    (farther) distance to the ball, but a couple of barely-passing (0.41
    visibility) low-confidence samples land implausibly close to the ball
    and drag its UNWEIGHTED mean below the other (right) side's consistent,
    all-high-visibility mean -- flipping the decision toward the side that
    is actually farther from the ball on the evidence that matters. The
    visibility-weighted mean must not let those few low-confidence samples
    outweigh the many high-confidence ones on the same side."""
    frames, ball = [], {}
    for i in range(8):
        frames.append(_pf(i, left_wrist=(0.0, 0.0, 0.9)))
        ball[i] = (0.25, 0.0)  # left_wrist distance = 0.25
    frames.append(_pf(8, left_wrist=(0.02, 0.0, 0.41)))  # noisy, barely passes floor
    ball[8] = (0.0, 0.0)  # left_wrist distance = 0.02
    frames.append(_pf(9, left_wrist=(0.02, 0.0, 0.41)))
    ball[9] = (0.0, 0.0)
    for i in range(10, 20):
        frames.append(_pf(i, right_wrist=(0.0, 0.0, 0.9)))
        ball[i] = (0.21, 0.0)  # right_wrist distance = 0.21, consistently

    # Unweighted: left_mean = (8*0.25 + 2*0.02)/10 = 0.204 < right_mean = 0.21
    # -> old code would pick "left", even though left's real (high-confidence)
    # signal (0.25) is farther from the ball than right's (0.21).
    old_left_mean = (8 * 0.25 + 2 * 0.02) / 10
    old_right_mean = 0.21
    assert old_left_mean < old_right_mean, "sanity check on the scenario itself"

    result = determine_shooting_side(frames, ball, 0, 19)
    assert result == "right", (
        "the two low-confidence samples should not be able to drag left's "
        "own mean below right's, reversing which side is really closer"
    )


def test_below_visibility_floor_is_excluded_entirely():
    # right_wrist visibility is below the 0.4 inclusion floor -- must be
    # excluded from the comparison entirely (not merely down-weighted),
    # even though it is numerically closer to the ball.
    frames = [_pf(0, left_wrist=(0.0, 0.0, 0.9), right_wrist=(0.51, 0.51, 0.2))]
    ball = {0: (0.5, 0.5)}
    assert determine_shooting_side(frames, ball, 0, 0) == "left"


def test_one_side_entirely_missing_returns_other_side():
    frames = [_pf(0, left_wrist=(0.5, 0.5, 0.9))]
    ball = {0: (0.5, 0.5)}
    assert determine_shooting_side(frames, ball, 0, 0) == "left"


def test_frames_outside_window_are_ignored():
    frames = [
        _pf(0, left_wrist=(0.0, 0.0, 0.9)),   # outside window
        _pf(5, right_wrist=(0.0, 0.0, 0.9)),  # inside window
    ]
    ball = {0: (0.0, 0.0), 5: (0.0, 0.0)}
    assert determine_shooting_side(frames, ball, 5, 5) == "right"
