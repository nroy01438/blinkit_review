from aisle.classify.pmgate import mock as mock_module
from aisle.classify.pmgate.stage4_extraction import filter_controlled_vocab, run_extraction
from aisle.db.connection import get_conn
from aisle.llm.client import LLMClient
from aisle.llm.cost import CostTracker


def _any_document_id() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM documents ORDER BY id LIMIT 1").fetchone()
    assert row is not None, "run aisle.db.seed first"
    return row["id"]


def test_filter_controlled_vocab_splits_known_from_proposed():
    kept, proposed = filter_controlled_vocab(
        ["reorders_from_saved_list", "made_up_behaviour"], ["reorders_from_saved_list", "uses_reorder_button"]
    )
    assert kept == ["reorders_from_saved_list"]
    assert proposed == ["made_up_behaviour"]


def test_non_verbatim_supporting_span_rejects_extraction(monkeypatch):
    text = "I only ever reorder my usual basket every week from the saved list."

    original_mock_extraction = mock_module.mock_extraction

    def bad_mock_extraction(_text):
        real = original_mock_extraction(_text)
        real["supporting_span"] = "this text was never in the source at all"
        return real

    monkeypatch.setattr(mock_module, "mock_extraction", bad_mock_extraction)
    client = LLMClient(cost_tracker=CostTracker(max_cost_usd=5.0))
    extraction, meta = run_extraction(text, client, document_id=_any_document_id())

    assert extraction is None
    assert meta["needs_human_review"] is True
    assert "verbatim" in meta["rejection_reason"]


def test_verbatim_supporting_span_is_accepted():
    text = "I only ever reorder my usual basket every week from the saved list."
    client = LLMClient(cost_tracker=CostTracker(max_cost_usd=5.0))
    extraction, meta = run_extraction(text, client, document_id=_any_document_id())

    assert extraction is not None
    assert extraction.supporting_span in text
    assert meta["needs_human_review"] is False
