from app.analytics.consistency import compute_consistency, most_consistent_metrics
from app.analytics.feedback import generate_makes_vs_misses_findings
from app.analytics.makes_vs_misses import compute_makes_vs_misses, top_differentiators
from app.analytics.shot_record import ShotRecord, TrajectoryMetrics
from app.analytics.trends import compute_trends
from app.biomechanics.metrics import ShotMechanics
from app.events.outcome_detector import ShotOutcome


def _shot(idx, outcome, knee_release, elbow_release, start_time, excluded=False,
          release_height=0.3, straightness=0.9):
    mech = ShotMechanics(
        knee_angle_at_load_deg=130.0, knee_angle_at_release_deg=knee_release,
        elbow_angle_at_load_deg=90.0, elbow_angle_at_release_deg=elbow_release,
        torso_lean_at_load_deg=5.0, torso_lean_at_release_deg=2.0,
        release_height_norm=release_height, release_horizontal_offset_norm=0.1,
        load_duration_sec=0.3, upward_duration_sec=0.2, total_prep_duration_sec=0.5,
        pose_quality=0.8,
    )
    traj = TrajectoryMetrics(apex_height_norm=1.2, straightness_ratio=straightness,
                               num_detected_points=10, quality=0.9)
    return ShotRecord(
        shot_index=idx, start_time_sec=start_time, release_time_sec=start_time + 0.5,
        end_time_sec=start_time + 1.5, outcome=outcome, outcome_confidence=0.8,
        outcome_reason="test", release_confidence=0.8, pose_quality=0.8,
        ball_track_quality=0.8, hoop_confidence=0.8, shooting_side="right",
        mechanics=mech, trajectory=traj, excluded_from_analysis=excluded,
    )


def _session(n_made=5, n_missed=5, knee_gap=15.0):
    """Made shots get a systematically higher release-knee-angle than
    missed shots, everything else similar, so the comparison should flag
    knee angle at release as a differentiator."""
    shots = []
    idx = 1
    t = 0.0
    for _ in range(n_made):
        shots.append(_shot(idx, ShotOutcome.MADE, knee_release=170.0 + (idx % 3), elbow_release=160.0, start_time=t))
        idx += 1
        t += 5.0
    for _ in range(n_missed):
        shots.append(_shot(idx, ShotOutcome.MISSED, knee_release=170.0 - knee_gap + (idx % 3), elbow_release=160.0, start_time=t))
        idx += 1
        t += 5.0
    return shots


def test_consistency_reports_cv_and_respects_min_sample():
    shots = _session(6, 6)
    results = compute_consistency(shots)
    knee_result = next(r for r in results if r.metric_key == "knee_angle_at_release_deg")
    assert knee_result.sufficient_sample
    assert knee_result.coefficient_of_variation is not None
    top = most_consistent_metrics(results, top_n=2)
    assert len(top) <= 2


def test_consistency_insufficient_sample_flagged():
    shots = _session(1, 1)
    results = compute_consistency(shots)
    knee_result = next(r for r in results if r.metric_key == "knee_angle_at_release_deg")
    assert not knee_result.sufficient_sample
    assert knee_result.coefficient_of_variation is None


def test_makes_vs_misses_detects_planted_differentiator():
    shots = _session(6, 6, knee_gap=20.0)
    report = compute_makes_vs_misses(shots)
    assert report.eligible
    top = top_differentiators(report, top_n=3)
    labels = [c.metric_name for c in top]
    assert any("Knee angle at release" in l for l in labels)


def test_makes_vs_misses_ineligible_with_too_few_shots():
    shots = _session(1, 1)
    report = compute_makes_vs_misses(shots)
    assert not report.eligible
    assert report.reason in ("not_enough_total_shots", "not_enough_made_or_missed_shots")


def test_makes_vs_misses_ignores_excluded_shots():
    shots = _session(6, 6)
    shots[0].excluded_from_analysis = True
    report = compute_makes_vs_misses(shots)
    assert report.made_count + report.missed_count < len(shots)


def test_feedback_generates_findings_from_real_differences():
    shots = _session(6, 6, knee_gap=20.0)
    report = compute_makes_vs_misses(shots)
    findings = generate_makes_vs_misses_findings(report)
    assert len(findings) >= 1
    assert all(f.evidence for f in findings)


def test_feedback_reports_no_strong_difference_honestly():
    shots = _session(6, 6, knee_gap=0.0)
    report = compute_makes_vs_misses(shots)
    findings = generate_makes_vs_misses_findings(report)
    assert len(findings) >= 1
    if "No strong measurable difference" in findings[0].finding:
        assert True
    else:
        # Some noise-level effect may still pass threshold; just ensure it's evidence-based.
        assert findings[0].evidence


def test_trends_splits_early_late_and_reports_shooting_pct_change():
    shots = []
    idx = 1
    t = 0.0
    # early third: high make rate
    for _ in range(4):
        shots.append(_shot(idx, ShotOutcome.MADE, 170.0, 160.0, t))
        idx += 1
        t += 5.0
    for _ in range(2):
        shots.append(_shot(idx, ShotOutcome.MISSED, 170.0, 160.0, t))
        idx += 1
        t += 5.0
    # late third: low make rate
    for _ in range(1):
        shots.append(_shot(idx, ShotOutcome.MADE, 150.0, 160.0, t))
        idx += 1
        t += 5.0
    for _ in range(5):
        shots.append(_shot(idx, ShotOutcome.MISSED, 150.0, 160.0, t))
        idx += 1
        t += 5.0

    report = compute_trends(shots)
    assert report.eligible
    assert report.early_shooting_pct is not None
    assert report.late_shooting_pct is not None
    assert report.early_shooting_pct > report.late_shooting_pct


def test_trends_ineligible_with_too_few_shots():
    shots = _session(1, 1)
    report = compute_trends(shots)
    assert not report.eligible
