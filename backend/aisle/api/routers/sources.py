"""Backend for /admin's source registry + on-demand pipeline triggers. The
"Run Now" endpoints are synchronous (fine at this corpus's size) — a real
deployment would enqueue these instead of blocking the request.
"""
from __future__ import annotations

from fastapi import APIRouter

from aisle.db.connection import get_conn

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/sources")
def list_sources() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, kind, brand, is_active, last_fetched_at, config_json FROM sources ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/run/ingest")
def run_ingest(dry_run: bool = False, limit_per_source: int = 100) -> dict:
    from aisle.ingest.runner import run_ingestion

    return run_ingestion(trigger="manual", limit_per_source=limit_per_source, dry_run=dry_run)


@router.post("/run/classify")
def run_classify_now(limit: int = 2000) -> dict:
    from aisle.classify.run import run_classification

    return run_classification(limit=limit, trigger="manual")


@router.post("/run/cluster")
def run_cluster_now() -> dict:
    from aisle.cluster.themes import run_theme_clustering

    return run_theme_clustering(trigger="manual")


@router.post("/run/insights")
def run_insights_now(run_id: int | None = None) -> dict:
    from aisle.insights.generate import generate_insights_for_run

    if run_id is None:
        with get_conn() as conn:
            row = conn.execute("SELECT run_id FROM themes ORDER BY run_id DESC LIMIT 1").fetchone()
        if row is None:
            return {"error": "no clustering run found — run cluster first"}
        run_id = row["run_id"]
    return generate_insights_for_run(run_id)
