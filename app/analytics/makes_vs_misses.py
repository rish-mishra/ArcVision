"""
The core "what's different about MY good shots and MY bad shots" analysis.
Compares every reliable metric between confidently-made and
confidently-classified-missed shots, and ranks the differentiators. Shots
with an UNKNOWN outcome are excluded from this comparison entirely (they
simply aren't evidence either way), and the whole analysis is skipped
below a minimum sample size rather than reporting a shaky finding from a
handful of shots.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.analytics.metric_extractors import METRICS, extract_values
from app.analytics.shot_record import ShotRecord
from app.analytics.stats_utils import ComparisonResult, compare_groups
from app.config import CONFIG
from app.events.outcome_detector import ShotOutcome


@dataclass
class MakesVsMissesReport:
    eligible: bool
    reason: Optional[str]
    made_count: int
    missed_count: int
    unknown_count: int
    comparisons: List[ComparisonResult]


def compute_makes_vs_misses(shots: List[ShotRecord]) -> MakesVsMissesReport:
    cfg = CONFIG.analytics
    usable = [s for s in shots if not s.excluded_from_analysis]
    made = [s for s in usable if s.outcome == ShotOutcome.MADE]
    missed = [s for s in usable if s.outcome == ShotOutcome.MISSED]
    unknown = [s for s in usable if s.outcome == ShotOutcome.UNKNOWN]

    if len(usable) < cfg.min_shots_for_makes_vs_misses:
        return MakesVsMissesReport(
            eligible=False, reason="not_enough_total_shots",
            made_count=len(made), missed_count=len(missed), unknown_count=len(unknown),
            comparisons=[],
        )
    if len(made) < cfg.min_makes_for_comparison or len(missed) < cfg.min_misses_for_comparison:
        return MakesVsMissesReport(
            eligible=False, reason="not_enough_made_or_missed_shots",
            made_count=len(made), missed_count=len(missed), unknown_count=len(unknown),
            comparisons=[],
        )

    comparisons = []
    for spec in METRICS:
        made_vals = extract_values(made, spec.key)
        missed_vals = extract_values(missed, spec.key)
        comparisons.append(compare_groups(
            spec.label, made_vals, missed_vals,
            min_n_each=min(cfg.min_makes_for_comparison, cfg.min_misses_for_comparison),
        ))

    return MakesVsMissesReport(
        eligible=True, reason=None,
        made_count=len(made), missed_count=len(missed), unknown_count=len(unknown),
        comparisons=comparisons,
    )


def top_differentiators(report: MakesVsMissesReport, top_n: int = 3) -> List[ComparisonResult]:
    if not report.eligible:
        return []
    valid = [c for c in report.comparisons if c.sufficient_sample and c.effect_size is not None]
    return sorted(valid, key=lambda c: abs(c.effect_size), reverse=True)[:top_n]
