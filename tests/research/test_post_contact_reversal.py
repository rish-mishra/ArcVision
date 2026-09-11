"""
Synthetic physical-behavior tests for the SHADOW-ONLY app/research/post_contact_reversal.py
module (docs/POST_CONTACT_REVERSAL_SHADOW.md). These test the shadow module only --
not production. No showcase/V4 timestamps, filenames, or session IDs are used;
every fixture is a hand-built trajectory describing one physical behavior.
"""
from app.research.post_contact_reversal import analyze_post_contact_reversal
from app.vision.types import BallObservation, DataSource, HoopLocation

FPS = 30.0
HOOP = HoopLocation(rim_center_x=500.0, rim_center_y=300.0, rim_radius_px=20.0,
                     confidence=0.9, votes=10, method="test")


def _pt(i, x, y, conf=0.9, source=DataSource.DETECTED):
    return BallObservation(frame_index=i, timestamp_sec=i / FPS, center_x=x, center_y=y,
                             radius_px=8.0, confidence=conf, source=source)


def test_a_clean_downward_make_has_no_reversal():
    pts = [
        _pt(0, 500, 100), _pt(1, 500, 150), _pt(2, 500, 200),
        _pt(3, 500, 250),   # contact: first point within near-rim-height range (>=250)
        _pt(4, 500, 300), _pt(5, 501, 330), _pt(6, 502, 360), _pt(7, 503, 400), _pt(8, 504, 440),
    ]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is False
    assert ep.escape_detected is False
    assert ep.reason == "no_reversal_clean_continuation"
    assert ep.evidence_quality == "strong"
    assert ep.contact_frame == 3


def test_b_rim_entry_then_upward_bounce_and_escape_is_a_reversal():
    pts = [
        _pt(0, 500, 100), _pt(1, 500, 200), _pt(2, 500, 260),
        _pt(3, 500, 300),   # contact
        _pt(4, 500, 330), _pt(5, 502, 345),   # deepest point (max depth)
        _pt(6, 520, 310),   # reversal candidate 1 -- still in wide band
        _pt(7, 580, 270),   # reversal candidate 2 -- leaves wide band AND rises above rim
    ]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is True
    assert ep.escape_detected is True
    assert ep.escape_direction == "lateral_and_upward"
    assert ep.evidence_quality == "strong"
    assert ep.reason == "post_contact_reversal_with_escape"
    assert ep.n_detected_support >= 2
    assert len(ep.reversal_confirm_frames) == 2


def test_c_ordinary_apex_in_band_is_not_mistaken_for_a_reversal():
    """The trajectory's global apex sits horizontally in-band (a flat, near-
    the-rim-line shot) but far above rim height -- ascent-to-apex-to-descent
    must never itself be read as a post-contact reversal. Only descent_pts
    (apex onward) are ever examined, and contact requires near-rim-height
    proximity the apex doesn't have."""
    pts = [
        _pt(0, 500, 250), _pt(1, 500, 180), _pt(2, 500, 120),   # ascent, in-band, nowhere near rim height
        _pt(3, 500, 100),   # apex
        _pt(4, 500, 160), _pt(5, 500, 220),
        _pt(6, 500, 260),   # contact: first descent point within near-rim-height range
        _pt(7, 500, 300), _pt(8, 501, 340), _pt(9, 502, 390), _pt(10, 503, 430),
    ]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is False
    assert ep.reason == "no_reversal_clean_continuation"
    assert ep.contact_frame == 6


def test_d_single_frame_jitter_is_not_enough_evidence():
    pts = [
        _pt(0, 500, 200), _pt(1, 500, 260),
        _pt(2, 500, 300),   # contact
        _pt(3, 500, 320),
        _pt(4, 500, 310),   # one-frame jitter, immediately superseded below
        _pt(5, 500, 340), _pt(6, 500, 370), _pt(7, 500, 410),
    ]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is False
    assert ep.reason == "no_reversal_clean_continuation"


def test_e_interpolated_only_reversal_is_insufficient_evidence():
    pts = [
        _pt(0, 500, 200), _pt(1, 500, 260),
        _pt(2, 500, 300),   # contact
        _pt(3, 500, 330), _pt(4, 502, 345),
        _pt(5, 520, 310, source=DataSource.INTERPOLATED),
        _pt(6, 580, 270, source=DataSource.INTERPOLATED),
    ]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is True   # structurally present...
    assert ep.n_detected_support == 0     # ...but with zero real-detection support
    assert ep.evidence_quality == "insufficient"
    assert ep.reason == "reversal_structurally_present_but_interpolated_only"


def test_f_tiny_bounce_that_still_continues_downward_is_not_rejected():
    pts = [
        _pt(0, 500, 200), _pt(1, 500, 260),
        _pt(2, 500, 300),   # contact
        _pt(3, 505, 330),   # local max 1
        _pt(4, 515, 320), _pt(5, 515, 315),   # tiny 2-point dip
        _pt(6, 500, 345),   # exceeds the earlier max -- supersedes the dip
        _pt(7, 498, 375), _pt(8, 495, 410),   # continues down, ends below rim
    ]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is False
    assert ep.reason == "no_reversal_clean_continuation"


def test_g_wobble_during_a_genuine_make_is_not_falsely_rejected():
    pts = [
        _pt(0, 500, 200), _pt(1, 500, 260),
        _pt(2, 500, 300),   # contact
        _pt(3, 505, 330),
        _pt(4, 515, 322),   # small in-band wobble
        _pt(5, 500, 340),   # supersedes the wobble
        _pt(6, 498, 370), _pt(7, 495, 405),   # settles below, in band -- a make
    ]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is False
    assert ep.escape_detected is False
    assert ep.reason == "no_reversal_clean_continuation"


def test_h_trajectory_disappears_right_after_contact_abstains():
    pts = [
        _pt(0, 500, 100), _pt(1, 500, 180), _pt(2, 500, 230),
        _pt(3, 500, 260),   # contact -- and nothing else observed afterward
    ]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is False
    assert ep.evidence_quality == "insufficient"
    assert ep.reason == "insufficient_post_contact_observation"


def test_no_interaction_region_observed_abstains():
    """Ball never comes within the wide zone of the hoop at all."""
    pts = [_pt(0, 50, 100), _pt(1, 55, 150), _pt(2, 60, 200), _pt(3, 65, 250)]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is False
    assert ep.evidence_quality == "insufficient"
    assert ep.reason == "no_rim_interaction_region_observed"


def test_i_motion_more_than_0_75s_after_contact_cannot_create_reversal():
    """Regression test for the contact-relative scoping correction
    (docs/POST_CONTACT_REVERSAL_SHADOW.md): the reversal/escape scan must be
    bounded to cfg.max_seconds_through_rim (0.75s) of the CONTACT frame, not
    the much looser 2.0s-from-apex bound the original prototype mistakenly
    reused. A dramatic reversal well outside that window (t=0.93s after
    contact here) must never be scanned at all."""
    pts = [
        _pt(0, 500, 200), _pt(1, 500, 260),
        _pt(2, 500, 300),   # contact, t=0.0667s
        _pt(3, 500, 330),   # dt=0.033s
        _pt(10, 500, 400),  # dt=0.267s
        _pt(20, 500, 500),  # dt=0.6s -- still within the 0.75s window
        _pt(28, 500, 350),  # dt=0.867s -- a reversal relative to the local max (500), but OUTSIDE
                             # the window and still well below the true apex (200), so it can't
                             # itself get mistaken for the apex; must be excluded from the scan
    ]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is False
    assert ep.reason == "no_reversal_clean_continuation"


def test_j_ordinary_post_make_floor_bounce_outside_window_does_not_count():
    """A clean pass-through the rim, well below and away from it by the time
    the ball leaves the interaction window -- then, much later (a real
    floor bounce, far outside any plausible rim-contact timescale), the
    ball's height rises again. That later bounce must not be read as rim
    reversal evidence."""
    pts = [
        _pt(0, 500, 200), _pt(1, 500, 260),
        _pt(2, 500, 300),   # contact, t=0.0667s
        _pt(5, 500, 400),   # dt=0.1s
        _pt(10, 505, 500),  # dt=0.267s -- clearly below and away, a genuine make continuing down
        _pt(18, 508, 600),  # dt=0.533s -- still within window, still descending
        _pt(35, 510, 350),  # dt=1.1s -- a real floor bounce, far outside the window
    ]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is False
    assert ep.reason == "no_reversal_clean_continuation"


def test_interaction_but_never_reaches_contact_proximity_abstains():
    """Ball passes through the wide zone but never gets close/low enough to
    count as genuine rim-height contact."""
    pts = [_pt(0, 500, 50), _pt(1, 500, 70), _pt(2, 500, 90), _pt(3, 500, 110)]
    ep = analyze_post_contact_reversal(pts, HOOP)
    assert ep.reversal_detected is False
    assert ep.evidence_quality == "insufficient"
    assert ep.reason == "no_contact_level_proximity_observed"
