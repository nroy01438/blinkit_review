import numpy as np

from aisle.cluster.embed import HashingEmbeddingProvider, embed_pending_documents, get_embedding_provider
from aisle.db.connection import get_conn


def test_hashing_provider_is_deterministic_and_normalised():
    provider = HashingEmbeddingProvider()
    a = provider.embed(["the pomegranates were split and dry"])
    b = provider.embed(["the pomegranates were split and dry"])
    assert np.allclose(a, b)
    assert a.shape == (1, 384)
    norm = np.linalg.norm(a[0])
    assert abs(norm - 1.0) < 1e-4


def test_hashing_provider_similar_texts_are_closer_than_unrelated():
    provider = HashingEmbeddingProvider()
    texts = [
        "I only ever reorder my usual basket every week from the saved list",
        "I always reorder my usual basket every single week from the saved list",
        "the delivery partner could not find my address today",
    ]
    vecs = provider.embed(texts)
    sim_related = float(vecs[0] @ vecs[1])
    sim_unrelated = float(vecs[0] @ vecs[2])
    assert sim_related > sim_unrelated


def test_get_embedding_provider_defaults_to_hashing_under_mock_mode():
    provider = get_embedding_provider()
    assert provider.model_name == "hashing-trick-v1"


def test_embed_pending_documents_is_idempotent():
    with get_conn() as conn:
        eligible_before = conn.execute(
            """
            SELECT count(*) AS n FROM documents d
            JOIN classifications c ON c.document_id = d.id
            LEFT JOIN embeddings e ON e.document_id = d.id
            WHERE e.document_id IS NULL AND d.dupe_of_id IS NULL AND c.is_junk = false AND c.discovery_relevance >= 2
            """
        ).fetchone()["n"]

    first = embed_pending_documents()
    second = embed_pending_documents()

    assert first["embedded"] == eligible_before
    assert second["embedded"] == 0
