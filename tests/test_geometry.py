import math

from app.biomechanics.geometry import (
    angle_deg, elbow_angle, knee_angle, torso_lean_deg, distance, midpoint,
    normalize_by_torso, straightness_ratio,
)


def test_angle_deg_right_angle():
    a, b, c = (0, 0), (1, 0), (1, 1)
    assert math.isclose(angle_deg(a, b, c), 90.0, abs_tol=1e-6)


def test_angle_deg_straight_line():
    a, b, c = (0, 0), (1, 0), (2, 0)
    assert math.isclose(angle_deg(a, b, c), 180.0, abs_tol=1e-6)


def test_angle_deg_degenerate_returns_none():
    assert angle_deg((0, 0), (0, 0), (1, 1)) is None


def test_elbow_angle_fully_extended():
    shoulder, elbow, wrist = (0, 0), (1, 0), (2, 0)
    assert math.isclose(elbow_angle(shoulder, elbow, wrist), 180.0, abs_tol=1e-6)


def test_knee_angle_bent():
    hip, knee, ankle = (0, 0), (0, 1), (1, 1)
    assert math.isclose(knee_angle(hip, knee, ankle), 90.0, abs_tol=1e-6)


def test_torso_lean_upright_is_zero():
    shoulder_mid, hip_mid = (0.5, 0.2), (0.5, 0.6)
    lean = torso_lean_deg(shoulder_mid, hip_mid)
    assert math.isclose(lean, 0.0, abs_tol=1e-6)


def test_torso_lean_forward_is_nonzero():
    shoulder_mid, hip_mid = (0.6, 0.2), (0.5, 0.6)
    lean = torso_lean_deg(shoulder_mid, hip_mid)
    assert lean is not None and lean > 0


def test_normalize_by_torso():
    assert math.isclose(normalize_by_torso(10.0, 20.0), 0.5)
    assert normalize_by_torso(10.0, 0.0) is None
    assert normalize_by_torso(10.0, None) is None


def test_straightness_ratio_straight_line():
    pts = [(0, 0), (1, 0), (2, 0), (3, 0)]
    assert math.isclose(straightness_ratio(pts), 1.0, abs_tol=1e-6)


def test_straightness_ratio_wobbly_path_is_lower():
    straight = [(0, 0), (1, 0), (2, 0)]
    wobbly = [(0, 0), (1, 1), (2, 0)]
    assert straightness_ratio(wobbly) < straightness_ratio(straight)


def test_distance_and_midpoint():
    assert math.isclose(distance((0, 0), (3, 4)), 5.0)
    assert midpoint((0, 0), (2, 4)) == (1, 2)
