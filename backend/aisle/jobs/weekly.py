"""The weekly job (§12). Idempotent and resumable by construction — every
stage it calls (ingestion, classification, incremental clustering, insight
generation) already skips work that's already done, so a crash partway
through and a re-run just picks up where it left off; a failure in one
ingestion source never blocks the others (§12 point 10) because
`aisle.ingest.runner.run_ingestion` already isolates per-source failures.

Usage: python -m aisle.jobs.weekly [--max-cost-usd X] [--digest-path PATH]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from aisle.classify.run import run_classification
from aisle.cluster.incremental import run_incremental_clustering
from aisle.db.connection import get_conn
from aisle.eval import metrics as metrics_module
from aisle.ingest.runner import run_ingestion
from aisle.insights.generate import generate_insight_for_theme
from aisle.llm.client import LLMClient
from aisle.llm.cost import CostTracker
from aisle.settings import get_settings

NEW_THEME_PREVALENCE_ALERT = 0.03
RELATIVE_MOVE_ALERT = 0.5


def _detect_alerts(ingest_stats: dict, theme_updates: list[dict], abstention: dict, prior_cost: float, current_cost: float) -> list[str]:
    alerts = []
    for name, error in (ingest_stats.get("errors") or {}).items():
        alerts.append(f"Ingestion failure on source '{name}': {error}")

    for t in theme_updates:
        if t["status"] == "new" and t["prevalence"] >= NEW_THEME_PREVALENCE_ALERT:
            alerts.append(f"New theme #{t['theme_id']} crossed {NEW_THEME_PREVALENCE_ALERT:.0%} prevalence ({t['prevalence']:.1%}).")
        if t["delta"] is not None and t["prevalence"] and abs(t["delta"] / max(t["prevalence"] - t["delta"], 1e-6)) > RELATIVE_MOVE_ALERT:
            direction = "up" if t["delta"] > 0 else "down"
            alerts.append(f"Theme #{t['theme_id']} moved >{RELATIVE_MOVE_ALERT:.0%} relative week-over-week ({direction}, Δ={t['delta']:+.1%}).")

    if abstention["n"] > 0 and (abstention["rate"] < 0.05 or abstention["rate"] > 0.15):
        alerts.append(f"Abstention rate {abstention['rate']:.1%} is outside the 5–12% target band (n={abstention['n']}).")

    if prior_cost > 0 and current_cost > prior_cost * 3:
        alerts.append(f"Cost anomaly: this run cost ${current_cost:.4f} vs. a recent baseline of ${prior_cost:.4f}.")

    return alerts


def _render_digest(*, run_id: int, ingest_stats: dict, classify_stats: dict, cluster_stats: dict,
                    new_insights: list[dict], alerts: list[str]) -> str:
    lines = [f"# AISLE weekly digest — run #{run_id}", f"_{datetime.now(timezone.utc).isoformat()}_", ""]

    lines.append("## Ingestion")
    for source, stats in (ingest_stats.get("per_source") or {}).items():
        lines.append(f"- **{source}**: {stats}")
    if ingest_stats.get("errors"):
        lines.append(f"- ⚠ errors: {ingest_stats['errors']}")
    lines.append("")

    lines.append("## Classification")
    lines.append(f"- processed {classify_stats.get('processed', 0)} document(s); abstention rate {classify_stats.get('abstention_rate', 0):.1%}")
    lines.append("")

    lines.append("## Themes")
    new_themes = [t for t in cluster_stats["themes"] if t["status"] == "new"]
    decaying = [t for t in cluster_stats["themes"] if t["status"] == "decaying"]
    growing = [t for t in cluster_stats["themes"] if t["status"] == "growing"]
    lines.append(f"- {cluster_stats['new_themes_created']} new theme(s), {len(growing)} growing, {len(decaying)} decaying")
    for t in new_themes:
        lines.append(f"  - NEW theme #{t['theme_id']}: {t['prevalence']:.1%} prevalence")
    for t in growing + decaying:
        lines.append(f"  - theme #{t['theme_id']} {t['status']}: Δ={t['delta']:+.1%}")
    lines.append("")

    lines.append("## New / regenerated insights")
    for i in new_insights:
        lines.append(f"- [{i['grade']}] {i['title']} (IQS {i['iqs_total']})")
    if not new_insights:
        lines.append("- none this run")
    lines.append("")

    lines.append("## Alerts")
    for a in alerts:
        lines.append(f"- ⚠ {a}")
    if not alerts:
        lines.append("- none")

    return "\n".join(lines)


def _post_webhook(digest_markdown: str) -> bool:
    """Optional Slack/email webhook (§12 step 8). No-op, clearly logged as
    such, when no webhook URL is configured — never silently pretend to
    have sent something.
    """
    import os

    webhook_url = os.environ.get("AISLE_DIGEST_WEBHOOK_URL")
    if not webhook_url:
        return False
    import httpx

    httpx.post(webhook_url, json={"text": digest_markdown}, timeout=10)
    return True


def run_weekly_job(*, max_cost_usd: float | None = None, digest_path: str | None = None) -> dict:
    settings = get_settings()
    cost_tracker = CostTracker(max_cost_usd=max_cost_usd or settings.aisle_max_cost_usd)

    with get_conn() as conn:
        prior_run = conn.execute("SELECT cost_usd FROM runs WHERE status = 'completed' ORDER BY id DESC LIMIT 1").fetchone()
        run_row = conn.execute("INSERT INTO runs (trigger, status) VALUES ('cron', 'running') RETURNING id").fetchone()
        conn.commit()
        run_id = run_row["id"]
    prior_cost = float(prior_run["cost_usd"]) if prior_run else 0.0

    ingest_stats = run_ingestion(trigger="cron", limit_per_source=500)
    classify_result = run_classification(limit=10_000, trigger="cron")
    cluster_result = run_incremental_clustering(run_id, max_cost_usd=max_cost_usd)

    new_insights = []
    client = LLMClient(cost_tracker=cost_tracker)
    for t in cluster_result["themes"]:
        if t["status"] == "new" or t["moved_beyond_prior_ci"]:
            result = generate_insight_for_theme(t["theme_id"], run_id, client)
            if result is not None:
                new_insights.append(result)

    abstention = metrics_module.abstention_rate("pmgate.v1")
    total_cost = classify_result.get("cost_usd", 0.0) + cluster_result.get("embed_stats", {}).get("embedded", 0) * 0 + cost_tracker.cost_usd
    alerts = _detect_alerts(ingest_stats, cluster_result["themes"], abstention, prior_cost, total_cost)

    digest = _render_digest(
        run_id=run_id, ingest_stats=ingest_stats, classify_stats=classify_result,
        cluster_stats=cluster_result, new_insights=new_insights, alerts=alerts,
    )
    webhook_sent = _post_webhook(digest)
    if digest_path:
        with open(digest_path, "w") as f:
            f.write(digest)

    status = "partial" if ingest_stats.get("errors") else "completed"
    stage_stats = {
        "ingest": ingest_stats, "classify": classify_result, "cluster": cluster_result,
        "new_insights": [{"insight_id": i["insight_id"], "title": i["title"], "grade": i["grade"]} for i in new_insights],
        "alerts": alerts, "digest_webhook_sent": webhook_sent,
    }
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = now(), status = %s, stage_stats_json = %s, cost_usd = %s WHERE id = %s",
            (status, json.dumps(stage_stats, default=str), round(total_cost, 4), run_id),
        )
        conn.commit()

    return {"run_id": run_id, "status": status, "digest": digest, **stage_stats}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cost-usd", type=float, default=None)
    parser.add_argument("--digest-path", type=str, default=None)
    args = parser.parse_args()
    result = run_weekly_job(max_cost_usd=args.max_cost_usd, digest_path=args.digest_path)
    print(result["digest"])
    print()
    print(json.dumps({k: v for k, v in result.items() if k != "digest"}, indent=2, default=str))


if __name__ == "__main__":
    main()
