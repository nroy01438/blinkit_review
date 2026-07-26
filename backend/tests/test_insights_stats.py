from aisle.insights.stats import two_proportion_z_test, wilson_ci


def test_wilson_ci_zero_n_returns_zero_zero_zero():
    assert wilson_ci(0, 0) == (0.0, 0.0, 0.0)


def test_wilson_ci_contains_point_estimate():
    p, low, high = wilson_ci(30, 100)
    assert low <= p <= high
    assert abs(p - 0.3) < 1e-9


def test_wilson_ci_narrows_with_larger_n():
    _, low_small, high_small = wilson_ci(30, 100)
    _, low_large, high_large = wilson_ci(300, 1000)
    assert (high_large - low_large) < (high_small - low_small)


def test_two_proportion_z_test_identical_rates_not_significant():
    z, p = two_proportion_z_test(50, 100, 50, 100)
    assert abs(z) < 1e-9
    assert p > 0.99


def test_two_proportion_z_test_large_difference_is_significant():
    z, p = two_proportion_z_test(90, 100, 10, 100)
    assert p < 0.05


def test_two_proportion_z_test_zero_denominator_returns_neutral():
    z, p = two_proportion_z_test(0, 0, 5, 10)
    assert z == 0.0
    assert p == 1.0
