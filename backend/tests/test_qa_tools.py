from aisle.qa.tools import compute_prevalence, get_insight, get_theme_stats, run_segment_comparison, search_reviews
from aisle.db.connection import get_conn


def test_search_reviews_returns_citable_shape():
    results = search_reviews("reorder usual basket", top_k=5)
    assert len(results) <= 5
    for r in results:
        assert "document_id" in r and "quote" in r


def test_compute_prevalence_returns_wilson_ci():
    result = compute_prevalence({})
    assert result["n"] > 0
    assert result["ci_low"] <= result["rate"] <= result["ci_high"]


def test_compute_prevalence_with_barrier_filter_narrows_successes():
    everything = compute_prevalence({})
    filtered = compute_prevalence({"barrier_code": "cannot_assess_freshness"})
    assert filtered["successes"] <= everything["successes"]
    assert filtered["n"] == everything["n"]


def test_run_segment_comparison_returns_two_cohorts_and_a_p_value():
    result = run_segment_comparison("habitual_replenisher", "explorer")
    assert "segment_a" in result and "segment_b" in result
    assert 0.0 <= result["p_value"] <= 1.0


def test_get_theme_stats_by_label_substring():
    with get_conn() as conn:
        row = conn.execute("SELECT label FROM themes ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return
    result = get_theme_stats(label_contains=row["label"][:5])
    assert result is not None
    assert "centroid" not in result


def test_get_insight_returns_none_for_missing_id():
    assert get_insight(999999999) is None


def test_get_insight_returns_doc_counts_when_present():
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM insights ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return
    result = get_insight(row["id"])
    assert result is not None
    assert "doc_count" in result
