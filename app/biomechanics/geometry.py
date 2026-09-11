"""
Pure geometric helpers used to turn raw landmark/detection coordinates into
angles and body-relative distances. Nothing in this module touches a video,
a model, or I/O -- it is deterministic math and is unit-tested directly.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

Point = Tuple[float, float]


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def angle_deg(a: Point, b: Point, c: Point) -> Optional[float]:
    """Angle ABC (at vertex b), in degrees, in [0, 180]. None if degenerate."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return None
    cos_theta = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return math.degrees(math.acos(cos_theta))


def elbow_angle(shoulder: Point, elbow: Point, wrist: Point) -> Optional[float]:
    """180 degrees = fully extended arm, smaller = more bent."""
    return angle_deg(shoulder, elbow, wrist)


def knee_angle(hip: Point, knee: Point, ankle: Point) -> Optional[float]:
    """180 degrees = fully extended leg, smaller = more bent (loaded)."""
    return angle_deg(hip, knee, ankle)


def torso_lean_deg(shoulder_mid: Point, hip_mid: Point) -> Optional[float]:
    """
    Angle of the torso line (hip->shoulder) from vertical, in degrees.
    0 = perfectly upright. Sign: positive leans toward +x (image right).
    """
    dx = shoulder_mid[0] - hip_mid[0]
    dy = hip_mid[1] - shoulder_mid[1]  # image y grows downward; want "up" positive
    if abs(dy) < 1e-9 and abs(dx) < 1e-9:
        return None
    return math.degrees(math.atan2(dx, dy))


def midpoint(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def torso_length(shoulder_mid: Point, hip_mid: Point) -> float:
    return distance(shoulder_mid, hip_mid)


def normalize_by_torso(value_px: float, torso_len_px: float) -> Optional[float]:
    """Convert a pixel distance to a body-relative unit (fraction of torso length)."""
    if torso_len_px is None or torso_len_px < 1e-6:
        return None
    return value_px / torso_len_px


def vertical_velocity(p_prev: Point, p_curr: Point, dt: float) -> Optional[float]:
    """Signed vertical velocity in px/sec, negative = moving up (image coords)."""
    if dt <= 0:
        return None
    return (p_curr[1] - p_prev[1]) / dt


def path_length(points) -> float:
    total = 0.0
    for i in range(1, len(points)):
        total += distance(points[i - 1], points[i])
    return total


def straightness_ratio(points) -> Optional[float]:
    """
    1.0 = perfectly straight path; lower values indicate a wobblier path.
    Ratio of straight-line displacement to total traveled path length.
    """
    if len(points) < 2:
        return None
    total = path_length(points)
    if total < 1e-9:
        return None
    direct = distance(points[0], points[-1])
    return direct / total
