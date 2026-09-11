from app.tracking.kalman_tracker import SingleObjectTracker
from app.tracking.hoop_aggregator import aggregate_hoop_candidates
from app.vision.types import DataSource


def _run(tracker, detections):
    """detections: list of (frame_index, ts, (x,y) or None, conf)"""
    out = []
    for frame_index, ts, xy, conf in detections:
        out.append(tracker.step(frame_index, ts, xy, conf))
    return out


def test_tracker_follows_moving_detection():
    tracker = SingleObjectTracker(max_age_frames=12, max_center_jump_px=140, max_extrapolation_frames=6)
    dets = [(i, i / 30.0, (10.0 + i * 2, 20.0), 0.9) for i in range(10)]
    pts = _run(tracker, dets)
    for p in pts:
        assert p.source == DataSource.DETECTED
    assert pts[-1].x > pts[0].x


def test_tracker_bridges_short_gap_as_interpolated_or_predicted():
    tracker = SingleObjectTracker(max_age_frames=12, max_center_jump_px=140, max_extrapolation_frames=6)
    dets = [(0, 0.0, (10.0, 20.0), 0.9), (1, 1/30, (12.0, 20.0), 0.9)]
    _run(tracker, dets)
    # Now three missed frames (short gap) -- should bridge, not go unavailable.
    missed = [(2, 2/30, None, 0.0), (3, 3/30, None, 0.0), (4, 4/30, None, 0.0)]
    pts = _run(tracker, missed)
    for p in pts:
        assert p.source in (DataSource.INTERPOLATED, DataSource.PREDICTED)


def test_tracker_marks_unavailable_after_long_gap():
    tracker = SingleObjectTracker(max_age_frames=12, max_center_jump_px=140, max_extrapolation_frames=3)
    _run(tracker, [(0, 0.0, (10.0, 20.0), 0.9)])
    missed = [(i, i/30, None, 0.0) for i in range(1, 10)]
    pts = _run(tracker, missed)
    assert pts[-1].source == DataSource.UNAVAILABLE


def test_tracker_rejects_implausible_jump():
    tracker = SingleObjectTracker(max_age_frames=12, max_center_jump_px=50, max_extrapolation_frames=6)
    _run(tracker, [(0, 0.0, (10.0, 20.0), 0.9), (1, 1/30, (11.0, 20.0), 0.9)])
    # A detection that teleports across the frame should not be trusted as-is.
    pt = tracker.step(2, 2/30, (900.0, 900.0), 0.9)
    assert pt.source != DataSource.DETECTED


def test_tracker_no_detection_ever_is_unavailable():
    tracker = SingleObjectTracker()
    pt = tracker.step(0, 0.0, None, 0.0)
    assert pt.source == DataSource.UNAVAILABLE


def test_hoop_aggregator_clusters_and_scores_confidence():
    candidates = [
        (0, 100.0, 50.0, 20.0, 0.6, "classical"),
        (1, 102.0, 51.0, 21.0, 0.5, "classical"),
        (2, 98.0, 49.0, 19.0, 0.7, "classical"),
        (3, 500.0, 500.0, 15.0, 0.3, "classical"),  # outlier / noise cluster
    ]
    hoop = aggregate_hoop_candidates(candidates)
    assert hoop is not None
    assert abs(hoop.rim_center_x - 100.0) < 10
    assert hoop.votes == 3
    assert hoop.confidence > 0


def test_hoop_aggregator_empty_returns_none():
    assert aggregate_hoop_candidates([]) is None


def test_hoop_aggregator_counts_distinct_frames_not_raw_candidates():
    """A real-video bug: a moving false-positive object producing two
    near-duplicate high-confidence boxes within the SAME couple of frames
    must not outscore a true static hoop seen once per frame across many
    more distinct frames."""
    candidates = [
        # True hoop: one (lower-confidence) candidate per frame, 5 distinct frames.
        (0, 100.0, 50.0, 20.0, 0.02, "learned"),
        (10, 101.0, 51.0, 20.0, 0.02, "learned"),
        (20, 99.0, 50.0, 20.0, 0.02, "learned"),
        (30, 100.0, 49.0, 20.0, 0.02, "learned"),
        (40, 101.0, 50.0, 20.0, 0.02, "learned"),
        # Moving false positive: only 2 distinct frames, but 2 near-duplicate
        # (NMS) boxes each, at high confidence -- 4 raw candidates total.
        (15, 400.0, 300.0, 15.0, 0.17, "learned"),
        (15, 401.0, 300.0, 15.0, 0.15, "learned"),
        (16, 402.0, 301.0, 15.0, 0.16, "learned"),
        (16, 403.0, 301.0, 15.0, 0.14, "learned"),
    ]
    hoop = aggregate_hoop_candidates(candidates)
    assert hoop is not None
    assert abs(hoop.rim_center_x - 100.0) < 10, "the true, more-frequently-observed hoop must win"
    assert hoop.votes == 5


def test_hoop_aggregator_dedupes_multiple_candidates_in_one_frame():
    """Two candidates from the same frame for the same cluster should only
    count as one vote, not two."""
    candidates = [
        (0, 100.0, 50.0, 20.0, 0.5, "classical"),
        (0, 101.0, 51.0, 20.0, 0.6, "learned"),  # same frame, same physical rim
    ]
    hoop = aggregate_hoop_candidates(candidates)
    assert hoop is not None
    assert hoop.votes == 1


def test_hoop_aggregator_method_reflects_contributing_sources():
    candidates = [
        (0, 100.0, 50.0, 20.0, 0.5, "classical"),
        (1, 101.0, 51.0, 20.0, 0.6, "learned"),
        (2, 99.0, 50.0, 20.0, 0.5, "learned"),
    ]
    hoop = aggregate_hoop_candidates(candidates)
    assert hoop is not None
    assert hoop.method == "classical+learned"
