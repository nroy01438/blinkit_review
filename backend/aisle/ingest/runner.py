"""Orchestrates incremental ingestion across every active source. A failure
in one connector never blocks the rest (§12) — it's recorded in the run's
stage_stats_json under `errors` and the runner moves on.

Usage: python -m aisle.ingest.runner [--limit-per-source N] [--dry-run] [--only SOURCE_NAME]
"""
from __future__ import annotations

import argparse
import json

from aisle.db.connection import get_conn
from aisle.ingest.pipeline import run_source_ingestion


def _start_run(trigger: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO runs (trigger, status) VALUES (%s, 'running') RETURNING id", (trigger,)
        ).fetchone()
        conn.commit()
        return row["id"]


def _finish_run(run_id: int, stage_stats: dict, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = now(), stage_stats_json = %s, status = %s WHERE id = %s",
            (json.dumps(stage_stats), status, run_id),
        )
        conn.commit()


def run_ingestion(*, trigger: str = "manual", limit_per_source: int = 500, dry_run: bool = False, only: str | None = None) -> dict:
    run_id = _start_run(trigger)
    with get_conn() as conn:
        sources = conn.execute(
            "SELECT id, name, kind, config_json, is_active, last_fetched_at FROM sources WHERE is_active = true"
        ).fetchall()

    per_source: dict = {}
    errors: dict = {}
    for s in sources:
        if only is not None and s["name"] != only:
            continue
        if s["kind"] in ("social", "manual_upload") and not dry_run:
            continue  # these have no scheduled fetch path — see their connector docstrings
        try:
            result = run_source_ingestion(
                s["id"], s["name"], s["kind"], s["config_json"],
                since=s["last_fetched_at"], limit=limit_per_source, dry_run=dry_run,
            )
            per_source[s["name"]] = result
        except Exception as e:  # noqa: BLE001 - one bad source must not kill the run
            errors[s["name"]] = str(e)

    status = "completed" if not errors else ("partial" if per_source else "failed")
    stage_stats = {"per_source": per_source, "errors": errors, "dry_run": dry_run}
    if not dry_run:
        _finish_run(run_id, stage_stats, status)
    return {"run_id": run_id, **stage_stats, "status": status}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-per-source", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", type=str, default=None)
    parser.add_argument("--trigger", type=str, default="manual", choices=["manual", "cron", "upload"])
    args = parser.parse_args()

    result = run_ingestion(
        trigger=args.trigger, limit_per_source=args.limit_per_source, dry_run=args.dry_run, only=args.only
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
