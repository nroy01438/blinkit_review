import numpy as np

from aisle.cluster.stability import compute_stability_ari


def test_stability_returns_note_for_too_few_documents():
    result = compute_stability_ari(np.random.default_rng(0).standard_normal((3, 384)).astype(np.float32))
    assert result["mean_ari"] is None
    assert "note" in result


def test_stability_computes_ari_in_valid_range():
    rng = np.random.default_rng(1)
    cluster_a = rng.standard_normal((15, 384)) * 0.1 + np.array([1.0] + [0.0] * 383)
    cluster_b = rng.standard_normal((15, 384)) * 0.1 + np.array([-1.0] + [0.0] * 383)
    vectors = np.vstack([cluster_a, cluster_b]).astype(np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / norms

    result = compute_stability_ari(vectors, seeds=[1, 2, 3])
    assert result["mean_ari"] is not None
    assert -1.0 <= result["mean_ari"] <= 1.0
    assert len(result["pairwise"]) == 3
