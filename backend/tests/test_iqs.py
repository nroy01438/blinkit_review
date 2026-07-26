from aisle.insights.iqs import compute_iqs, grade_for_score


def test_grade_bands_match_config():
    assert grade_for_score(85) == "A"
    assert grade_for_score(70) == "B"
    assert grade_for_score(55) == "C"
    assert grade_for_score(30) == "D"


def test_unsupported_claim_caps_grade_at_c_even_with_high_numeric_score():
    result = compute_iqs(
        claims=[{"claim": "a", "supported": True}, {"claim": "b", "supported": False}],
        doc_count=100, doc_total=120, ci_low=0.7, ci_high=0.75,
        source_counts={"s1": 40, "s2": 30, "s3": 30}, matched_prior_run=True,
        actionability_rubric=4, novelty_rubric=4,
    )
    assert result["grade"] == "C"
    assert "_grade_capped_reason" in result["breakdown"]


def test_fully_supported_high_evidence_high_precision_scores_well():
    result = compute_iqs(
        claims=[{"claim": "a", "supported": True}] * 5,
        doc_count=80, doc_total=100, ci_low=0.75, ci_high=0.82,
        source_counts={"s1": 20, "s2": 20, "s3": 20, "s4": 20}, matched_prior_run=True,
        actionability_rubric=4, novelty_rubric=4,
    )
    assert result["total"] >= 65
    assert "_grade_capped_reason" not in result["breakdown"]


def test_single_source_gets_zero_triangulation():
    result = compute_iqs(
        claims=[{"claim": "a", "supported": True}],
        doc_count=10, doc_total=100, ci_low=0.05, ci_high=0.2,
        source_counts={"only_one_source": 10}, matched_prior_run=False,
        actionability_rubric=2, novelty_rubric=2,
    )
    assert result["breakdown"]["source_triangulation"] == 0.0


def test_very_wide_ci_scores_zero_on_statistical_precision():
    result = compute_iqs(
        claims=[{"claim": "a", "supported": True}],
        doc_count=5, doc_total=100, ci_low=0.0, ci_high=0.6,  # width 0.6 >= the 0.5 zero-floor
        source_counts={"s1": 5}, matched_prior_run=False,
        actionability_rubric=2, novelty_rubric=2,
    )
    assert result["breakdown"]["statistical_precision"] == 0.0


def test_moderately_wide_ci_scores_lower_than_a_narrow_one():
    wide = compute_iqs(
        claims=[{"claim": "a", "supported": True}], doc_count=5, doc_total=100, ci_low=0.01, ci_high=0.4,
        source_counts={"s1": 5}, matched_prior_run=False, actionability_rubric=2, novelty_rubric=2,
    )
    narrow = compute_iqs(
        claims=[{"claim": "a", "supported": True}], doc_count=5, doc_total=100, ci_low=0.2, ci_high=0.22,
        source_counts={"s1": 5}, matched_prior_run=False, actionability_rubric=2, novelty_rubric=2,
    )
    assert wide["breakdown"]["statistical_precision"] < narrow["breakdown"]["statistical_precision"]
