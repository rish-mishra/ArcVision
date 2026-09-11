"""
Unit tests for the near-hoop chain-building mechanism (see
app/vision/detection/near_hoop_enrichment.py), diagnosed and rewritten
while root-causing a real-video false-confident-MISS: the ROI ball
detector's classical (color/circularity) fallback caps every single-frame
candidate at a flat, low confidence in bright/overexposed lighting, so no
fixed per-frame confidence floor can separate genuine ball sightings from
clutter (net wires, backboard edges, fixed background features). These
tests exercise the actual mechanism that does the separating -- seeded,
velocity-gated, multi-frame chaining with a minimum chain length and a
guard against locking onto static clutter -- using synthetic candidates,
never real-video-specific coordinates or expected outcomes.
"""
from app.vision.detection.near_hoop_enrichment import (
    MIN_CHAIN_LENGTH,
    _build_chain_for_shot,
    _observed_max_speed_px_per_sec,
)
from app.vision.types import BallObservation, DataSource, Detection, HoopLocation

HOOP = HoopLocation(rim_center_x=100.0, rim_center_y=100.0, rim_radius_px=15.0,
                     confidence=0.8, votes=6, method="learned")
FPS = 30.0


def _obs(frame, x, y, source=DataSource.DETECTED, conf=0.8):
    return BallObservation(frame_index=frame, timestamp_sec=frame / FPS,
                             center_x=x, center_y=y, radius_px=8.0,
                             confidence=conf, source=source)


def _det(frame, x, y, conf=0.3, size=16.0):
    half = size / 2.0
    return Detection(frame_index=frame, timestamp_sec=frame / FPS,
                       x1=x - half, y1=y - half, x2=x + half, y2=y + half,
                       confidence=conf, class_name="hoop_roi_classical")


def test_no_seed_anchor_means_no_recovery():
    """Without a genuine prior DETECTED/INTERPOLATED point to seed a
    position and velocity from, the chain has nothing trustworthy to
    extend -- it must not invent a starting point from a bare candidate,
    since a static piece of clutter could otherwise seed its own
    self-consistent (but fake) chain."""
    candidates = {f: [_det(f, 90 - f, 90 - f)] for f in range(10, 16)}
    chain = _build_chain_for_shot(10, 16, ball_observations=[], per_frame_candidates=candidates,
                                    hoop=HOOP, max_speed_px_per_sec=500.0)
    assert chain == []


def test_chain_shorter_than_minimum_is_discarded_entirely():
    """Two coincidentally-aligned candidates is not enough to trust as
    real evidence -- a chain must reach MIN_CHAIN_LENGTH before any of its
    points are promoted."""
    seed = _obs(9, 90, 90)
    prior = _obs(8, 95, 95)
    candidates = {10: [_det(10, 85, 85)], 11: [_det(11, 80, 80)]}
    assert MIN_CHAIN_LENGTH > 2
    chain = _build_chain_for_shot(10, 15, ball_observations=[prior, seed], per_frame_candidates=candidates,
                                    hoop=HOOP, max_speed_px_per_sec=500.0)
    assert chain == []


def test_velocity_gated_selection_prefers_trajectory_consistent_candidate():
    """When a frame offers both a candidate consistent with the ball's
    established motion and an unrelated one sitting elsewhere, the chain
    must follow the consistent one, not whichever has the higher raw
    per-frame confidence."""
    prior = _obs(8, 200, 200)
    seed = _obs(9, 180, 180)   # moving at roughly (-20, -20) px/frame = (-600,-600) px/sec
    candidates = {
        10: [_det(10, 160, 160, conf=0.2), _det(10, 400, 50, conf=0.9)],   # clutter has higher confidence
        11: [_det(11, 140, 140, conf=0.2), _det(11, 410, 55, conf=0.9)],
        12: [_det(12, 120, 120, conf=0.2), _det(12, 420, 60, conf=0.9)],
    }
    chain = _build_chain_for_shot(10, 12, ball_observations=[prior, seed], per_frame_candidates=candidates,
                                    hoop=HOOP, max_speed_px_per_sec=2000.0)
    assert len(chain) == 3
    for p in chain:
        assert p.center_x < 200 and p.center_y < 200  # followed the consistent path, not the clutter


def test_static_repeat_run_truncates_the_chain():
    """A candidate that repeats the same pixel position for more than a
    couple of consecutive frames is far more consistent with the detector
    having locked onto a fixed background feature than a ball in flight --
    the chain must stop there rather than keep trusting that position."""
    prior = _obs(8, 200, 200)
    seed = _obs(9, 180, 180)
    candidates = {
        10: [_det(10, 160, 160)],
        11: [_det(11, 140, 140)],
        12: [_det(12, 120, 120)],
        # A static cluster begins here -- same position repeated.
        13: [_det(13, 100.0, 100.0)],
        14: [_det(14, 100.2, 100.1)],
        15: [_det(15, 100.1, 100.0)],
        16: [_det(16, 100.0, 100.2)],
    }
    chain = _build_chain_for_shot(10, 16, ball_observations=[prior, seed], per_frame_candidates=candidates,
                                    hoop=HOOP, max_speed_px_per_sec=2000.0)
    kept_frames = {p.frame_index for p in chain}
    assert 13 not in kept_frames or 16 not in kept_frames, (
        "a long run of a repeated position must not all be trusted as genuine ball motion"
    )


def test_observed_max_speed_uses_only_detected_points():
    """The speed calibration must come from genuine DETECTED consecutive
    pairs only -- an INTERPOLATED (Kalman-guessed) pair says nothing about
    the ball's real observed speed."""
    obs = [
        _obs(0, 0, 0, source=DataSource.DETECTED),
        _obs(1, 100, 0, source=DataSource.DETECTED),   # 100px / (1/30)s = 3000 px/s
        _obs(2, 5000, 5000, source=DataSource.INTERPOLATED),  # must be ignored
    ]
    speed = _observed_max_speed_px_per_sec(obs)
    assert 2900 < speed < 3100
