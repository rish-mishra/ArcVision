"""Top-level session summary shown at the head of the dashboard."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.analytics.consistency import ConsistencyResult, most_consistent_metrics
from app.analytics.makes_vs_misses import MakesVsMissesReport, top_differentiators
from app.analytics.shot_record import ShotRecord
from app.analytics.stats_utils import mean
from app.events.outcome_detector import ShotOutcome


@dataclass
class SessionSummary:
    total_shots_detected: int
    made: int
    missed: int
    unknown: int
    excluded: int
    shooting_percentage: Optional[float]
    session_duration_sec: float
    mean_pose_quality: Optional[float]
    mean_ball_track_quality: Optional[float]
    hoop_confidence: Optional[float]
    strongest_consistency_label: Optional[str]
    biggest_differentiator_label: Optional[str]
    warnings: List[str]


def compute_session_summary(shots: List[ShotRecord], consistency_results: List[ConsistencyResult],
                              makes_vs_misses: MakesVsMissesReport) -> SessionSummary:
    usable = [s for s in shots if not s.excluded_from_analysis]
    made = sum(1 for s in usable if s.outcome == ShotOutcome.MADE)
    missed = sum(1 for s in usable if s.outcome == ShotOutcome.MISSED)
    unknown = sum(1 for s in usable if s.outcome == ShotOutcome.UNKNOWN)
    excluded = len(shots) - len(usable)

    classified = made + missed
    shooting_pct = round(100.0 * made / classified, 1) if classified > 0 else None

    duration = max((s.end_time_sec for s in shots), default=0.0)

    pose_qualities = [s.pose_quality for s in usable if s.pose_quality > 0]
    ball_qualities = [s.ball_track_quality for s in usable if s.ball_track_quality > 0]
    hoop_confidences = [s.hoop_confidence for s in shots]

    warnings = []
    if unknown > 0:
        warnings.append(f"{unknown} shot(s) could not be confidently classified as made or missed.")
    if excluded > 0:
        warnings.append(f"{excluded} shot(s) were excluded from analysis due to low detection confidence.")
    if hoop_confidences and mean(hoop_confidences) is not None and mean(hoop_confidences) < 0.4:
        warnings.append("Hoop location confidence was low for this session; outcome detection may be unreliable.")

    top_consistent = most_consistent_metrics(consistency_results, top_n=1)
    strongest_label = None
    if top_consistent:
        c = top_consistent[0]
        strongest_label = f"{c.label} (CV={c.coefficient_of_variation})"

    top_diff = top_differentiators(makes_vs_misses, top_n=1)
    biggest_label = None
    if top_diff:
        d = top_diff[0]
        biggest_label = f"{d.metric_name} (effect size={d.effect_size}, {d.effect_label})"

    return SessionSummary(
        total_shots_detected=len(shots),
        made=made, missed=missed, unknown=unknown, excluded=excluded,
        shooting_percentage=shooting_pct,
        session_duration_sec=round(duration, 1),
        mean_pose_quality=round(mean(pose_qualities), 3) if pose_qualities else None,
        mean_ball_track_quality=round(mean(ball_qualities), 3) if ball_qualities else None,
        hoop_confidence=round(mean(hoop_confidences), 3) if hoop_confidences else None,
        strongest_consistency_label=strongest_label,
        biggest_differentiator_label=biggest_label,
        warnings=warnings,
    )
