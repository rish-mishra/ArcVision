"""
Central registry of every "reliable metric" that consistency analysis,
makes-vs-misses comparison, and trend analysis operate on. Adding a new
comparable metric means adding one entry here -- nothing else needs to
change, which is what keeps those three analytics modules generic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.analytics.shot_record import ShotRecord


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    unit: str  # "deg" | "sec" | "ratio" | "body-lengths"
    getter: Callable[[ShotRecord], Optional[float]]
    lower_is_better: Optional[bool] = None  # None = no universal direction claimed


def _m(shot: ShotRecord):
    return shot.mechanics


METRICS = [
    MetricSpec("knee_angle_at_load_deg", "Knee angle at load (deepest bend)", "deg",
               lambda s: _m(s).knee_angle_at_load_deg),
    MetricSpec("knee_angle_at_release_deg", "Knee angle at release", "deg",
               lambda s: _m(s).knee_angle_at_release_deg),
    MetricSpec("elbow_angle_at_load_deg", "Elbow angle at load", "deg",
               lambda s: _m(s).elbow_angle_at_load_deg),
    MetricSpec("elbow_angle_at_release_deg", "Elbow angle at release", "deg",
               lambda s: _m(s).elbow_angle_at_release_deg),
    MetricSpec("torso_lean_at_load_deg", "Torso lean at load", "deg",
               lambda s: _m(s).torso_lean_at_load_deg),
    MetricSpec("torso_lean_at_release_deg", "Torso lean at release", "deg",
               lambda s: _m(s).torso_lean_at_release_deg),
    MetricSpec("release_height_norm", "Release height (relative to hip, body-lengths)", "body-lengths",
               lambda s: _m(s).release_height_norm),
    MetricSpec("release_horizontal_offset_norm", "Release horizontal offset from shoulder", "body-lengths",
               lambda s: _m(s).release_horizontal_offset_norm),
    MetricSpec("load_duration_sec", "Load phase duration", "sec",
               lambda s: _m(s).load_duration_sec),
    MetricSpec("upward_duration_sec", "Upward-motion duration", "sec",
               lambda s: _m(s).upward_duration_sec),
    MetricSpec("total_prep_duration_sec", "Total prep-to-release duration", "sec",
               lambda s: _m(s).total_prep_duration_sec),
    MetricSpec("apex_height_norm", "Trajectory apex height (body-lengths above release)", "body-lengths",
               lambda s: s.trajectory.apex_height_norm),
    MetricSpec("trajectory_straightness_ratio", "Trajectory straightness (1.0 = perfectly straight)", "ratio",
               lambda s: s.trajectory.straightness_ratio),
]

METRICS_BY_KEY = {m.key: m for m in METRICS}


def extract_values(shots, metric_key: str):
    spec = METRICS_BY_KEY[metric_key]
    values = []
    for s in shots:
        if s.excluded_from_analysis:
            continue
        v = spec.getter(s)
        if v is not None:
            values.append(v)
    return values
