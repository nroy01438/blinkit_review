"""Backend for `/` — the overview dashboard (§11)."""
from __future__ import annotations

from fastapi import APIRouter

from aisle.db.connection import get_conn
from aisle.eval import metrics as metrics_module

router = APIRouter(tags=["overview"])


@router.get("/overview")
def overview() -> dict:
    with get_conn() as conn:
        fetched = conn.execute("SELECT count(*) AS n FROM documents").fetchone()["n"]
        deduped = conn.execute("SELECT count(*) AS n FROM documents WHERE dupe_of_id IS NULL").fetchone()["n"]
        non_junk = conn.execute(
            "SELECT count(*) AS n FROM classifications c JOIN documents d ON d.id = c.document_id WHERE d.dupe_of_id IS NULL AND c.is_junk = false"
        ).fetchone()["n"]
        high_utility = conn.execute(
            "SELECT count(*) AS n FROM classifications c JOIN documents d ON d.id = c.document_id WHERE d.dupe_of_id IS NULL AND c.is_junk = false AND c.pm_verdict = 'high_signal'"
        ).fetchone()["n"]
        relevant = conn.execute(
            "SELECT count(*) AS n FROM classifications c JOIN documents d ON d.id = c.document_id WHERE d.dupe_of_id IS NULL AND c.is_junk = false AND c.discovery_relevance >= 2"
        ).fetchone()["n"]

        source_mix = conn.execute(
            "SELECT s.name, s.brand, count(*) AS n FROM documents d JOIN sources s ON s.id = d.source_id WHERE d.dupe_of_id IS NULL GROUP BY 1, 2 ORDER BY n DESC"
        ).fetchall()
        lang_mix = conn.execute(
            "SELECT coalesce(lang_detected, 'unknown') AS lang, count(*) AS n FROM documents WHERE dupe_of_id IS NULL GROUP BY 1 ORDER BY n DESC"
        ).fetchall()
        sentiment_mix = conn.execute(
            "SELECT coalesce(sentiment, 'unknown') AS sentiment, count(*) AS n FROM classifications GROUP BY 1 ORDER BY n DESC"
        ).fetchall()

        latest_run_id = conn.execute("SELECT run_id FROM themes ORDER BY run_id DESC LIMIT 1").fetchone()
        top_themes = []
        if latest_run_id:
            top_themes = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, label, doc_count, doc_total, prevalence, ci_low, ci_high, status, delta_vs_prev_run "
                    "FROM themes WHERE run_id = %s ORDER BY prevalence DESC LIMIT 5",
                    (latest_run_id["run_id"],),
                ).fetchall()
            ]

        top_insights = [
            dict(r)
            for r in conn.execute(
                """
                SELECT i.id, i.title, i.grade, i.iqs_total, i.prevalence, i.ci_low, i.ci_high,
                       t.doc_count, t.doc_total
                FROM insights i
                LEFT JOIN themes t ON t.id = i.theme_ids[1]
                WHERE i.grade = 'A' ORDER BY i.iqs_total DESC LIMIT 3
                """
            ).fetchall()
        ]

        cost_total = conn.execute("SELECT coalesce(sum(cost_usd), 0) AS n FROM runs").fetchone()["n"]
        classified_count = conn.execute("SELECT count(*) AS n FROM classifications").fetchone()["n"]

    abstention = metrics_module.abstention_rate("pmgate.v1")
    gate = metrics_module.acceptance_gate("synthetic_proxy_v1")

    funnel = [
        {"stage": "fetched", "n": fetched, "retention_pct": 100.0},
        {"stage": "deduped", "n": deduped, "retention_pct": round(100 * deduped / fetched, 1) if fetched else 0},
        {"stage": "non_junk", "n": non_junk, "retention_pct": round(100 * non_junk / fetched, 1) if fetched else 0},
        {"stage": "high_utility", "n": high_utility, "retention_pct": round(100 * high_utility / fetched, 1) if fetched else 0},
        {"stage": "discovery_relevant", "n": relevant, "retention_pct": round(100 * relevant / fetched, 1) if fetched else 0},
    ]

    return {
        "funnel": funnel,
        "source_mix": [dict(r) for r in source_mix],
        "lang_mix": [dict(r) for r in lang_mix],
        "sentiment_mix": [dict(r) for r in sentiment_mix],
        "top_themes": top_themes,
        "top_insights": top_insights,
        "pmgate_health": {
            "kappa": gate["checks"]["kappa"]["value"],
            "stage1_junk_recall": gate["checks"]["stage1_junk_recall"]["value"],
            "stage3_relevance_f1": gate["checks"]["stage3_relevance_f1"]["value"],
            "abstention_rate": abstention["rate"],
            "cost_per_1k_docs_usd": round(1000 * float(cost_total) / classified_count, 4) if classified_count else 0,
            "acceptance_gate_passed": gate["all_passed"],
        },
    }
