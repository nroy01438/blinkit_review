"""CLI entrypoint for Phase 5. Usage: python -m aisle.insights.run --run-id N [--max-cost-usd X]

Generates insights for every theme in an existing clustering run (see
`python -m aisle.cluster.run`, Phase 4) — insight generation is a separate
step from clustering, not fused into it, so re-running insight generation
alone (e.g. after a prompt-version bump) never needs to re-cluster.
"""
from __future__ import annotations

import argparse
import json

from aisle.db.connection import get_conn
from aisle.insights.generate import generate_insights_for_run


def _latest_run_id() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT run_id FROM themes ORDER BY run_id DESC LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("No theme-clustering run found — run `python -m aisle.cluster.run` first.")
    return row["run_id"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, default=None, help="defaults to the most recent clustering run")
    parser.add_argument("--max-cost-usd", type=float, default=None)
    args = parser.parse_args()
    run_id = args.run_id or _latest_run_id()
    result = generate_insights_for_run(run_id, max_cost_usd=args.max_cost_usd)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
