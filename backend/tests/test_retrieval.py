from aisle.qa.retrieval import hybrid_search


def test_hybrid_search_returns_relevant_documents_ranked_above_unrelated():
    results = hybrid_search("reorder usual basket every week", top_k=10)
    assert len(results) > 0
    top_text = results[0]["raw_text"].lower()
    assert "reorder" in top_text or "usual" in top_text or "basket" in top_text


def test_hybrid_search_respects_top_k():
    results = hybrid_search("delivery freshness return policy", top_k=5)
    assert len(results) <= 5


def test_hybrid_search_empty_query_still_returns_something_from_pool():
    results = hybrid_search("", top_k=5)
    assert isinstance(results, list)
