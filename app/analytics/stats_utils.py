"""
Small, honest statistics helpers shared by the analytics modules. No
p-value theater: sample sizes here are small (a session is typically 10-30
shots), so results are reported as descriptive differences with effect
size and explicit sample counts, and a significance label is only ever a
soft descriptor ("appears meaningful" / "inconclusive"), never a claim of
statistical proof.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from app.config import CONFIG


def mean(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def stdev(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    m = mean(values)
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def coefficient_of_variation(values: List[float]) -> Optional[float]:
    """Lower = more consistent. None if mean is ~0 (ratio undefined) or <2 samples."""
    m = mean(values)
    s = stdev(values)
    if m is None or s is None or abs(m) < 1e-6:
        return None
    return abs(s / m)


def cohens_d(a: List[float], b: List[float]) -> Optional[float]:
    if len(a) < 2 or len(b) < 2:
        return None
    ma, mb = mean(a), mean(b)
    sa, sb = stdev(a), stdev(b)
    if sa is None or sb is None:
        return None
    na, nb = len(a), len(b)
    pooled_var = ((na - 1) * sa ** 2 + (nb - 1) * sb ** 2) / (na + nb - 2)
    pooled_sd = math.sqrt(pooled_var) if pooled_var > 0 else None
    if not pooled_sd:
        return None
    return (ma - mb) / pooled_sd


def effect_size_label(d: Optional[float]) -> str:
    if d is None:
        return "unknown"
    ad = abs(d)
    cfg = CONFIG.analytics
    if ad < cfg.effect_size_small:
        return "negligible"
    if ad < cfg.effect_size_medium:
        return "small"
    if ad < cfg.effect_size_large:
        return "medium"
    return "large"


@dataclass
class ComparisonResult:
    metric_name: str
    made_mean: Optional[float]
    missed_mean: Optional[float]
    made_n: int
    missed_n: int
    made_std: Optional[float]
    missed_std: Optional[float]
    difference: Optional[float]
    effect_size: Optional[float]
    effect_label: str
    sufficient_sample: bool
    p_value: Optional[float] = None


def compare_groups(metric_name: str, made_values: List[float], missed_values: List[float],
                    min_n_each: int) -> ComparisonResult:
    sufficient = len(made_values) >= min_n_each and len(missed_values) >= min_n_each
    d = cohens_d(made_values, missed_values) if sufficient else None
    p_value = None
    if sufficient and len(made_values) >= 2 and len(missed_values) >= 2:
        try:
            from scipy import stats as _stats
            _, p_value = _stats.ttest_ind(made_values, missed_values, equal_var=False)
            p_value = float(p_value)
            if math.isnan(p_value) or math.isinf(p_value):
                p_value = None
        except Exception:
            p_value = None

    made_m, missed_m = mean(made_values), mean(missed_values)
    diff = (made_m - missed_m) if (made_m is not None and missed_m is not None) else None

    return ComparisonResult(
        metric_name=metric_name,
        made_mean=round(made_m, 3) if made_m is not None else None,
        missed_mean=round(missed_m, 3) if missed_m is not None else None,
        made_n=len(made_values),
        missed_n=len(missed_values),
        made_std=round(stdev(made_values), 3) if stdev(made_values) is not None else None,
        missed_std=round(stdev(missed_values), 3) if stdev(missed_values) is not None else None,
        difference=round(diff, 3) if diff is not None else None,
        effect_size=round(d, 3) if d is not None else None,
        effect_label=effect_size_label(d),
        sufficient_sample=sufficient,
        p_value=round(p_value, 4) if p_value is not None else None,
    )
