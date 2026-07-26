"""Local-dev equivalent of the GitHub Actions weekly cron (§12) —
APScheduler in-process. Production runs on the GitHub Action instead; this
is for exercising the weekly job on a schedule without needing a deployed
Action, e.g. while developing.

Usage: python -m aisle.jobs.scheduler
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from aisle.jobs.weekly import run_weekly_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _run_and_log() -> None:
    logger.info("Starting scheduled weekly job")
    result = run_weekly_job()
    logger.info("Weekly job finished: run_id=%s status=%s", result["run_id"], result["status"])


def main() -> None:
    scheduler = BlockingScheduler()
    # Monday 02:00 IST == Monday 20:30 UTC (previous day) — see .github/workflows/weekly.yml
    # for the exact UTC cron used in production; this local trigger matches it.
    scheduler.add_job(_run_and_log, CronTrigger(day_of_week="sun", hour=20, minute=30))
    logger.info("Scheduler started — weekly job will fire Sunday 20:30 UTC (Monday 02:00 IST)")
    scheduler.start()


if __name__ == "__main__":
    main()
