"""
Tests for the single-reference (regulation rim diameter) physical-unit
estimator. Deliberately narrow in scope -- see
app/biomechanics/rim_calibration.py's module docstring for why this never
attempts release velocity, shot arc, or anything away from the rim's own
depth.
"""
import pytest

from app.biomechanics.rim_calibration import estimate_speed_near_rim, rim_pixels_per_meter
from app.config import CONFIG
from app.vision.types import BallObservation, DataSource, HoopLocation

HOOP = HoopLocation(rim_center_x=100.0, rim_center_y=100.0, rim_radius_px=40.0,
                     confidence=0.8, votes=6, method="learned")


def _pt(frame, x, y, source=DataSource.DETECTED, t=None):
    return BallObservation(frame_index=frame, timestamp_sec=t if t is not None else frame / 30.0,
                             center_x=x, center_y=y, radius_px=8.0, confidence=0.8, source=source)


def test_rim_pixels_per_meter_uses_regulation_18_inch_diameter():
    # 40px radius corresponds to 0.2286m (9in) -- ratio should be px / 0.2286.
    ratio = rim_pixels_per_meter(HOOP)
    assert ratio == pytest.approx(40.0 / 0.2286)


def test_returns_none_when_either_point_is_not_detected():
    p1 = _pt(0, 90, 100, source=DataSource.DETECTED)
    p2 = _pt(1, 110, 100, source=DataSource.INTERPOLATED)
    assert estimate_speed_near_rim(p1, p2, HOOP, CONFIG.outcome) is None


def test_returns_none_when_points_are_far_from_the_rim():
    # Both detected, but nowhere near the rim's vicinity -- the calibration
    # is only valid at the rim's own depth.
    p1 = _pt(0, 900, 900, source=DataSource.DETECTED)
    p2 = _pt(1, 910, 910, source=DataSource.DETECTED)
    assert estimate_speed_near_rim(p1, p2, HOOP, CONFIG.outcome) is None


def test_returns_a_plausible_speed_for_two_genuine_near_rim_points():
    # 30px apart (well within the wide zone), 1/30s apart.
    p1 = _pt(0, 95, 90, source=DataSource.DETECTED, t=0.0)
    p2 = _pt(1, 95, 120, source=DataSource.DETECTED, t=1.0 / 30.0)
    speed = estimate_speed_near_rim(p1, p2, HOOP, CONFIG.outcome)
    assert speed is not None
    px_per_m = rim_pixels_per_meter(HOOP)
    expected = (30.0 / px_per_m) / (1.0 / 30.0)
    assert speed == pytest.approx(expected)


def test_returns_none_for_zero_elapsed_time():
    p1 = _pt(0, 95, 100, source=DataSource.DETECTED, t=1.0)
    p2 = _pt(0, 96, 100, source=DataSource.DETECTED, t=1.0)
    assert estimate_speed_near_rim(p1, p2, HOOP, CONFIG.outcome) is None
