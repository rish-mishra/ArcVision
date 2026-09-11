"""
Physical-unit estimation from the ONE reliable real-world reference this
pipeline has: a regulation basketball rim's inner diameter, 18 inches
(0.4572m / 0.2286m radius) -- see docs/METHODOLOGY.md "Physical-unit
calibration" for the full reasoning behind what is and is not attempted
here.

This is deliberately narrow. A single object's known size gives a
pixels-per-meter ratio that is only valid AT THAT OBJECT'S DEPTH from the
camera -- for any other point in the frame at a different distance from
the camera (a shooter's release point, the ball partway through its arc),
applying the same ratio silently mixes in whatever perspective
foreshortening exists between the two depths, which this single-camera,
uncalibrated setup has no way to measure or correct for. Rather than
produce a number that LOOKS like a real velocity/height/speed but is
actually contaminated by an unknown, unaccounted-for depth error, this
module only ever estimates quantities for points genuinely near the rim's
own depth (within its own vicinity in the frame), and refuses everywhere
else.

Concretely:
  MEASURED: nothing -- there is no ground-truth-verified physical
    measurement anywhere in this pipeline.
  ESTIMATED (rough, single-reference, rim-depth-only): ball speed between
    two genuinely DETECTED (not interpolated/predicted) points that are
    both within the rim's near-vicinity -- see estimate_speed_near_rim().
  NOT RELIABLY RECOVERABLE: release velocity, release height, shot speed
    away from the rim, full shot arc height, entry angle -- all of these
    either span multiple depths (shooter to rim) or occur entirely at the
    shooter's depth, which is NOT the depth this calibration is valid for.
    Do not add these without first solving actual camera calibration
    (e.g. two known-size references at different depths, or a calibration
    checkerboard pass) -- a single rim-diameter reference cannot support
    them, no matter how the pixel math is dressed up.
"""
from __future__ import annotations

from typing import Optional

from app.vision.types import BallObservation, DataSource, HoopLocation

RIM_INNER_RADIUS_METERS = 0.2286  # 18in diameter / 2, regulation


def rim_pixels_per_meter(hoop: HoopLocation) -> float:
    """Valid ONLY for objects at the rim's own depth from the camera --
    see module docstring. Never apply this scale to a point elsewhere in
    the frame (e.g. the shooter) without a second reference at that
    point's own depth."""
    return hoop.rim_radius_px / RIM_INNER_RADIUS_METERS


def estimate_speed_near_rim(p1: BallObservation, p2: BallObservation, hoop: HoopLocation,
                              cfg) -> Optional[float]:
    """
    Returns an estimated ball speed in meters/second between two ball
    observations, or None if the estimate would not be defensible.

    Requires BOTH points to be DataSource.DETECTED (a real detection, not
    a Kalman guess -- an interpolated/predicted point's position error is
    unknown and would silently corrupt a speed estimate) and BOTH within
    the rim's near-vicinity (the wide interaction zone already used for
    rim-interaction evidence elsewhere in outcome detection -- see
    events/outcome_detector.py), since that is the only region this
    module's single-reference calibration is valid for.
    """
    if p1.source != DataSource.DETECTED or p2.source != DataSource.DETECTED:
        return None

    from app.events.outcome_detector import _in_band, _wide_zone
    avg_radius = (p1.radius_px + p2.radius_px) / 2.0
    band = _wide_zone(hoop, avg_radius, cfg)
    if not (_in_band(p1, hoop, band) and _in_band(p2, hoop, band)):
        return None

    dt = abs(p2.timestamp_sec - p1.timestamp_sec)
    if dt <= 1e-6:
        return None

    dist_px = ((p2.center_x - p1.center_x) ** 2 + (p2.center_y - p1.center_y) ** 2) ** 0.5
    px_per_m = rim_pixels_per_meter(hoop)
    if px_per_m <= 0:
        return None

    dist_m = dist_px / px_per_m
    return dist_m / dt
