"""The five tools available to the QnA agent (§11) — so it can *compute*,
not just retrieve. Each is a plain, independently-callable, independently-
testable Python function; `agent.py` decides which to invoke.
"""
from __future__ import annotations

from aisle.db.connection import get_conn
from aisle.insights.stats import two_proportion_z_test, wilson_ci
from aisle.qa.retrieval import hybrid_search

FILTER_COLUMNS = {
    "barrier_code": ("c.barrier_codes", "ANY"),
    "behaviour_code": ("c.behaviour_codes", "ANY"),
    "category": ("c.categories_mentioned", "ANY"),
    "segment": ("c.segment_label", "EQ"),
    "sentiment": ("c.sentiment", "EQ"),
    "brand": ("s.brand", "EQ"),
}


def search_reviews(query: str, top_k: int = 10) -> list[dict]:
    docs = hybrid_search(query, top_k=top_k)
    return [
        {
            "document_id": d["document_id"],
            "quote": d["raw_text"][:400],
            "source_name": d["source_name"],
            "brand": d["brand"],
            "posted_at": str(d["posted_at"]) if d["posted_at"] else None,
            "segment_label": d["segment_label"],
        }
        for d in docs
    ]


def get_theme_stats(theme_id: int | None = None, label_contains: str | None = None) -> dict | None:
    with get_conn() as conn:
        if theme_id is not None:
            row = conn.execute("SELECT * FROM themes WHERE id = %s", (theme_id,)).fetchone()
        elif label_contains:
            row = conn.execute(
                "SELECT * FROM themes WHERE label ILIKE %s ORDER BY run_id DESC LIMIT 1", (f"%{label_contains}%",)
            ).fetchone()
        else:
            return None
    if row is None:
        return None
    result = dict(row)
    result.pop("centroid", None)
    return result


def _filter_clause(filters: dict) -> tuple[str, list]:
    clauses, params = [], []
    for key, value in (filters or {}).items():
        if key not in FILTER_COLUMNS or value is None:
            continue
        column, kind = FILTER_COLUMNS[key]
        if kind == "ANY":
            clauses.append(f"%s = ANY({column})")
        else:
            clauses.append(f"{column} = %s")
        params.append(value)
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


def compute_prevalence(filters: dict, relevance_floor: int = 2) -> dict:
    """(successes, n) among the discovery-relevant, non-junk, non-dupe
    corpus, plus the Wilson 95% CI — never returned as a naked percentage.
    """
    clause, params = _filter_clause(filters)
    with get_conn() as conn:
        n = conn.execute(
            """
            SELECT count(*) AS n FROM documents d JOIN classifications c ON c.document_id = d.id
            JOIN sources s ON s.id = d.source_id
            WHERE d.dupe_of_id IS NULL AND c.is_junk = false AND c.discovery_relevance >= %s
            """,
            (relevance_floor,),
        ).fetchone()["n"]
        successes = conn.execute(
            f"""
            SELECT count(*) AS n FROM documents d JOIN classifications c ON c.document_id = d.id
            JOIN sources s ON s.id = d.source_id
            WHERE d.dupe_of_id IS NULL AND c.is_junk = false AND c.discovery_relevance >= %s {clause}
            """,
            (relevance_floor, *params),
        ).fetchone()["n"]
    rate, ci_low, ci_high = wilson_ci(successes, n)
    return {"successes": successes, "n": n, "rate": rate, "ci_low": ci_low, "ci_high": ci_high, "filters": filters}


def run_segment_comparison(segment_a: str, segment_b: str, filters: dict | None = None, relevance_floor: int = 2) -> dict:
    """Two-proportion z-test between two segments' rates of matching
    `filters` (default: any discovery-relevant document at all) — the real
    statistical test §7/§11 require for any segment-difference claim.
    """
    filters = dict(filters or {})
    clause, params = _filter_clause(filters)
    with get_conn() as conn:

        def cohort(segment: str) -> tuple[int, int]:
            n = conn.execute(
                """
                SELECT count(*) AS n FROM documents d JOIN classifications c ON c.document_id = d.id
                WHERE d.dupe_of_id IS NULL AND c.is_junk = false AND c.discovery_relevance >= %s AND c.segment_label = %s
                """,
                (relevance_floor, segment),
            ).fetchone()["n"]
            successes = conn.execute(
                f"""
                SELECT count(*) AS n FROM documents d JOIN classifications c ON c.document_id = d.id
                JOIN sources s ON s.id = d.source_id
                WHERE d.dupe_of_id IS NULL AND c.is_junk = false AND c.discovery_relevance >= %s
                  AND c.segment_label = %s {clause}
                """,
                (relevance_floor, segment, *params),
            ).fetchone()["n"]
            return successes, n

        successes_a, n_a = cohort(segment_a)
        successes_b, n_b = cohort(segment_b)

    rate_a, ci_low_a, ci_high_a = wilson_ci(successes_a, n_a)
    rate_b, ci_low_b, ci_high_b = wilson_ci(successes_b, n_b)
    z, p = two_proportion_z_test(successes_a, n_a, successes_b, n_b)
    return {
        "segment_a": {"label": segment_a, "successes": successes_a, "n": n_a, "rate": rate_a, "ci_low": ci_low_a, "ci_high": ci_high_a},
        "segment_b": {"label": segment_b, "successes": successes_b, "n": n_b, "rate": rate_b, "ci_low": ci_low_b, "ci_high": ci_high_b},
        "z": round(z, 3),
        "p_value": round(p, 4),
        "significant_at_0_05": p < 0.05,
    }


def get_insight(insight_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT i.*, t.doc_count, t.doc_total FROM insights i
            LEFT JOIN themes t ON t.id = i.theme_ids[1] WHERE i.id = %s
            """,
            (insight_id,),
        ).fetchone()
    return dict(row) if row else None
