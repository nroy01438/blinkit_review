"""Hybrid retrieval (§11): BM25 (lexical) + pgvector cosine (semantic),
fused with Reciprocal Rank Fusion, then a lightweight lexical-overlap
rerank pass. Operates over the same discovery-relevant, non-junk, non-dupe
corpus the clustering/insight pipeline uses — this product answers
questions about *that* corpus, not the ops-bucket/junk documents.

At this corpus's size (hundreds of docs), building the BM25 index fresh
per request and re-embedding the query is cheap. At 25k+ scale this would
need a persistent BM25 index and a proper ANN query instead of a full
per-request rebuild — documented as a scaling TODO, not solved here.
"""
from __future__ import annotations

import re

import numpy as np
from rank_bm25 import BM25Okapi

from aisle.cluster.embed import get_embedding_provider
from aisle.db.connection import get_conn

RRF_K = 60
MIN_COSINE_SIMILARITY = 0.35  # below this, the hashing embedding's "similarity" is noise, not signal
TOKEN_RE = re.compile(r"[a-z]{2,}")


def _tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _corpus_pool(relevance_floor: int = 2) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id AS document_id, d.raw_text, d.posted_at, s.name AS source_name, s.brand,
                   c.segment_label, c.categories_mentioned, c.barrier_codes, c.behaviour_codes,
                   e.vector
            FROM documents d
            JOIN classifications c ON c.document_id = d.id
            JOIN sources s ON s.id = d.source_id
            LEFT JOIN embeddings e ON e.document_id = d.id
            WHERE d.dupe_of_id IS NULL AND c.is_junk = false AND c.discovery_relevance >= %s
            """,
            (relevance_floor,),
        ).fetchall()
    return [dict(r) for r in rows]


def _rrf_fuse(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


def _lexical_rerank_boost(query_tokens: set[str], text: str) -> float:
    text_tokens = set(_tokenize(text))
    if not query_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / len(query_tokens)


def hybrid_search(query: str, top_k: int = 40, relevance_floor: int = 2) -> list[dict]:
    pool = _corpus_pool(relevance_floor)
    if not pool:
        return []

    query_tokens_list = _tokenize(query)
    corpus_tokens = [_tokenize(r["raw_text"]) for r in pool]
    bm25 = BM25Okapi(corpus_tokens)
    bm25_scores = bm25.get_scores(query_tokens_list)
    bm25_score_by_id = {pool[i]["document_id"]: float(bm25_scores[i]) for i in range(len(pool))}
    bm25_ranking = [pool[i]["document_id"] for i in np.argsort(-bm25_scores)]

    with_vectors = [r for r in pool if r["vector"] is not None]
    vector_ranking: list[int] = []
    cosine_by_id: dict[int, float] = {}
    if with_vectors:
        provider = get_embedding_provider()
        query_vec = provider.embed([query])[0]
        matrix = np.array([r["vector"] for r in with_vectors], dtype=np.float32)
        sims = matrix @ query_vec
        cosine_by_id = {with_vectors[i]["document_id"]: float(sims[i]) for i in range(len(with_vectors))}
        vector_ranking = [with_vectors[i]["document_id"] for i in np.argsort(-sims)]

    # A document only counts as genuinely retrieved if it shows real signal
    # in at least one channel — an empty/irrelevant query must not silently
    # return "the whole corpus, ranked" (RRF always produces a full ranking
    # regardless of whether any candidate is actually relevant), or the
    # agent's refusal rule (§11) could never fire.
    relevant_ids = {
        doc_id
        for doc_id in bm25_score_by_id
        if bm25_score_by_id.get(doc_id, 0.0) > 0.0 or cosine_by_id.get(doc_id, 0.0) >= MIN_COSINE_SIMILARITY
    }
    if not relevant_ids:
        return []

    fused = _rrf_fuse([bm25_ranking, vector_ranking] if vector_ranking else [bm25_ranking])
    fused = {doc_id: score for doc_id, score in fused.items() if doc_id in relevant_ids}

    query_token_set = set(query_tokens_list)
    by_id = {r["document_id"]: r for r in pool}
    candidates = sorted(fused.items(), key=lambda kv: -kv[1])[: top_k * 2]
    reranked = sorted(
        candidates,
        key=lambda kv: kv[1] + 0.05 * _lexical_rerank_boost(query_token_set, by_id[kv[0]]["raw_text"]),
        reverse=True,
    )
    return [by_id[doc_id] for doc_id, _ in reranked[:top_k]]
