from aisle.db.connection import get_conn
from aisle.eval.golden import generate_synthetic_proxy_labels, stratified_sample, submit_golden_label


def test_stratified_sample_returns_unique_documents():
    sample = stratified_sample(n=30)
    ids = [r["id"] for r in sample]
    assert len(ids) == len(set(ids))
    assert len(sample) <= 30


def test_submit_golden_label_is_upsert(tmp_path):
    with get_conn() as conn:
        doc_id = conn.execute("SELECT id FROM documents ORDER BY id LIMIT 1").fetchone()["id"]

    submit_golden_label(doc_id, {"is_junk": True}, annotator_id="test_annotator", label_round=1)
    submit_golden_label(doc_id, {"is_junk": False}, annotator_id="test_annotator", label_round=1)

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT human_label_json FROM golden_labels WHERE document_id = %s AND annotator_id = %s AND round = 1",
            (doc_id, "test_annotator"),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["human_label_json"]["is_junk"] is False


def test_generate_synthetic_proxy_labels_is_clearly_tagged():
    written = generate_synthetic_proxy_labels(n=50)
    assert written > 0
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT annotator_id FROM golden_labels WHERE annotator_id = 'synthetic_proxy_v1'"
        ).fetchall()
    assert rows[0]["annotator_id"] == "synthetic_proxy_v1"
