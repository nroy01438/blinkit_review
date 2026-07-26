from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from aisle.db.connection import get_conn

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("")
def list_insights(grade: str | None = None, status: str | None = None, run_id: int | None = None) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT i.id, i.run_id, i.theme_ids, i.title, i.statement, i.so_what, i.opportunity,
                   i.affected_segments, i.affected_categories, i.prevalence, i.ci_low, i.ci_high,
                   i.counter_evidence, i.iqs_total, i.iqs_breakdown_json, i.grade, i.status, i.created_at,
                   t.doc_count, t.doc_total
            FROM insights i
            LEFT JOIN themes t ON t.id = i.theme_ids[1]
            WHERE (%s::text IS NULL OR i.grade = %s::text)
              AND (%s::text IS NULL OR i.status = %s::text)
              AND (%s::bigint IS NULL OR i.run_id = %s::bigint)
            ORDER BY i.iqs_total DESC
            """,
            (grade, grade, status, status, run_id, run_id),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{insight_id}")
def get_insight(insight_id: int) -> dict | None:
    with get_conn() as conn:
        insight = conn.execute(
            """
            SELECT i.*, t.doc_count, t.doc_total, t.label AS theme_label
            FROM insights i LEFT JOIN themes t ON t.id = i.theme_ids[1]
            WHERE i.id = %s
            """,
            (insight_id,),
        ).fetchone()
        if insight is None:
            return None
        evidence = conn.execute(
            """
            SELECT ie.id, ie.document_id, ie.quote, ie.supports, d.posted_at, s.name AS source_name, s.brand
            FROM insight_evidence ie JOIN documents d ON d.id = ie.document_id JOIN sources s ON s.id = d.source_id
            WHERE ie.insight_id = %s
            """,
            (insight_id,),
        ).fetchall()
    result = dict(insight)
    result["evidence"] = [dict(e) for e in evidence]
    return result


class StatusUpdate(BaseModel):
    status: str  # 'human_approved' | 'human_rejected'


@router.post("/{insight_id}/status")
def update_insight_status(insight_id: int, payload: StatusUpdate) -> dict:
    if payload.status not in ("human_approved", "human_rejected", "auto"):
        return {"error": f"invalid status {payload.status!r}"}
    with get_conn() as conn:
        conn.execute("UPDATE insights SET status = %s WHERE id = %s", (payload.status, insight_id))
        conn.commit()
    return {"status": "ok"}
