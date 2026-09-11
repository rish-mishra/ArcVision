"""
Tests for app/analytics/coaching.py -- the ArcVision Coach synthesis layer.
Follows the same synthetic-ShotRecord pattern as tests/test_analytics.py
(no CV pipeline is run; ShotRecord/ShotMechanics/TrajectoryMetrics are
constructed directly so each scenario's evidence is fully controlled).
"""
from app.analytics.coaching import build_coaching_summary
from app.analytics.consistency import compute_consistency
from app.analytics.makes_vs_misses import compute_makes_vs_misses
from app.analytics.session_summary import compute_session_summary
from app.analytics.shot_record import ShotRecord, TrajectoryMetrics
from app.biomechanics.metrics import ShotMechanics
from app.events.outcome_detector import ShotOutcome


def _shot(idx, outcome, start_time, knee_release=170.0, elbow_release=160.0,
          release_height=0.3, excluded=False, pose_quality=0.8, ball_track_quality=0.8):
    mech = ShotMechanics(
        knee_angle_at_load_deg=130.0, knee_angle_at_release_deg=knee_release,
        elbow_angle_at_load_deg=90.0, elbow_angle_at_release_deg=elbow_release,
        torso_lean_at_load_deg=5.0, torso_lean_at_release_deg=2.0,
        release_height_norm=release_height, release_horizontal_offset_norm=0.1,
        load_duration_sec=0.3, upward_duration_sec=0.2, total_prep_duration_sec=0.5,
        pose_quality=pose_quality,
    )
    traj = TrajectoryMetrics(apex_height_norm=1.2, straightness_ratio=0.9,
                               num_detected_points=10, quality=0.9)
    return ShotRecord(
        shot_index=idx, start_time_sec=start_time, release_time_sec=start_time + 0.5,
        end_time_sec=start_time + 1.5, outcome=outcome, outcome_confidence=0.8,
        outcome_reason="test", release_confidence=0.8, pose_quality=pose_quality,
        ball_track_quality=ball_track_quality, hoop_confidence=0.8, shooting_side="right",
        mechanics=mech, trajectory=traj, excluded_from_analysis=excluded,
    )


def _coach(shots):
    consistency = compute_consistency(shots)
    mvm = compute_makes_vs_misses(shots)
    summary = compute_session_summary(shots, consistency, mvm)
    return build_coaching_summary(shots, summary, consistency, mvm), consistency, mvm, summary


def test_healthy_session_makes_vs_misses_priority():
    """A planted, large, real makes-vs-misses gap should become the #1
    priority, with cues and evidence, and should also surface in the
    makes-vs-misses section."""
    shots = []
    idx, t = 1, 0.0
    for _ in range(6):
        shots.append(_shot(idx, ShotOutcome.MADE, t, knee_release=170.0 + (idx % 3)))
        idx += 1; t += 5.0
    for _ in range(6):
        shots.append(_shot(idx, ShotOutcome.MISSED, t, knee_release=145.0 + (idx % 3)))
        idx += 1; t += 5.0

    coaching, _, mvm, _ = _coach(shots)
    assert mvm.eligible

    assert coaching.eligible
    assert coaching.priority is not None
    assert coaching.priority.source == "makes_vs_misses"
    assert coaching.priority.confidence in ("medium", "high")
    assert "Knee angle at release" in coaching.priority.metric_label
    assert 1 <= len(coaching.priority.cues) <= 3
    assert all(c.text for c in coaching.priority.cues)
    assert coaching.priority.evidence.detail["made_n"] == 6
    assert coaching.priority.evidence.detail["missed_n"] == 6

    assert coaching.makes_vs_misses_note is not None
    assert coaching.makes_vs_misses_reason is None
    assert coaching.coach_note  # non-empty, human-readable


def test_consistency_fallback_when_no_strong_makes_vs_misses_difference():
    """Makes-vs-misses is eligible (enough makes and misses) but nothing
    differentiates them -- coaching must fall back to the consistency
    signal rather than reporting nothing."""
    shots = []
    idx, t = 1, 0.0
    # High/low pairs alternate WITHIN each outcome, not aligned with it, so
    # both made and missed groups see the same mix of high/low values --
    # real shot-to-shot spread, but no makes-vs-misses correlation.
    heights = [0.1, 0.5, 0.5, 0.1, 0.15, 0.55, 0.55, 0.15, 0.2, 0.5, 0.5, 0.2]
    for i in range(12):
        outcome = ShotOutcome.MADE if i % 2 == 0 else ShotOutcome.MISSED
        shots.append(_shot(idx, outcome, t, knee_release=170.0, elbow_release=160.0,
                             release_height=heights[i]))
        idx += 1; t += 5.0

    coaching, consistency, mvm, _ = _coach(shots)
    assert mvm.eligible  # enough makes (6) and misses (6)

    assert coaching.eligible
    assert coaching.priority is not None
    assert coaching.priority.source == "consistency"
    assert coaching.priority.metric_key == "release_height_norm"
    assert coaching.priority.confidence == "medium"
    assert len(coaching.priority.cues) >= 1
    # A constant metric (CV=0) should be flagged as the strength, distinct
    # from the varying one flagged as priority.
    assert coaching.strength is not None
    assert coaching.strength.metric_key != coaching.priority.metric_key


def test_insufficient_sample_says_so_and_produces_no_priority():
    shots = [
        _shot(1, ShotOutcome.MADE, 0.0),
        _shot(2, ShotOutcome.MISSED, 5.0),
    ]
    coaching, consistency, mvm, _ = _coach(shots)
    assert not mvm.eligible

    assert coaching.eligible  # there ARE usable, well-tracked shots -- just not enough to compare
    assert coaching.priority is None
    assert coaching.strength is None
    assert coaching.makes_vs_misses_reason is not None
    assert coaching.makes_vs_misses_note is None
    assert coaching.consistency_reason is not None
    assert coaching.consistency_note is None
    assert coaching.confidence == "low"
    assert "enough evidence" in coaching.coach_note.lower() or "enough" in coaching.coach_note.lower()


def test_low_pose_and_tracking_quality_abstains():
    shots = []
    idx, t = 1, 0.0
    for _ in range(6):
        shots.append(_shot(idx, ShotOutcome.MADE, t, knee_release=170.0,
                             pose_quality=0.25, ball_track_quality=0.25))
        idx += 1; t += 5.0
    for _ in range(6):
        shots.append(_shot(idx, ShotOutcome.MISSED, t, knee_release=145.0,
                             pose_quality=0.25, ball_track_quality=0.25))
        idx += 1; t += 5.0

    coaching, _, mvm, summary = _coach(shots)
    assert mvm.eligible  # the sample size itself is fine -- it's specifically a quality abstention being tested

    assert not coaching.eligible
    assert coaching.priority is None
    assert coaching.strength is None
    assert "low_tracking_quality" in coaching.data_quality_notes
    assert "quality" in coaching.coach_note.lower()


def test_all_makes_falls_back_to_consistency():
    shots = []
    idx, t = 1, 0.0
    knees = [165.0, 175.0, 168.0, 178.0, 170.0, 180.0, 166.0, 176.0]
    for i in range(8):
        shots.append(_shot(idx, ShotOutcome.MADE, t, knee_release=knees[i]))
        idx += 1; t += 5.0

    coaching, consistency, mvm, _ = _coach(shots)
    assert not mvm.eligible
    assert mvm.reason == "not_enough_made_or_missed_shots"

    assert coaching.eligible
    assert coaching.makes_vs_misses_note is None
    assert coaching.makes_vs_misses_reason == (
        "Not enough confidently-made and confidently-missed shots were detected this session to compare them reliably."
    )
    if coaching.priority is not None:
        assert coaching.priority.source == "consistency"


def test_all_misses_falls_back_to_consistency():
    shots = []
    idx, t = 1, 0.0
    knees = [165.0, 175.0, 168.0, 178.0, 170.0, 180.0, 166.0, 176.0]
    for i in range(8):
        shots.append(_shot(idx, ShotOutcome.MISSED, t, knee_release=knees[i]))
        idx += 1; t += 5.0

    coaching, consistency, mvm, _ = _coach(shots)
    assert not mvm.eligible

    assert coaching.eligible
    assert coaching.makes_vs_misses_note is None
    if coaching.priority is not None:
        assert coaching.priority.source == "consistency"


def test_unknown_heavy_session_still_supports_consistency_coaching():
    """Mostly-UNKNOWN outcomes should sink makes-vs-misses eligibility but
    must not block consistency-based coaching, which doesn't depend on
    outcome at all."""
    shots = []
    idx, t = 1, 0.0
    knees = [160.0, 178.0, 162.0, 176.0, 164.0, 180.0, 161.0, 179.0, 163.0, 177.0]
    for i in range(10):
        outcome = ShotOutcome.UNKNOWN if i < 8 else (ShotOutcome.MADE if i == 8 else ShotOutcome.MISSED)
        shots.append(_shot(idx, outcome, t, knee_release=knees[i]))
        idx += 1; t += 5.0

    coaching, consistency, mvm, _ = _coach(shots)
    assert not mvm.eligible  # only 1 made, 1 missed

    assert coaching.eligible
    assert coaching.priority is not None
    assert coaching.priority.source == "consistency"


def test_deterministic_output_for_identical_input():
    shots = []
    idx, t = 1, 0.0
    for _ in range(6):
        shots.append(_shot(idx, ShotOutcome.MADE, t, knee_release=170.0 + (idx % 3)))
        idx += 1; t += 5.0
    for _ in range(6):
        shots.append(_shot(idx, ShotOutcome.MISSED, t, knee_release=145.0 + (idx % 3)))
        idx += 1; t += 5.0

    coaching1, _, _, _ = _coach(shots)
    coaching2, _, _, _ = _coach(shots)
    assert coaching1 == coaching2


def test_no_data_session_abstains_cleanly():
    coaching, consistency, mvm, summary = _coach([])
    assert not coaching.eligible
    assert coaching.priority is None
    assert coaching.strength is None
    assert "no_usable_shots" in coaching.data_quality_notes
    assert coaching.coach_note
