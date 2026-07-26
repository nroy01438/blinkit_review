"""Theme identification (§7): embed → UMAP → HDBSCAN → name via LLM
(grounded only in c-TF-IDF top terms + medoid documents) → merge
near-duplicate themes → map to the taxonomy → compute prevalence with a
Wilson 95% CI, source/brand/segment/category splits, and week-over-week
delta → persist.
"""
from __future__ import annotations

import json

import numpy as np

from aisle.cluster.embed import embed_pending_documents
from aisle.cluster.schemas import MergeDecision, ThemeNaming
from aisle.cluster.terms import c_tf_idf, tokenize
from aisle.db.connection import get_conn
from aisle.insights.stats import wilson_ci
from aisle.llm.client import LLMClient
from aisle.llm.cost import CostTracker
from aisle.settings import get_settings, scoring_config, themes_taxonomy

MEDOIDS_PER_THEME = 8
NAMING_PROMPT_VERSION = "theme_naming.v1"
MERGE_PROMPT_VERSION = "theme_merge.v1"


def run_umap_hdbscan(vectors: np.ndarray, random_state: int) -> np.ndarray:
    import hdbscan
    import umap

    cfg = scoring_config()["clustering"]
    n_neighbors = min(cfg["umap"]["n_neighbors"], max(2, len(vectors) - 1))
    reduced = umap.UMAP(
        n_neighbors=n_neighbors, min_dist=cfg["umap"]["min_dist"], n_components=5, random_state=random_state
    ).fit_transform(vectors)

    min_cluster_size = max(cfg["hdbscan"]["min_cluster_size_floor"], round(cfg["hdbscan"]["min_cluster_size_pct_of_corpus"] * len(vectors)))
    min_cluster_size = min(min_cluster_size, max(2, len(vectors) // 2))
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size)
    return clusterer.fit_predict(reduced)


def _medoid_doc_ids(vectors: np.ndarray, doc_ids: list[int], labels: np.ndarray, cluster_id: int, k: int = MEDOIDS_PER_THEME) -> list[int]:
    mask = labels == cluster_id
    cluster_vectors = vectors[mask]
    cluster_doc_ids = [d for d, m in zip(doc_ids, mask) if m]
    centroid = cluster_vectors.mean(axis=0)
    centroid /= (np.linalg.norm(centroid) or 1)
    sims = cluster_vectors @ centroid
    order = np.argsort(-sims)
    return [cluster_doc_ids[i] for i in order[:k]]


def _mock_theme_naming(top_terms: list[str], medoid_texts: list[str]) -> dict:
    label = " / ".join(top_terms[:3]).replace("_", " ").title() if top_terms else "Unnamed cluster"
    snippet = medoid_texts[0][:140] if medoid_texts else ""
    description = (
        f"Documents in this cluster recurrently mention {', '.join(top_terms[:5]) or 'shared language'}. "
        f"Representative example: \"{snippet}\""
    )
    return {"label": label[:120], "description": description[:500]}


def name_theme(top_terms: list[str], medoid_texts: list[str], client: LLMClient) -> ThemeNaming:
    prompt = (
        "Name this theme from a cluster of Blinkit user-feedback documents, using ONLY the evidence below "
        "(do not invent claims beyond it). Top distinguishing terms: " + ", ".join(top_terms) + "\n\n"
        "Medoid (most representative) documents:\n" + "\n---\n".join(medoid_texts[:8]) + "\n\n"
        'Respond with strict JSON: {"label": string (<=10 words), "description": string (2 sentences, grounded only in the medoids above)}'
    )
    result = client.complete_json(
        prompt=prompt, response_model=ThemeNaming, prompt_version=NAMING_PROMPT_VERSION,
        model=get_settings().aisle_synth_model, stage="theme_naming",
        mock_response_factory=lambda: _mock_theme_naming(top_terms, medoid_texts),
    )
    return result.parsed or ThemeNaming(**_mock_theme_naming(top_terms, medoid_texts))


def _mock_merge_decision(terms_a: list[str], terms_b: list[str]) -> dict:
    overlap = len(set(terms_a) & set(terms_b))
    return {"should_merge": overlap >= 3, "rationale": f"{overlap} shared top terms"}


def adjudicate_merge(terms_a: list[str], terms_b: list[str], client: LLMClient) -> MergeDecision:
    prompt = (
        f"Two theme clusters have highly similar centroids. Cluster A top terms: {terms_a}. "
        f"Cluster B top terms: {terms_b}. Should these be merged into one theme? "
        'Respond with strict JSON: {"should_merge": bool, "rationale": string}'
    )
    result = client.complete_json(
        prompt=prompt, response_model=MergeDecision, prompt_version=MERGE_PROMPT_VERSION,
        model=get_settings().aisle_synth_model, stage="theme_merge",
        mock_response_factory=lambda: _mock_merge_decision(terms_a, terms_b),
    )
    return result.parsed or MergeDecision(**_mock_merge_decision(terms_a, terms_b))


def _merge_clusters(centroids: dict[int, np.ndarray], top_terms: dict[int, list[str]], client: LLMClient) -> dict[int, int]:
    """Returns a mapping old_cluster_id -> canonical_cluster_id after
    merging any pair whose centroid cosine similarity clears the config
    threshold and whose merge the LLM (or mock) approves.
    """
    threshold = scoring_config()["theme_merge"]["centroid_cosine_similarity_threshold"]
    parent = {cid: cid for cid in centroids}

    def find(x: int) -> int:
        while parent[x] != x:
            x = parent[x]
        return x

    ids = sorted(centroids)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            sim = float(centroids[a] @ centroids[b])
            if sim >= threshold:
                decision = adjudicate_merge(top_terms[a], top_terms[b], client)
                if decision.should_merge:
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[max(ra, rb)] = min(ra, rb)
    return {cid: find(cid) for cid in centroids}


def _map_to_taxonomy(top_terms: list[str], label: str) -> str | None:
    taxonomy = themes_taxonomy()["nodes"]
    theme_tokens = set(top_terms) | set(tokenize(label))
    best_node, best_overlap = None, 0
    for node in taxonomy:
        node_tokens = set(tokenize(node["label"])) | set(tokenize(node["description"]))
        overlap = len(theme_tokens & node_tokens)
        if overlap > best_overlap:
            best_node, best_overlap = node["id"], overlap
    return best_node if best_overlap >= 2 else None


def _previous_theme(taxonomy_node: str | None, label: str, before_run_id: int) -> dict | None:
    with get_conn() as conn:
        if taxonomy_node:
            row = conn.execute(
                "SELECT * FROM themes WHERE taxonomy_node = %s AND run_id < %s ORDER BY run_id DESC LIMIT 1",
                (taxonomy_node, before_run_id),
            ).fetchone()
            if row:
                return dict(row)
        row = conn.execute(
            "SELECT * FROM themes WHERE label = %s AND run_id < %s ORDER BY run_id DESC LIMIT 1",
            (label, before_run_id),
        ).fetchone()
        return dict(row) if row else None


def run_theme_clustering(*, trigger: str = "manual", relevance_floor: int = 2, max_cost_usd: float | None = None) -> dict:
    embed_stats = embed_pending_documents(relevance_floor=relevance_floor)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id AS document_id, d.raw_text, d.lang_detected, s.name AS source_name, s.brand,
                   c.segment_label, c.categories_mentioned, e.vector
            FROM documents d
            JOIN classifications c ON c.document_id = d.id
            JOIN embeddings e ON e.document_id = d.id
            JOIN sources s ON s.id = d.source_id
            WHERE d.dupe_of_id IS NULL AND c.is_junk = false AND c.discovery_relevance >= %s
            """,
            (relevance_floor,),
        ).fetchall()
        run_row = conn.execute("INSERT INTO runs (trigger, status) VALUES (%s, 'running') RETURNING id", (trigger,)).fetchone()
        conn.commit()
        run_id = run_row["id"]

    doc_total = len(rows)
    if doc_total < 4:
        with get_conn() as conn:
            conn.execute(
                "UPDATE runs SET finished_at = now(), status = 'partial', stage_stats_json = %s WHERE id = %s",
                (json.dumps({"reason": "too few eligible documents to cluster", "doc_total": doc_total}), run_id),
            )
            conn.commit()
        return {"run_id": run_id, "doc_total": doc_total, "themes": [], "note": "too few eligible documents to cluster"}

    doc_ids = [r["document_id"] for r in rows]
    doc_id_to_index = {d: i for i, d in enumerate(doc_ids)}
    vectors = np.array([r["vector"] for r in rows], dtype=np.float32)

    labels = run_umap_hdbscan(vectors, random_state=scoring_config()["clustering"]["stability"]["seeds"][0])
    noise_pct = float((labels == -1).sum()) / len(labels)

    cluster_texts = {int(cid): [rows[i]["raw_text"] for i in range(len(rows)) if labels[i] == cid] for cid in set(labels) if cid != -1}
    top_terms_by_cluster = c_tf_idf(cluster_texts)

    centroids = {}
    for cid in cluster_texts:
        mask = labels == cid
        centroid = vectors[mask].mean(axis=0)
        centroids[cid] = centroid / (np.linalg.norm(centroid) or 1)

    client = LLMClient(cost_tracker=CostTracker(max_cost_usd=max_cost_usd or get_settings().aisle_max_cost_usd))
    merge_map = _merge_clusters(centroids, top_terms_by_cluster, client) if len(centroids) > 1 else {cid: cid for cid in centroids}

    canonical_clusters: dict[int, list[int]] = {}
    for cid, canon in merge_map.items():
        canonical_clusters.setdefault(canon, []).append(cid)

    stability = None
    try:
        from aisle.cluster.stability import compute_stability_ari

        stability = compute_stability_ari(vectors)
    except Exception:  # noqa: BLE001 - stability is a diagnostic extra, never block persistence on it
        stability = {"mean_ari": None, "pairwise": [], "note": "stability computation failed"}

    theme_summaries = []
    for canon_cid, member_cids in canonical_clusters.items():
        member_mask = np.isin(labels, member_cids)
        member_doc_ids = [d for d, m in zip(doc_ids, member_mask) if m]
        merged_terms = sorted({t for cid in member_cids for t in top_terms_by_cluster.get(cid, [])}, key=lambda t: -sum(1 for cid in member_cids if t in top_terms_by_cluster.get(cid, [])))[:10]

        medoid_ids = _medoid_doc_ids(vectors, doc_ids, np.array([canon_cid if l in member_cids else l for l in labels]), canon_cid)
        medoid_texts = [rows[doc_id_to_index[mid]]["raw_text"] for mid in medoid_ids]

        naming = name_theme(merged_terms, medoid_texts, client)
        taxonomy_node = _map_to_taxonomy(merged_terms, naming.label)
        prev = _previous_theme(taxonomy_node, naming.label, run_id)

        doc_count = len(member_doc_ids)
        prevalence, ci_low, ci_high = wilson_ci(doc_count, doc_total)

        member_rows = [rows[doc_id_to_index[d]] for d in member_doc_ids]
        source_counts: dict[str, int] = {}
        brand_counts: dict[str, int] = {}
        segment_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        for r in member_rows:
            source_counts[r["source_name"]] = source_counts.get(r["source_name"], 0) + 1
            brand_counts[r["brand"]] = brand_counts.get(r["brand"], 0) + 1
            if r["segment_label"]:
                segment_counts[r["segment_label"]] = segment_counts.get(r["segment_label"], 0) + 1
            for cat in r["categories_mentioned"] or []:
                category_counts[cat] = category_counts.get(cat, 0) + 1

        delta = None
        status = "new"
        first_seen_run = run_id
        if prev is not None:
            delta = round(prevalence - prev["prevalence"], 4)
            first_seen_run = prev["first_seen_run"] or prev["run_id"]
            if prev["prevalence"] and abs(delta / prev["prevalence"]) > 0.2:
                status = "growing" if delta > 0 else "decaying"
            else:
                status = "stable"

        with get_conn() as conn:
            theme_row = conn.execute(
                """
                INSERT INTO themes (run_id, label, description, taxonomy_node, doc_count, doc_total, prevalence,
                                     ci_low, ci_high, source_spread_json, first_seen_run, delta_vs_prev_run,
                                     centroid, status, noise_pct, stability_ari)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    run_id, naming.label, naming.description, taxonomy_node, doc_count, doc_total, prevalence,
                    ci_low, ci_high,
                    json.dumps({"sources": source_counts, "brands": brand_counts, "segments": segment_counts, "categories": category_counts}),
                    first_seen_run, delta, centroids[canon_cid].tolist(), status, round(noise_pct, 4),
                    stability["mean_ari"],
                ),
            ).fetchone()
            theme_id = theme_row["id"]
            for d in member_doc_ids:
                is_exemplar = d in medoid_ids
                conn.execute(
                    "INSERT INTO theme_documents (theme_id, document_id, is_exemplar) VALUES (%s, %s, %s)",
                    (theme_id, d, is_exemplar),
                )
            conn.commit()

        theme_summaries.append(
            {
                "theme_id": theme_id, "label": naming.label, "doc_count": doc_count, "doc_total": doc_total,
                "prevalence": round(prevalence, 4), "ci_low": round(ci_low, 4), "ci_high": round(ci_high, 4),
                "source_spread": {"n_distinct_sources": len(source_counts)}, "status": status,
                "delta_vs_prev_run": delta, "taxonomy_node": taxonomy_node,
            }
        )

    stats = {
        "doc_total": doc_total, "n_themes": len(theme_summaries), "noise_pct": round(noise_pct, 4),
        "stability_ari": stability["mean_ari"], "embed_stats": embed_stats,
        "themes": theme_summaries, "cost_usd": round(client.cost_tracker.cost_usd, 4),
    }
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = now(), status = 'completed', stage_stats_json = %s, cost_usd = %s WHERE id = %s",
            (json.dumps(stats, default=str), stats["cost_usd"], run_id),
        )
        conn.commit()

    return {"run_id": run_id, **stats}
