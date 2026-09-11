"""
Session-trend analysis: splits the session into early/middle/late thirds
(by shot order, not clock time, since rest breaks vary) and compares each
reliable metric's mean between the first and last third, plus the makes
percentage. Never labeled as physiological "fatigue" -- only as an observed
change in measured mechanics/outcome across the session.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.analytics.metric_extractors import METRICS, extract_values
from app.analytics.shot_record import ShotRecord
from app.analytics.stats_utils import mean
from app.config import CONFIG
from app.events.outcome_detector import ShotOutcome


@dataclass
class TrendMetricResult:
    metric_key: str
    label: str
    unit: str
    early_mean: Optional[float]
    late_mean: Optional[float]
    change: Optional[float]
    early_n: int
    late_n: int


@dataclass
class TrendReport:
    eligible: bool
    reason: Optional[str]
    early_shooting_pct: Optional[float]
    late_shooting_pct: Optional[float]
    early_n_classified: int
    late_n_classified: int
    metric_trends: List[TrendMetricResult]


def _shooting_pct(shots: List[ShotRecord]) -> Optional[float]:
    classified = [s for s in shots if s.outcome in (ShotOutcome.MADE, ShotOutcome.MISSED)]
    if not classified:
        return None
    made = sum(1 for s in classified if s.outcome == ShotOutcome.MADE)
    return round(100.0 * made / len(classified), 1)


def compute_trends(shots: List[ShotRecord]) -> TrendReport:
    cfg = CONFIG.analytics
    usable = [s for s in shots if not s.excluded_from_analysis]
    usable = sorted(usable, key=lambda s: s.start_time_sec)

    if len(usable) < cfg.min_shots_for_trend_analysis:
        return TrendReport(False, "not_enough_shots_for_trend_analysis", None, None, 0, 0, [])

    third = max(1, len(usable) // 3)
    early = usable[:third]
    late = usable[-third:]

    metric_trends = []
    for spec in METRICS:
        early_vals = extract_values(early, spec.key)
        late_vals = extract_values(late, spec.key)
        e_mean = mean(early_vals)
        l_mean = mean(late_vals)
        change = (l_mean - e_mean) if (e_mean is not None and l_mean is not None) else None
        metric_trends.append(TrendMetricResult(
            metric_key=spec.key, label=spec.label, unit=spec.unit,
            early_mean=round(e_mean, 3) if e_mean is not None else None,
            late_mean=round(l_mean, 3) if l_mean is not None else None,
            change=round(change, 3) if change is not None else None,
            early_n=len(early_vals), late_n=len(late_vals),
        ))

    early_classified = [s for s in early if s.outcome in (ShotOutcome.MADE, ShotOutcome.MISSED)]
    late_classified = [s for s in late if s.outcome in (ShotOutcome.MADE, ShotOutcome.MISSED)]

    return TrendReport(
        eligible=True, reason=None,
        early_shooting_pct=_shooting_pct(early), late_shooting_pct=_shooting_pct(late),
        early_n_classified=len(early_classified), late_n_classified=len(late_classified),
        metric_trends=metric_trends,
    )
