"""
Regression coverage for the overnight-pass fix in
app/analytics/stats_utils.py: scipy.stats.ttest_ind can return a NaN
p-value (not raise) for degenerate/near-identical samples, and a NaN float
is `is not None`, so it used to sail past the old `p_value is not None`
guard and get serialized as the literal JSON token `NaN` -- which broke
JSON.parse() in the browser for the entire exported demo session. See
docs/OVERNIGHT_PUBLICATION_READINESS.md section C/K.
"""
import json
import math

from app.analytics.stats_utils import compare_groups


def test_degenerate_equal_samples_yield_none_p_value_not_nan():
    # Two identical-valued samples -- scipy's t-test degenerates to 0/0 and
    # returns NaN (not an exception) for this input, confirmed directly
    # against scipy.stats.ttest_ind during this fix's development.
    made_values = [2.0, 2.0, 2.0]
    missed_values = [2.0, 2.0, 2.0]

    result = compare_groups("test_metric", made_values, missed_values, min_n_each=2)

    assert result.p_value is None
    # A ComparisonResult with a real (non-None) p_value must never be able
    # to reach json.dumps(..., allow_nan=False) -- confirm the whole
    # dataclass round-trips through strict JSON regardless.
    json.dumps(vars(result), allow_nan=False)


def test_normal_samples_still_produce_a_real_p_value():
    made_values = [10.0, 12.0, 9.0, 11.0]
    missed_values = [4.0, 5.0, 3.0, 6.0]

    result = compare_groups("test_metric", made_values, missed_values, min_n_each=2)

    assert result.p_value is not None
    assert not math.isnan(result.p_value)
    assert 0.0 <= result.p_value <= 1.0
