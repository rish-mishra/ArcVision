"""
Shot-to-shot consistency for every reliable metric: how much a metric
varies across the session's shots, using the coefficient of variation
(standard deviation / mean) for angle/timing metrics, which is scale-free
and easy to explain. A metric with very few valid samples is reported as
such rather than given a misleading precise-looking number.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.analytics.metric_extractors import METRICS, extract_values
from app.analytics.shot_record import ShotRecord
from app.analytics.stats_utils import coefficient_of_variation, mean, stdev

MIN_SAMPLES_FOR_CONSISTENCY = 4


@dataclass
class ConsistencyResult:
    metric_key: str
    label: str
    unit: str
    n: int
    mean_value: Optional[float]
    std_dev: Optional[float]
    coefficient_of_variation: Optional[float]
    sufficient_sample: bool


def compute_consistency(shots: List[ShotRecord]) -> List[ConsistencyResult]:
    results = []
    for spec in METRICS:
        values = extract_values(shots, spec.key)
        sufficient = len(values) >= MIN_SAMPLES_FOR_CONSISTENCY
        results.append(ConsistencyResult(
            metric_key=spec.key,
            label=spec.label,
            unit=spec.unit,
            n=len(values),
            mean_value=round(mean(values), 3) if values else None,
            std_dev=round(stdev(values), 3) if stdev(values) is not None else None,
            coefficient_of_variation=(
                round(coefficient_of_variation(values), 3)
                if sufficient and coefficient_of_variation(values) is not None else None
            ),
            sufficient_sample=sufficient,
        ))
    return results


def most_consistent_metrics(results: List[ConsistencyResult], top_n: int = 3) -> List[ConsistencyResult]:
    valid = [r for r in results if r.sufficient_sample and r.coefficient_of_variation is not None]
    return sorted(valid, key=lambda r: r.coefficient_of_variation)[:top_n]


def least_consistent_metrics(results: List[ConsistencyResult], top_n: int = 3) -> List[ConsistencyResult]:
    valid = [r for r in results if r.sufficient_sample and r.coefficient_of_variation is not None]
    return sorted(valid, key=lambda r: r.coefficient_of_variation, reverse=True)[:top_n]
