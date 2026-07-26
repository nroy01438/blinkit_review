"""Runs the PM-Gate cascade over every document that doesn't yet have a
classification row for the current schema_version (near-dupes — `dupe_of_id
IS NOT NULL` — are skipped entirely; they're excluded from every downstream
denominator anyway). Respects --max-cost-usd as a hard stop mid-run.

Usage: python -m aisle.classify.run [--limit N] [--max-cost-usd X]
"""
from __future__ import annotations

import argparse
import json

from aisle.classify.pmgate.cascade import SCHEMA_VERSION, classify_document
from aisle.db.connection import get_conn
from aisle.llm.client import LLMClient
from aisle.llm.cost import CostTracker, MaxCostExceededError
from aisle.settings import get_settings


def _pending_documents(limit: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT d.id, d.raw_text FROM documents d
            LEFT JOIN classifications c ON c.document_id = d.id AND c.schema_version = %s
            WHERE c.id IS NULL AND d.dupe_of_id IS NULL
            ORDER BY d.id
            LIMIT %s
            """,
            (SCHEMA_VERSION, limit),
        ).fetchall()


def run_classification(*, limit: int = 10_000, max_cost_usd: float | None = None, trigger: str = "manual") -> dict:
    settings = get_settings()
    cost_tracker = CostTracker(max_cost_usd=max_cost_usd if max_cost_usd is not None else settings.aisle_max_cost_usd)
    client = LLMClient(cost_tracker=cost_tracker)

    docs = _pending_documents(limit)
    with get_conn() as conn:
        run_row = conn.execute("INSERT INTO runs (trigger, status) VALUES (%s, 'running') RETURNING id", (trigger,)).fetchone()
        conn.commit()
        run_id = run_row["id"]

    kill_reasons: dict[str, int] = {}
    verdicts: dict[str, int] = {}
    abstained = 0
    processed = 0
    stopped_early = False

    for doc in docs:
        try:
            result = classify_document(doc["id"], doc["raw_text"], client)
        except MaxCostExceededError:
            stopped_early = True
            break
        processed += 1
        if result.get("is_junk"):
            kill_reasons[result.get("junk_reason") or "unspecified"] = kill_reasons.get(result.get("junk_reason") or "unspecified", 0) + 1
        elif result.get("pm_verdict"):
            verdicts[result["pm_verdict"]] = verdicts.get(result["pm_verdict"], 0) + 1
        if result.get("abstained"):
            abstained += 1

    stats = {
        "processed": processed,
        "pending_before_run": len(docs),
        "kill_reasons": kill_reasons,
        "pm_verdicts": verdicts,
        "abstention_rate": round(abstained / processed, 4) if processed else 0.0,
        "cost_usd": round(cost_tracker.cost_usd, 4),
        "tokens_in": cost_tracker.tokens_in,
        "tokens_out": cost_tracker.tokens_out,
        "stopped_early_on_cost": stopped_early,
    }
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = now(), status = %s, stage_stats_json = %s, cost_usd = %s WHERE id = %s",
            ("partial" if stopped_early else "completed", json.dumps(stats), stats["cost_usd"], run_id),
        )
        conn.commit()
    return {"run_id": run_id, **stats}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument("--max-cost-usd", type=float, default=None)
    parser.add_argument("--trigger", type=str, default="manual", choices=["manual", "cron", "upload"])
    args = parser.parse_args()
    result = run_classification(limit=args.limit, max_cost_usd=args.max_cost_usd, trigger=args.trigger)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
