"""Shared statistical primitives — Wilson 95% confidence intervals (§2's
"no naked percentages" rule) and the two-proportion z-test (§8's
segment-difference testing). Lives under `insights/` per the brief's §13
tree, but Phase 4 (theme prevalence) needs the same Wilson CI, so it's
imported from both.
"""
from __future__ import annotations

import math


def wilson_ci(successes: int, n: int, *, confidence: float = 0.95) -> tuple[float, float, float]:
    """Returns (point_estimate, ci_low, ci_high). n=0 returns (0, 0, 0) —
    callers must not report a percentage with no denominator (§2).
    """
    if n == 0:
        return 0.0, 0.0, 0.0
    z = 1.959963984540054 if confidence == 0.95 else _z_for(confidence)
    p_hat = successes / n
    denom = 1 + z**2 / n
    centre = p_hat + z**2 / (2 * n)
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n)
    low = (centre - margin) / denom
    high = (centre + margin) / denom
    return p_hat, max(0.0, low), min(1.0, high)


def _z_for(confidence: float) -> float:
    # Inverse-CDF via a standard rational approximation would be overkill for
    # the confidence levels this project actually uses; 95% is the only one
    # called for anywhere in the brief.
    table = {0.90: 1.6448536269514722, 0.95: 1.959963984540054, 0.99: 2.5758293035489004}
    if confidence not in table:
        raise ValueError(f"Unsupported confidence level {confidence}; add it to the table in _z_for().")
    return table[confidence]


def two_proportion_z_test(successes_a: int, n_a: int, successes_b: int, n_b: int) -> tuple[float, float]:
    """Returns (z_statistic, p_value) for a two-sided test of whether two
    proportions differ (§7/§8's segment-difference testing).
    """
    if n_a == 0 or n_b == 0:
        return 0.0, 1.0
    p_a, p_b = successes_a / n_a, successes_b / n_b
    p_pool = (successes_a + successes_b) / (n_a + n_b)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    if se == 0:
        return 0.0, 1.0
    z = (p_a - p_b) / se
    p_value = 2 * (1 - _std_normal_cdf(abs(z)))
    return z, p_value


def _std_normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
