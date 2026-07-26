import pytest

from aisle.classify.run import run_classification
from aisle.eval import metrics as metrics_module
from aisle.eval.golden import generate_synthetic_proxy_labels


@pytest.fixture(scope="module", autouse=True)
def _classified_and_labelled_corpus():
    run_classification(limit=2000, trigger="manual")
    generate_synthetic_proxy_labels(n=300)
    yield


def test_stage1_junk_metrics_reasonable_against_synthetic_proxy():
    result = metrics_module.stage1_junk_metrics("synthetic_proxy_v1")
    assert result["n"] > 0
    assert result["precision"] is not None
    assert 0.0 <= result["recall"] <= 1.0


def test_stage3_relevance_metrics_reasonable_against_synthetic_proxy():
    result = metrics_module.stage3_relevance_metrics("synthetic_proxy_v1")
    assert result["n"] > 0
    assert 0.0 <= result["f1"] <= 1.0


def test_classifier_vs_human_kappa_computes():
    result = metrics_module.classifier_vs_human_kappa("synthetic_proxy_v1")
    assert result["n"] > 0
    assert result["kappa"] is not None
    assert -1.0 <= result["kappa"] <= 1.0


def test_human_vs_human_kappa_detects_known_disagreement():
    from aisle.db.connection import get_conn
    from aisle.eval.golden import submit_golden_label

    with get_conn() as conn:
        doc_ids = [r["id"] for r in conn.execute("SELECT id FROM documents ORDER BY id LIMIT 20").fetchall()]

    for i, doc_id in enumerate(doc_ids):
        submit_golden_label(doc_id, {"is_junk": i % 2 == 0}, annotator_id="annotator_a", label_round=99)
        submit_golden_label(doc_id, {"is_junk": i % 2 == 0}, annotator_id="annotator_b", label_round=99)

    perfect_agreement = metrics_module.human_vs_human_kappa("annotator_a", "annotator_b", "is_junk", label_round=99)
    assert perfect_agreement["kappa"] == 1.0

    for i, doc_id in enumerate(doc_ids):
        submit_golden_label(doc_id, {"is_junk": True}, annotator_id="annotator_c", label_round=99)

    disagreement = metrics_module.human_vs_human_kappa("annotator_a", "annotator_c", "is_junk", label_round=99)
    assert disagreement["kappa"] is not None
    assert disagreement["kappa"] < perfect_agreement["kappa"]


def test_calibration_bins_cover_full_range():
    bins = metrics_module.calibration_bins("synthetic_proxy_v1", n_bins=5)
    assert len(bins) == 5
    assert sum(b["n"] for b in bins) > 0


def test_abstention_rate_is_a_fraction():
    result = metrics_module.abstention_rate("pmgate.v1")
    assert result["n"] > 0
    assert 0.0 <= result["rate"] <= 1.0


def test_acceptance_gate_reports_all_three_checks():
    gate = metrics_module.acceptance_gate("synthetic_proxy_v1")
    assert set(gate["checks"].keys()) == {"stage1_junk_recall", "stage3_relevance_f1", "kappa"}
    assert isinstance(gate["all_passed"], bool)
