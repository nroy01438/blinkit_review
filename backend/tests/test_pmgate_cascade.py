from aisle.classify.pmgate.cascade import classify_document
from aisle.db.connection import get_conn
from aisle.llm.client import LLMClient
from aisle.llm.cost import CostTracker


def _fresh_client() -> LLMClient:
    return LLMClient(cost_tracker=CostTracker(max_cost_usd=10.0))


def _sample_doc(bucket_hint: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, raw_text FROM documents WHERE meta_json->>'bucket_hint' = %s ORDER BY id LIMIT 1",
            (bucket_hint,),
        ).fetchone()
    assert row is not None, f"no seeded document with bucket_hint={bucket_hint!r} — run aisle.db.seed first"
    return row


def test_junk_bucket_short_circuits_at_stage1():
    doc = _sample_doc("junk")
    result = classify_document(doc["id"], doc["raw_text"], _fresh_client())
    assert result["is_junk"] is True
    assert result["stage_reached"] == 1
    assert result["junk_reason"] is not None
    assert "pm_utility_score" not in result or result.get("pm_utility_score") is None


def test_ops_bucket_is_routed_to_ops_bucket_not_deleted():
    """Off-topic ops complaints (crashes, delivery timing) are marked
    is_junk=True with junk_reason='ops_off_topic' per §6's Stage-1 design —
    kept in the corpus (never deleted), short-circuited before relevance
    scoring, and excluded from discovery denominators via is_junk, while
    remaining queryable for the ops-bucket view (Q6)."""
    doc = _sample_doc("ops")
    result = classify_document(doc["id"], doc["raw_text"], _fresh_client())
    assert result["is_junk"] is True
    assert result["junk_reason"] == "ops_off_topic"
    assert result["stage_reached"] == 1
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM documents WHERE id = %s", (doc["id"],)).fetchone()
    assert row is not None, "ops-bucket documents must never be deleted"


def test_discovery_high_bucket_reaches_extraction_with_verbatim_span():
    doc = _sample_doc("discovery_high")
    result = classify_document(doc["id"], doc["raw_text"], _fresh_client())
    assert result["is_junk"] is False
    assert result.get("discovery_relevance", 0) >= 2
    assert result["stage_reached"] == 5
    span = result.get("supporting_span")
    assert span is not None
    assert span in doc["raw_text"]


def test_extracted_codes_are_all_from_controlled_vocabulary():
    from aisle.settings import codes_taxonomy

    taxonomy = codes_taxonomy()
    doc = _sample_doc("discovery_high")
    result = classify_document(doc["id"], doc["raw_text"], _fresh_client())
    for code in result.get("behaviour_codes") or []:
        assert code in taxonomy["behaviour_codes"]
    for code in result.get("barrier_codes") or []:
        assert code in taxonomy["barrier_codes"]


def test_classification_is_upserted_not_duplicated():
    doc = _sample_doc("discovery_low")
    client = _fresh_client()
    classify_document(doc["id"], doc["raw_text"], client)
    classify_document(doc["id"], doc["raw_text"], client)
    with get_conn() as conn:
        count = conn.execute(
            "SELECT count(*) AS n FROM classifications WHERE document_id = %s", (doc["id"],)
        ).fetchone()["n"]
    assert count == 1
