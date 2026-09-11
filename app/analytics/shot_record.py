"""
The shot-level data model. Every other analytics module (session summary,
consistency, makes-vs-misses, trends, feedback) operates on a list of
ShotRecord, so this is the contract that keeps them all decoupled from the
detection/tracking/event internals that produced each shot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.biomechanics.geometry import straightness_ratio
from app.biomechanics.metrics import ShotMechanics
from app.events.outcome_detector import OutcomeResult, ShotOutcome
from app.events.release_detector import ReleaseEstimate
from app.events.shot_state_machine import ShotWindow
from app.vision.types import BallObservation, Confidence, DataSource


@dataclass
class TrajectoryMetrics:
    apex_height_norm: Optional[float] = None
    straightness_ratio: Optional[float] = None
    num_detected_points: int = 0
    num_interpolated_points: int = 0
    num_predicted_points: int = 0
    quality: float = 0.0
    warnings: List[str] = field(default_factory=list)


@dataclass
class ShotRecord:
    shot_index: int
    start_time_sec: float
    release_time_sec: Optional[float]
    end_time_sec: float

    outcome: ShotOutcome
    outcome_confidence: float
    outcome_reason: str

    release_confidence: float
    pose_quality: float
    ball_track_quality: float
    hoop_confidence: float

    shooting_side: Optional[str]
    mechanics: ShotMechanics
    trajectory: TrajectoryMetrics

    warnings: List[str] = field(default_factory=list)
    excluded_from_analysis: bool = False
    exclusion_reason: Optional[str] = None
    # Rich, per-outcome diagnostic detail from the outcome detector (phase
    # points, apex frame, tight/wide band sizes, deflection frame, etc.) --
    # kept here rather than only in the transient OutcomeResult so it's
    # visible in the stored session/shot JSON, not just in-process.
    outcome_evidence: dict = field(default_factory=dict)

    @property
    def overall_confidence_level(self) -> Confidence:
        score = min(self.release_confidence, self.pose_quality, self.ball_track_quality)
        return Confidence.from_score(score)

    @property
    def duration_sec(self) -> float:
        return round(self.end_time_sec - self.start_time_sec, 3)


def _trajectory_metrics(flight_points: List[BallObservation], release_point: Optional[BallObservation],
                         torso_length_px_at_release: Optional[float]) -> TrajectoryMetrics:
    tm = TrajectoryMetrics()
    if not flight_points:
        tm.warnings.append("no_ball_trajectory_during_flight")
        return tm

    for p in flight_points:
        if p.source == DataSource.DETECTED:
            tm.num_detected_points += 1
        elif p.source == DataSource.INTERPOLATED:
            tm.num_interpolated_points += 1
        elif p.source == DataSource.PREDICTED:
            tm.num_predicted_points += 1

    reliable = [p for p in flight_points if p.source in (DataSource.DETECTED, DataSource.INTERPOLATED)]
    total = len(flight_points)
    tm.quality = round(len(reliable) / total, 3) if total else 0.0

    if len(reliable) >= 3:
        pts = [(p.center_x, p.center_y) for p in reliable]
        sr = straightness_ratio(pts)
        tm.straightness_ratio = round(sr, 3) if sr is not None else None
    else:
        tm.warnings.append("insufficient_reliable_points_for_straightness")

    if release_point is not None and torso_length_px_at_release and torso_length_px_at_release > 1e-6 and reliable:
        min_y = min(p.center_y for p in reliable)
        apex_px = release_point.center_y - min_y
        tm.apex_height_norm = round(apex_px / torso_length_px_at_release, 3)
    else:
        tm.warnings.append("apex_height_unavailable")

    return tm


def build_shot_record(shot_index: int, window: ShotWindow, release: Optional[ReleaseEstimate],
                       outcome: OutcomeResult, mechanics: ShotMechanics,
                       shooting_side: Optional[str], ball_track_quality: float,
                       hoop_confidence: float, flight_points: List[BallObservation],
                       release_ball_point: Optional[BallObservation],
                       torso_length_px_at_release: Optional[float],
                       start_time_sec: float, end_time_sec: float,
                       min_pose_quality_to_trust: float = 0.35) -> ShotRecord:
    trajectory = _trajectory_metrics(flight_points, release_ball_point, torso_length_px_at_release)

    warnings = list(window.warnings)
    excluded, reason = False, None
    if release is None:
        warnings.append("release_could_not_be_estimated")
        excluded, reason = True, "no_release_detected"
    elif mechanics.pose_quality < min_pose_quality_to_trust:
        warnings.append("low_pose_confidence_for_this_shot")

    return ShotRecord(
        shot_index=shot_index,
        start_time_sec=round(start_time_sec, 3),
        release_time_sec=round(release.release_timestamp_sec, 3) if release else None,
        end_time_sec=round(end_time_sec, 3),
        outcome=outcome.outcome,
        outcome_confidence=outcome.confidence,
        outcome_reason=outcome.reason,
        release_confidence=release.confidence if release else 0.0,
        pose_quality=mechanics.pose_quality,
        ball_track_quality=round(ball_track_quality, 3),
        hoop_confidence=hoop_confidence,
        shooting_side=shooting_side,
        mechanics=mechanics,
        trajectory=trajectory,
        warnings=warnings,
        excluded_from_analysis=excluded,
        exclusion_reason=reason,
        outcome_evidence=outcome.evidence,
    )
