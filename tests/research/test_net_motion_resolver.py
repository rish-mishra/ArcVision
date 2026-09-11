"""
Synthetic diagnostic-behavior tests for the SHADOW-ONLY
app/research/net_motion_resolver.py module (docs/NET_MOTION_SHADOW.md).
These test the shadow module only -- not production. No showcase/V4
imagery is used; every fixture is a hand-built synthetic frame sequence
describing one physical/optical behavior. No MADE/MISSED verdict is
computed anywhere in this module or these tests -- only the diagnostic
motion measurements.
"""
import numpy as np

from app.research.net_motion_resolver import BallSample, PersonSample, analyze_net_motion_from_frames
from app.vision.types import HoopLocation

H, W = 300, 400
HOOP = HoopLocation(rim_center_x=200.0, rim_center_y=80.0, rim_radius_px=20.0,
                     confidence=0.9, votes=10, method="test")


def _blank(value=100.0):
    return np.full((H, W), value, dtype=np.uint8)


def test_a_static_rim_net_has_no_motion_evidence():
    frames = [_blank(100), _blank(100), _blank(100)]
    idx = [0, 1, 2]
    ep = analyze_net_motion_from_frames(frames, idx, HOOP)
    assert ep.quality == "measured"
    assert ep.max_relative_motion == 0.0
    assert ep.n_elevated_pairs == 0


def test_b_global_brightness_change_is_not_strong_net_evidence():
    frames = [_blank(100), _blank(150), _blank(150)]
    idx = [0, 1, 2]
    ep = analyze_net_motion_from_frames(frames, idx, HOOP)
    assert ep.quality == "measured"
    # Uniform change affects the net ROI and its controls equally -- the
    # relative ratio must sit at (or essentially at) the no-differential-
    # motion baseline of 1.0, never registering as "elevated" (>1.0).
    assert all(r <= 1.01 for r in ep.relative_motion_series)
    assert ep.n_elevated_pairs == 0


def test_c_global_translation_is_normalized_out():
    """A uniformly shifting textured background (camera pan/shake) produces
    real pixel differences, but the SAME differences in the net ROI as in
    its immediate control neighbors, since a linear ramp pattern shifted by
    a fixed offset changes by a spatially-constant amount almost
    everywhere."""
    yy, xx = np.mgrid[0:H, 0:W]
    ramp1 = ((xx + yy) % 256).astype(np.uint8)
    ramp2 = ((xx + yy + 6) % 256).astype(np.uint8)  # uniform diagonal shift
    frames = [ramp1, ramp2]
    idx = [0, 1]
    ep = analyze_net_motion_from_frames(frames, idx, HOOP)
    assert ep.quality == "measured"
    # Not dramatically elevated -- global motion must not masquerade as
    # localized net/structure motion.
    assert ep.max_relative_motion < 1.5


def test_d_localized_below_rim_deformation_is_detected():
    f1 = _blank(100)
    f2 = _blank(100).copy()
    # Only the net ROI region changes substantially; controls get a small
    # baseline change (so the ratio is well-defined and meaningful).
    net, left, right = _rois_for_test()
    f2[net.y0:net.y1, net.x0:net.x1] = 200
    f2[left.y0:left.y1, left.x0:left.x1] = 102
    f2[right.y0:right.y1, right.x0:right.x1] = 102
    ep = analyze_net_motion_from_frames([f1, f2], [0, 1], HOOP)
    assert ep.quality == "measured"
    assert ep.n_elevated_pairs == 1
    assert ep.max_relative_motion > 10  # clearly, structurally separated from baseline


def test_e_ball_only_motion_is_suppressed_by_masking():
    f1 = _blank(100)
    f2 = _blank(100).copy()
    net, left, right = _rois_for_test()
    # Small baseline motion in controls so the ratio is meaningful.
    f2[left.y0:left.y1, left.x0:left.x1] = 101
    f2[right.y0:right.y1, right.x0:right.x1] = 101
    # A "ball" appears inside the net ROI in frame 2 only.
    ball_cx, ball_cy, ball_r = 200.0, 100.0, 8.0
    yy, xx = np.mgrid[0:H, 0:W]
    ball_disc = ((xx - ball_cx) ** 2 + (yy - ball_cy) ** 2) <= ball_r ** 2
    f2[ball_disc] = 250

    ep_unmasked = analyze_net_motion_from_frames([f1, f2], [0, 1], HOOP)
    ep_masked = analyze_net_motion_from_frames(
        [f1, f2], [0, 1], HOOP,
        ball_by_frame={1: BallSample(frame_index=1, center_x=ball_cx, center_y=ball_cy, radius_px=ball_r)},
    )
    assert ep_unmasked.quality == "measured" and ep_masked.quality == "measured"
    # Without masking, the ball spike inflates net motion well above baseline.
    assert ep_unmasked.n_elevated_pairs == 1
    # With masking, the ball's own contribution is excluded -- net motion
    # falls back toward the (near-zero) background-only level.
    assert ep_masked.net_motion_series[0] < ep_unmasked.net_motion_series[0]
    assert ep_masked.ball_masked_fraction_series[0] > 0.0


def test_f_unrelated_motion_outside_roi_is_ignored():
    f1 = _blank(100)
    f2 = _blank(100).copy()
    f2[0:20, 0:20] = 250  # far corner, nowhere near net or control ROIs
    ep = analyze_net_motion_from_frames([f1, f2], [0, 1], HOOP)
    assert ep.quality == "measured"
    assert ep.net_motion_series[0] == 0.0
    assert ep.control_motion_series[0] == 0.0


def test_g_insufficient_frames_abstains():
    ep = analyze_net_motion_from_frames([_blank()], [0], HOOP)
    assert ep.quality == "insufficient"
    assert ep.reason == "insufficient_frames"


def test_h_missing_or_unreliable_hoop_abstains():
    ep_none = analyze_net_motion_from_frames([_blank(), _blank()], [0, 1], None)
    assert ep_none.quality == "insufficient"
    assert ep_none.reason == "hoop_location_not_reliable"

    low_conf_hoop = HoopLocation(rim_center_x=200.0, rim_center_y=80.0, rim_radius_px=20.0,
                                    confidence=0.05, votes=1, method="test")
    ep_low = analyze_net_motion_from_frames([_blank(), _blank()], [0, 1], low_conf_hoop)
    assert ep_low.quality == "insufficient"
    assert ep_low.reason == "hoop_location_not_reliable"


def _rois_for_test():
    from app.research.net_motion_resolver import _rois
    return _rois(HOOP)


# ---------------------------------------------------------------------------
# Part 2: controlled measurement -- shooter masking (existing person/pose
# geometry) + upgraded ball masking (real detected/interpolated provenance).
# See docs/NET_MOTION_SHADOW.md Part 2.
# ---------------------------------------------------------------------------

def test_part2_a_localized_net_deformation_survives_person_masking():
    net, left, right = _rois_for_test()
    f1 = _blank(100)
    f2 = _blank(100).copy()
    f2[net.y0:net.y1, net.x0:net.x1] = 200
    f2[left.y0:left.y1, left.x0:left.x1] = 102
    f2[right.y0:right.y1, right.x0:right.x1] = 102
    # A person standing well clear of all three ROIs (elsewhere in frame) --
    # must not suppress the genuine net deformation.
    person = {1: PersonSample(frame_index=1, x1=0, y1=200, x2=40, y2=300)}
    ep = analyze_net_motion_from_frames([f1, f2], [0, 1], HOOP, person_by_frame=person)
    assert ep.quality == "measured"
    assert ep.n_elevated_pairs == 1
    assert ep.max_relative_motion > 10


def test_part2_b_person_crossing_control_roi_is_suppressed():
    net, left, right = _rois_for_test()
    f1 = _blank(100)
    f2 = _blank(100).copy()
    # The "person" walks through the right control ROI, producing a large
    # raw change there with no net-region or left-control change at all.
    f2[right.y0:right.y1, right.x0:right.x1] = 250
    person_box = PersonSample(frame_index=1, x1=right.x0, y1=right.y0, x2=right.x1, y2=right.y1)

    ep_unmasked = analyze_net_motion_from_frames([f1, f2], [0, 1], HOOP)
    ep_masked = analyze_net_motion_from_frames([f1, f2], [0, 1], HOOP, person_by_frame={1: person_box})

    assert ep_unmasked.control_motion_series[0] > 50  # dominated by the "person"
    assert ep_masked.control_motion_series[0] < 1.0    # suppressed once masked
    assert ep_masked.person_mask_available_series[0] is True


def test_part2_c_person_crossing_net_roi_is_suppressed():
    net, left, right = _rois_for_test()
    f1 = _blank(100)
    f2 = _blank(100).copy()
    # The "person" (not the net) is what changes inside the net ROI.
    f2[net.y0:net.y1, net.x0:net.x1] = 250
    person_box = PersonSample(frame_index=1, x1=net.x0, y1=net.y0, x2=net.x1, y2=net.y1)

    ep_unmasked = analyze_net_motion_from_frames([f1, f2], [0, 1], HOOP)
    ep_masked = analyze_net_motion_from_frames([f1, f2], [0, 1], HOOP, person_by_frame={1: person_box})

    assert ep_unmasked.net_motion_series[0] > 100
    assert ep_masked.net_motion_series[0] < 1.0


def test_part2_d_ball_through_net_roi_suppressed_with_detected_source():
    net, left, right = _rois_for_test()
    f1 = _blank(100)
    f2 = _blank(100).copy()
    f2[left.y0:left.y1, left.x0:left.x1] = 101
    f2[right.y0:right.y1, right.x0:right.x1] = 101
    ball_cx, ball_cy, ball_r = 200.0, 100.0, 8.0
    yy, xx = np.mgrid[0:H, 0:W]
    ball_disc = ((xx - ball_cx) ** 2 + (yy - ball_cy) ** 2) <= ball_r ** 2
    f2[ball_disc] = 250

    ball = {1: BallSample(frame_index=1, center_x=ball_cx, center_y=ball_cy, radius_px=ball_r, source="detected")}
    ep = analyze_net_motion_from_frames([f1, f2], [0, 1], HOOP, ball_by_frame=ball)
    assert ep.ball_mask_source_series[0] == "detected"
    assert ep.net_motion_series[0] < 1.0  # ball fully masked, no residual net-wide change


def test_part2_e_simultaneous_ball_and_net_deformation_preserves_net_signal():
    net, left, right = _rois_for_test()
    f1 = _blank(100)
    f2 = _blank(100).copy()
    # Genuine net-wide change (structural) ...
    f2[net.y0:net.y1, net.x0:net.x1] = 150
    # ... PLUS a ball passing through part of the same region.
    ball_cx, ball_cy, ball_r = 200.0, 100.0, 8.0
    yy, xx = np.mgrid[0:H, 0:W]
    ball_disc = ((xx - ball_cx) ** 2 + (yy - ball_cy) ** 2) <= ball_r ** 2
    f2[ball_disc] = 250
    f2[left.y0:left.y1, left.x0:left.x1] = 102
    f2[right.y0:right.y1, right.x0:right.x1] = 102

    ball = {1: BallSample(frame_index=1, center_x=ball_cx, center_y=ball_cy, radius_px=ball_r, source="detected")}
    ep = analyze_net_motion_from_frames([f1, f2], [0, 1], HOOP, ball_by_frame=ball)
    # The ball's own contribution is excluded, but the surrounding genuine
    # net-wide change (100 -> 150) must still register as elevated motion.
    assert ep.n_elevated_pairs == 1
    assert 40 < ep.net_motion_series[0] < 60


def test_part2_f_incomplete_person_mask_reports_degraded_evidence():
    f1, f2, f3 = _blank(100), _blank(101), _blank(102)
    # Person data only anchored at frame 0 -- pair (0,1) can fall back to it,
    # but pair (1,2) has no person sample in either of its two frames.
    person = {0: PersonSample(frame_index=0, x1=0, y1=0, x2=5, y2=5)}
    ep = analyze_net_motion_from_frames([f1, f2, f3], [0, 1, 2], HOOP, person_by_frame=person)
    assert ep.person_mask_available_series == [True, False]
    assert ep.n_fully_clean_pairs < ep.n_frame_pairs


def test_part2_g_incomplete_ball_mask_reports_degraded_evidence():
    f1, f2, f3 = _blank(100), _blank(101), _blank(102)
    # Person data complete for both pairs, so ball provenance is the only
    # varying factor in n_fully_clean_pairs here.
    person = {0: PersonSample(frame_index=0, x1=0, y1=0, x2=5, y2=5),
              1: PersonSample(frame_index=1, x1=0, y1=0, x2=5, y2=5),
              2: PersonSample(frame_index=2, x1=0, y1=0, x2=5, y2=5)}
    ball = {
        1: BallSample(frame_index=1, center_x=200, center_y=100, radius_px=8, source="detected"),
        2: BallSample(frame_index=2, center_x=200, center_y=100, radius_px=8, source="interpolated"),
    }
    ep = analyze_net_motion_from_frames([f1, f2, f3], [0, 1, 2], HOOP, ball_by_frame=ball, person_by_frame=person)
    assert ep.ball_mask_source_series == ["detected", "interpolated"]
    assert ep.n_fully_clean_pairs == 1  # only the "detected" pair counts as fully clean


def test_part2_h_static_scene_with_masking_params_still_shows_no_evidence():
    frames = [_blank(100), _blank(100), _blank(100)]
    ball = {1: BallSample(frame_index=1, center_x=200, center_y=100, radius_px=8)}
    person = {2: PersonSample(frame_index=2, x1=0, y1=0, x2=5, y2=5)}
    ep = analyze_net_motion_from_frames(frames, [0, 1, 2], HOOP, ball_by_frame=ball, person_by_frame=person)
    assert ep.quality == "measured"
    assert ep.max_relative_motion == 0.0
    assert ep.n_elevated_pairs == 0
