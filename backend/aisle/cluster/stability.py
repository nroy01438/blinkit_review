"""Cluster stability (§7's robustness requirement): re-run UMAP+HDBSCAN at
several random seeds and report the mean Adjusted Rand Index across every
seed pair. A theme that only appears at one seed is not a theme — low mean
ARI is a signal to widen `min_cluster_size` or revisit the embedding, not
something to paper over.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
from sklearn.metrics import adjusted_rand_score

from aisle.settings import scoring_config


def cluster_at_seed(vectors: np.ndarray, seed: int) -> np.ndarray:
    from aisle.cluster.themes import run_umap_hdbscan  # local import avoids a cycle

    return run_umap_hdbscan(vectors, random_state=seed)


def compute_stability_ari(vectors: np.ndarray, seeds: list[int] | None = None) -> dict:
    seeds = seeds or scoring_config()["clustering"]["stability"]["seeds"]
    if len(vectors) < 4:
        return {"mean_ari": None, "pairwise": [], "seeds": seeds, "note": "too few documents to assess stability"}

    labels_by_seed = {seed: cluster_at_seed(vectors, seed) for seed in seeds}
    pairwise = []
    for seed_a, seed_b in combinations(seeds, 2):
        ari = adjusted_rand_score(labels_by_seed[seed_a], labels_by_seed[seed_b])
        pairwise.append({"seed_a": seed_a, "seed_b": seed_b, "ari": round(float(ari), 4)})

    mean_ari = round(sum(p["ari"] for p in pairwise) / len(pairwise), 4) if pairwise else None
    return {"mean_ari": mean_ari, "pairwise": pairwise, "seeds": seeds}
