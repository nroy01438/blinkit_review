"""CLI entrypoint for Phase 4. Usage: python -m aisle.cluster.run [--max-cost-usd X]"""
from __future__ import annotations

import argparse
import json

from aisle.cluster.themes import run_theme_clustering


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cost-usd", type=float, default=None)
    parser.add_argument("--trigger", type=str, default="manual", choices=["manual", "cron", "upload"])
    args = parser.parse_args()
    result = run_theme_clustering(trigger=args.trigger, max_cost_usd=args.max_cost_usd)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
