"""The §9 negative-control experiment: 50 synthetic reviews describing a
plausible-but-fabricated problem (a "hidden discovery tax") were injected
into the seed corpus by `aisle.ingest.generate_synthetic_corpus`, tagged
`meta_json.negative_control=true` — a tag nothing in the classify/cluster/
insight pipeline ever reads. This module is the *only* place that flag is
read, and only after the fact, to grade the pipeline's own output: did any
insight built substantially from fabricated evidence land a high IQS grade?

A trustworthy engine either doesn't surface the fabricated theme prominently
(low prevalence/low doc_count) or, if it does, gives it a low IQS grade. If
a majority-fabricated insight lands an A or B, the IQS formula (or this
pipeline) is broken and that must be reported, not hidden — see README.
"""
from __future__ import annotations

from aisle.db.connection import get_conn

AT_RISK_GRADE_THRESHOLD = {"A", "B"}
MAJORITY_FRACTION = 0.5


def negative_control_document_count() -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT count(*) AS n FROM documents WHERE meta_json->>'negative_control' = 'true'"
        ).fetchone()["n"]


def run_negative_control_check(run_id: int | None = None) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT i.id AS insight_id, i.title, i.grade, i.iqs_total, i.theme_ids,
                   count(*) AS theme_doc_count,
                   sum(CASE WHEN d.meta_json->>'negative_control' = 'true' THEN 1 ELSE 0 END) AS negative_control_count
            FROM insights i
            JOIN themes t ON t.id = ANY(i.theme_ids)
            JOIN theme_documents td ON td.theme_id = t.id
            JOIN documents d ON d.id = td.document_id
            WHERE (%s::bigint IS NULL OR i.run_id = %s::bigint)
            GROUP BY i.id, i.title, i.grade, i.iqs_total, i.theme_ids
            """,
            (run_id, run_id),
        ).fetchall()

    total_nc_docs = negative_control_document_count()
    at_risk = []
    for r in rows:
        fraction = r["negative_control_count"] / r["theme_doc_count"] if r["theme_doc_count"] else 0
        if fraction >= MAJORITY_FRACTION:
            at_risk.append(
                {
                    "insight_id": r["insight_id"], "title": r["title"], "grade": r["grade"],
                    "iqs_total": r["iqs_total"], "negative_control_fraction": round(fraction, 3),
                    "theme_doc_count": r["theme_doc_count"],
                }
            )

    broken = [i for i in at_risk if i["grade"] in AT_RISK_GRADE_THRESHOLD]
    verdict = "FAIL" if broken else "PASS"
    explanation = (
        f"{len(broken)} majority-fabricated insight(s) scored A/B — the IQS formula (or this pipeline) is "
        f"not catching synthetic/templated evidence; see README for the honest writeup."
        if broken
        else (
            f"No majority-fabricated insight scored above C. {len(at_risk)} insight(s) were majority-composed "
            f"of the {total_nc_docs} negative-control documents, but IQS correctly kept "
            f"{'them' if at_risk else 'any such theme'} at C/D."
            if at_risk
            else f"None of the {total_nc_docs} negative-control documents ended up majority-composing any generated insight."
        )
    )
    return {
        "verdict": verdict, "explanation": explanation, "total_negative_control_docs": total_nc_docs,
        "majority_fabricated_insights": at_risk, "broken_insights": broken,
    }
