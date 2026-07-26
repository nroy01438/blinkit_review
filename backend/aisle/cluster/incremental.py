"""Incremental clustering for the weekly job (§12 step 4): assign newly
embedded documents to an existing theme where cosine similarity clears the
config threshold, cluster the residual to propose new themes, then
recompute prevalence/CI/delta for every current theme against the grown
corpus — not just the ones that got new members, since the denominator
(`doc_total`) changed for everyone.

Existing themes are updated in place (same theme `id`, `run_id` bumped to
the current run) rather than re-inserted every run — a persistent-entity
model, not Phase 4's "every run is a fresh clustering" model. This is a
deliberate divergence from `aisle.cluster.themes.run_theme_clustering`
(a full from-scratch re-cluster, still the right tool for a `python -m
aisle.cluster.run` initial/manual run) — the weekly job is specifically an
*incremental* update over what's already there.
"""
from __future__ import annotations

import json

import numpy as np

from aisle.cluster.embed import embed_pending_documents
from aisle.cluster.terms import c_tf_idf
from aisle.cluster.themes import _map_to_taxonomy, _medoid_doc_ids, name_theme, run_umap_hdbscan
from aisle.db.connection import get_conn
from aisle.insights.stats import wilson_ci
from aisle.llm.client import LLMClient
from aisle.llm.cost import CostTracker
from aisle.settings import get_settings, scoring_config

RELEVANCE_FLOOR = 2


def _current_themes(conn) -> list[dict]:
    latest_run = conn.execute("SELECT run_id FROM themes ORDER BY run_id DESC LIMIT 1").fetchone()
    if latest_run is None:
        return []
    rows = conn.execute("SELECT * FROM themes WHERE run_id = %s", (latest_run["run_id"],)).fetchall()
    return [dict(r) for r in rows]


def _unassigned_eligible_docs(conn) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT d.id AS document_id, d.raw_text, e.vector
            FROM documents d
            JOIN classifications c ON c.document_id = d.id
            JOIN embeddings e ON e.document_id = d.id
            WHERE d.dupe_of_id IS NULL AND c.is_junk = false AND c.discovery_relevance >= %s
              AND NOT EXISTS (SELECT 1 FROM theme_documents td WHERE td.document_id = d.id)
            """,
            (RELEVANCE_FLOOR,),
        ).fetchall()
    ]


def _doc_total(conn) -> int:
    return conn.execute(
        "SELECT count(*) AS n FROM documents d JOIN classifications c ON c.document_id = d.id "
        "WHERE d.dupe_of_id IS NULL AND c.is_junk = false AND c.discovery_relevance >= %s",
        (RELEVANCE_FLOOR,),
    ).fetchone()["n"]


def run_incremental_clustering(run_id: int, *, max_cost_usd: float | None = None) -> dict:
    embed_stats = embed_pending_documents(relevance_floor=RELEVANCE_FLOOR)

    with get_conn() as conn:
        current_themes = _current_themes(conn)
        new_docs = _unassigned_eligible_docs(conn)

    threshold = scoring_config()["theme_merge"]["incremental_assign_cosine_threshold"]
    assigned_counts: dict[int, int] = {}
    residual: list[dict] = []

    theme_centroids = {t["id"]: np.array(t["centroid"], dtype=np.float32) for t in current_themes if t["centroid"] is not None}

    for doc in new_docs:
        if doc["vector"] is None or not theme_centroids:
            residual.append(doc)
            continue
        vec = np.array(doc["vector"], dtype=np.float32)
        best_theme_id, best_sim = None, -1.0
        for theme_id, centroid in theme_centroids.items():
            sim = float(vec @ centroid)
            if sim > best_sim:
                best_theme_id, best_sim = theme_id, sim
        if best_sim >= threshold:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO theme_documents (theme_id, document_id, membership_score) VALUES (%s, %s, %s)",
                    (best_theme_id, doc["document_id"], best_sim),
                )
                conn.commit()
            assigned_counts[best_theme_id] = assigned_counts.get(best_theme_id, 0) + 1
        else:
            residual.append(doc)

    new_theme_ids: list[int] = []
    cfg = scoring_config()["clustering"]["hdbscan"]
    min_cluster_size = max(cfg["min_cluster_size_floor"], round(cfg["min_cluster_size_pct_of_corpus"] * max(1, len(residual))))
    if len(residual) >= min_cluster_size and len(residual) >= 4:
        client = LLMClient(cost_tracker=CostTracker(max_cost_usd=max_cost_usd or get_settings().aisle_max_cost_usd))
        vectors = np.array([d["vector"] for d in residual], dtype=np.float32)
        labels = run_umap_hdbscan(vectors, random_state=scoring_config()["clustering"]["stability"]["seeds"][0])
        cluster_texts = {int(cid): [residual[i]["raw_text"] for i in range(len(residual)) if labels[i] == cid] for cid in set(labels) if cid != -1}
        top_terms_by_cluster = c_tf_idf(cluster_texts)
        doc_ids = [d["document_id"] for d in residual]

        for cid, texts in cluster_texts.items():
            member_ids = [doc_ids[i] for i in range(len(residual)) if labels[i] == cid]
            medoid_ids = _medoid_doc_ids(vectors, doc_ids, labels, cid)
            medoid_texts = [residual[doc_ids.index(m)]["raw_text"] for m in medoid_ids]
            naming = name_theme(top_terms_by_cluster[cid], medoid_texts, client)
            taxonomy_node = _map_to_taxonomy(top_terms_by_cluster[cid], naming.label)
            centroid = vectors[[i for i in range(len(residual)) if labels[i] == cid]].mean(axis=0)
            centroid /= np.linalg.norm(centroid) or 1

            with get_conn() as conn:
                row = conn.execute(
                    """
                    INSERT INTO themes (run_id, label, description, taxonomy_node, doc_count, doc_total,
                                         first_seen_run, centroid, status)
                    VALUES (%s, %s, %s, %s, %s, 0, %s, %s, 'new')
                    RETURNING id
                    """,
                    (run_id, naming.label, naming.description, taxonomy_node, len(member_ids), run_id, centroid.tolist()),
                ).fetchone()
                theme_id = row["id"]
                for d in member_ids:
                    conn.execute(
                        "INSERT INTO theme_documents (theme_id, document_id, is_exemplar) VALUES (%s, %s, %s)",
                        (theme_id, d, d in medoid_ids),
                    )
                conn.commit()
            new_theme_ids.append(theme_id)

    # Recompute prevalence/CI/delta for every current + newly-created theme
    # against the grown corpus — the denominator moved for everyone, not
    # just themes that got new members this run.
    with get_conn() as conn:
        doc_total = _doc_total(conn)
        all_theme_ids = [t["id"] for t in current_themes] + new_theme_ids
        updated = []
        for theme_id in all_theme_ids:
            theme = conn.execute("SELECT * FROM themes WHERE id = %s", (theme_id,)).fetchone()
            doc_count = conn.execute("SELECT count(*) AS n FROM theme_documents WHERE theme_id = %s", (theme_id,)).fetchone()["n"]
            prevalence, ci_low, ci_high = wilson_ci(doc_count, doc_total)

            old_prevalence, old_ci_low, old_ci_high = theme["prevalence"], theme["ci_low"], theme["ci_high"]
            moved_beyond_prior_ci = old_ci_low is not None and not (old_ci_low <= prevalence <= old_ci_high)
            delta = round(prevalence - old_prevalence, 4) if old_prevalence is not None else None
            if theme_id in new_theme_ids:
                status = "new"
            elif delta is not None and old_prevalence and abs(delta / old_prevalence) > 0.2:
                status = "growing" if delta > 0 else "decaying"
            else:
                status = "stable"

            members = conn.execute(
                """
                SELECT s.name AS source_name, s.brand, c.segment_label, c.categories_mentioned
                FROM theme_documents td JOIN documents d ON d.id = td.document_id
                JOIN sources s ON s.id = d.source_id JOIN classifications c ON c.document_id = d.id
                WHERE td.theme_id = %s
                """,
                (theme_id,),
            ).fetchall()
            source_counts, brand_counts, segment_counts, category_counts = {}, {}, {}, {}
            for m in members:
                source_counts[m["source_name"]] = source_counts.get(m["source_name"], 0) + 1
                brand_counts[m["brand"]] = brand_counts.get(m["brand"], 0) + 1
                if m["segment_label"]:
                    segment_counts[m["segment_label"]] = segment_counts.get(m["segment_label"], 0) + 1
                for cat in m["categories_mentioned"] or []:
                    category_counts[cat] = category_counts.get(cat, 0) + 1

            conn.execute(
                """
                UPDATE themes SET run_id = %s, doc_count = %s, doc_total = %s, prevalence = %s, ci_low = %s,
                                   ci_high = %s, delta_vs_prev_run = %s, status = %s, source_spread_json = %s
                WHERE id = %s
                """,
                (
                    run_id, doc_count, doc_total, prevalence, ci_low, ci_high, delta, status,
                    json.dumps({"sources": source_counts, "brands": brand_counts, "segments": segment_counts, "categories": category_counts}),
                    theme_id,
                ),
            )
            conn.commit()
            updated.append(
                {"theme_id": theme_id, "doc_count": doc_count, "prevalence": prevalence, "delta": delta,
                 "status": status, "moved_beyond_prior_ci": moved_beyond_prior_ci}
            )

    return {
        "embed_stats": embed_stats,
        "new_docs": len(new_docs),
        "assigned_to_existing": sum(assigned_counts.values()),
        "residual_size": len(residual),
        "new_themes_created": len(new_theme_ids),
        "themes": updated,
    }
