"""§9's mandated negative-control experiment. This test doesn't assert a
predetermined outcome — it asserts the *mechanism* runs correctly and
reports whatever the real result is (see aisle/README.md for the actual
verdict against this corpus, which is the artifact the brief wants, not a
number tuned to pass this test).
"""
from aisle.cluster.themes import run_theme_clustering
from aisle.eval.negative_control import negative_control_document_count, run_negative_control_check
from aisle.insights.generate import generate_insights_for_run


def test_negative_control_documents_exist_in_seed_corpus():
    assert negative_control_document_count() >= 40


def test_negative_control_check_runs_and_returns_a_verdict():
    clustering_result = run_theme_clustering(trigger="manual")
    generate_insights_for_run(clustering_result["run_id"])

    report = run_negative_control_check(clustering_result["run_id"])

    assert report["verdict"] in ("PASS", "FAIL")
    assert report["total_negative_control_docs"] >= 40
    assert isinstance(report["majority_fabricated_insights"], list)
    assert isinstance(report["explanation"], str) and len(report["explanation"]) > 0
