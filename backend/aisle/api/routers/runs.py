"""Backend for /workflow — the animated pipeline-provenance screen. Reads
`runs.stage_stats_json` directly (never a static asset), per §11's explicit
requirement that this screen not be a static PNG.
"""
from __future__ import annotations

from fastapi import APIRouter

from aisle.db.connection import get_conn

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
def list_runs(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, started_at, finished_at, trigger, status, cost_usd, stage_stats_json
            FROM runs ORDER BY id DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{run_id}")
def get_run(run_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, started_at, finished_at, trigger, status, cost_usd, stage_stats_json, config_snapshot_json FROM runs WHERE id = %s",
            (run_id,),
        ).fetchone()
    return dict(row) if row else None


@router.get("/{run_id}/documents/sample")
def get_run_document_sample(run_id: int, killed: bool = False, limit: int = 10) -> list[dict]:
    """10 sample docs that passed / that were killed (with reason) — §11's
    click-a-workflow-node drill-down. Runs don't record which documents they
    touched directly, so this samples from `classifications` created in the
    same window as the run instead (best-effort, documented as such).
    """
    with get_conn() as conn:
        run = conn.execute("SELECT started_at, finished_at FROM runs WHERE id = %s", (run_id,)).fetchone()
        if run is None:
            return []
        rows = conn.execute(
            """
            SELECT d.id AS document_id, d.raw_text, c.is_junk, c.junk_reason, c.pm_verdict, c.discovery_relevance
            FROM classifications c JOIN documents d ON d.id = c.document_id
            WHERE c.created_at BETWEEN %s AND coalesce(%s, now()) AND c.is_junk = %s
            ORDER BY c.id LIMIT %s
            """,
            (run["started_at"], run["finished_at"], killed, limit),
        ).fetchall()
    return [dict(r) for r in rows]
