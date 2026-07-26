"""Insight generation (§8): for each theme, assemble an evidence pack,
draft from that evidence only, run an isolated adversarial counter-evidence
pass, verify groundedness/actionability/novelty, test any segment-difference
claim, score IQS, and persist. Deliberately theme-by-theme, not
theme-*pairs* — the brief calls interaction insights out as valuable, but
generating them well needs a much larger corpus to have pairs worth testing
at this corpus's size; scoped out rather than done badly (see README).
"""
from __future__ import annotations

import json

from aisle.insights import mock as mock_module
from aisle.insights.evidence import assemble_evidence_pack, segment_cohort_rate
from aisle.insights.iqs import compute_iqs
from aisle.insights.schemas import AdversarialCritique, InsightDraft, IQSVerification
from aisle.insights.stats import two_proportion_z_test, wilson_ci
from aisle.db.connection import get_conn
from aisle.llm.client import LLMClient
from aisle.settings import get_settings

MIN_DOC_COUNT_FOR_INSIGHT = 5
DRAFT_PROMPT_VERSION = "insight_draft.v1"
ADVERSARIAL_PROMPT_VERSION = "insight_adversarial.v1"
VERIFY_PROMPT_VERSION = "insight_verify.v1"


def _segment_stats(theme_id: int, source_spread: dict) -> list[dict]:
    stats = []
    for segment_label, count in (source_spread.get("segments") or {}).items():
        successes, n = segment_cohort_rate(segment_label, theme_id)
        rate, ci_low, ci_high = wilson_ci(successes, n)
        stats.append({"segment_label": segment_label, "n": n, "successes": successes, "rate": rate, "ci_low": ci_low, "ci_high": ci_high})
    stats.sort(key=lambda s: -s["n"])

    if len(stats) >= 2:
        a, b = stats[0], stats[1]
        z, p = two_proportion_z_test(a["successes"], a["n"], b["successes"], b["n"])
        for s in (a, b):
            s["z_test_vs_other_top_segment"] = {"z": round(z, 3), "p_value": round(p, 4), "significant_at_0_05": p < 0.05}
    return stats


def draft_insight(theme: dict, evidence_pack: list[dict], client: LLMClient) -> InsightDraft:
    evidence_snippets = [e["raw_text"][:300] for e in evidence_pack]
    categories = sorted({cat for e in evidence_pack for cat in (e["categories_mentioned"] or [])})
    segment_stats = _segment_stats(theme["id"], theme["source_spread"])

    prompt = (
        f"Draft a PM insight from ONLY the evidence below. Do not generalise beyond these documents; "
        f"if the evidence doesn't support a confident claim, set confident=false and say so plainly.\n\n"
        f"Theme: {theme['label']} — {theme['description']}\n"
        f"Exact numbers to use verbatim (never invent your own): doc_count={theme['doc_count']}, "
        f"doc_total={theme['doc_total']}, prevalence={theme['prevalence']:.4f}, "
        f"ci_low={theme['ci_low']:.4f}, ci_high={theme['ci_high']:.4f}.\n"
        f"Segment rates: {json.dumps(segment_stats, default=str)}\n"
        f"Evidence snippets:\n" + "\n---\n".join(evidence_snippets[:20]) + "\n\n"
        'Respond with strict JSON: {"title": string, "statement": string, "so_what": string, '
        '"opportunity": string ("If we X, then Y, measured by Z"), "affected_segments": [string], '
        '"affected_categories": [string], "confident": bool}'
    )
    result = client.complete_json(
        prompt=prompt, response_model=InsightDraft, prompt_version=DRAFT_PROMPT_VERSION,
        model=get_settings().aisle_synth_model, stage="insight_draft",
        mock_response_factory=lambda: mock_module.mock_draft(
            theme_label=theme["label"], theme_description=theme["description"], doc_count=theme["doc_count"],
            doc_total=theme["doc_total"], prevalence=theme["prevalence"], ci_low=theme["ci_low"], ci_high=theme["ci_high"],
            evidence_snippets=evidence_snippets, segment_stats=segment_stats, categories=categories,
        ),
    )
    return result.parsed, segment_stats


def run_adversarial_pass(evidence_pack: list[dict], client: LLMClient) -> AdversarialCritique:
    texts = [e["raw_text"] for e in evidence_pack]
    sources = [e["source_name"] for e in evidence_pack]
    prompt = (
        "Here is a set of user-feedback documents (NOT the insight drafted from them — argue purely from "
        "the raw evidence). What's the strongest case that a pattern found in this evidence would be an "
        "artifact of sampling, of the platform, of a vocal minority, or of the question asked, rather than "
        "a real, generalisable finding?\n\n" + "\n---\n".join(t[:300] for t in texts[:20]) + "\n\n"
        'Respond with strict JSON: {"counter_evidence": string, "undermines_insight": bool}'
    )
    result = client.complete_json(
        prompt=prompt, response_model=AdversarialCritique, prompt_version=ADVERSARIAL_PROMPT_VERSION,
        model=get_settings().aisle_synth_model, stage="insight_adversarial",
        mock_response_factory=lambda: mock_module.mock_adversarial(texts, sources),
    )
    return result.parsed


def run_verification(draft: InsightDraft, evidence_pack: list[dict], client: LLMClient) -> IQSVerification:
    texts = [e["raw_text"] for e in evidence_pack]
    distinct_codes = len({c for e in evidence_pack for c in (e["categories_mentioned"] or [])})
    prompt = (
        f"Decompose this insight into atomic factual claims and check each against the evidence pack. "
        f"Also rate actionability (does the opportunity name a surface, a mechanism, and a measurable "
        f"outcome? 0-4) and novelty (4 = a Blinkit PM would NOT already know this without research; "
        f"0 = obvious).\n\nSTATEMENT: {draft.statement}\nSO WHAT: {draft.so_what}\nOPPORTUNITY: {draft.opportunity}\n\n"
        f"EVIDENCE:\n" + "\n---\n".join(t[:300] for t in texts[:20]) + "\n\n"
        'Respond with strict JSON: {"claims": [{"claim": string, "supported": bool}], '
        '"actionability_score": int, "novelty_score": int, "actionability_rationale": string, "novelty_rationale": string}'
    )
    result = client.complete_json(
        prompt=prompt, response_model=IQSVerification, prompt_version=VERIFY_PROMPT_VERSION,
        model=get_settings().aisle_synth_model, stage="insight_verify",
        mock_response_factory=lambda: mock_module.mock_verify(draft.statement, draft.so_what, draft.opportunity, texts, distinct_codes),
    )
    return result.parsed


def generate_insight_for_theme(theme_id: int, run_id: int, client: LLMClient) -> dict | None:
    with get_conn() as conn:
        theme_row = conn.execute("SELECT * FROM themes WHERE id = %s", (theme_id,)).fetchone()
    if theme_row is None or theme_row["doc_count"] < MIN_DOC_COUNT_FOR_INSIGHT:
        return None
    theme = dict(theme_row)
    theme["source_spread"] = theme["source_spread_json"]

    evidence_pack = assemble_evidence_pack(theme_id)
    draft, segment_stats = draft_insight(theme, evidence_pack, client)
    critique = run_adversarial_pass(evidence_pack, client)
    verification = run_verification(draft, evidence_pack, client)

    matched_prior_run = theme["status"] in ("stable", "growing", "decaying")
    iqs = compute_iqs(
        claims=[c.model_dump() for c in verification.claims],
        doc_count=theme["doc_count"], doc_total=theme["doc_total"],
        ci_low=theme["ci_low"], ci_high=theme["ci_high"],
        source_counts=theme["source_spread"].get("sources", {}),
        matched_prior_run=matched_prior_run,
        actionability_rubric=verification.actionability_score, novelty_rubric=verification.novelty_score,
    )

    with get_conn() as conn:
        insight_row = conn.execute(
            """
            INSERT INTO insights (run_id, theme_ids, title, statement, so_what, opportunity,
                                   affected_segments, affected_categories, prevalence, ci_low, ci_high,
                                   counter_evidence, iqs_total, iqs_breakdown_json, grade, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'auto')
            RETURNING id
            """,
            (
                run_id, [theme_id], draft.title, draft.statement, draft.so_what, draft.opportunity,
                draft.affected_segments, draft.affected_categories,
                theme["prevalence"], theme["ci_low"], theme["ci_high"],
                critique.counter_evidence, iqs["total"], json.dumps(iqs["breakdown"]), iqs["grade"],
            ),
        ).fetchone()
        insight_id = insight_row["id"]

        for e in evidence_pack[:10]:
            quote = e["raw_text"][:280]
            conn.execute(
                """
                INSERT INTO insight_evidence (insight_id, document_id, quote, supports)
                VALUES (%s, %s, %s, 'direct')
                """,
                (insight_id, e["document_id"], quote),
            )
        conn.commit()

    return {
        "insight_id": insight_id, "theme_id": theme_id, "title": draft.title, "grade": iqs["grade"],
        "iqs_total": iqs["total"], "iqs_breakdown": iqs["breakdown"], "confident": draft.confident,
        "undermines_insight": critique.undermines_insight, "segment_stats": segment_stats,
    }


def generate_insights_for_run(run_id: int, *, max_cost_usd: float | None = None) -> dict:
    from aisle.llm.cost import CostTracker

    with get_conn() as conn:
        theme_ids = [r["id"] for r in conn.execute("SELECT id FROM themes WHERE run_id = %s", (run_id,)).fetchall()]

    client = LLMClient(cost_tracker=CostTracker(max_cost_usd=max_cost_usd or get_settings().aisle_max_cost_usd))
    results = []
    skipped = 0
    for theme_id in theme_ids:
        result = generate_insight_for_theme(theme_id, run_id, client)
        if result is None:
            skipped += 1
        else:
            results.append(result)

    grade_counts: dict[str, int] = {}
    for r in results:
        grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1

    return {
        "run_id": run_id, "themes_considered": len(theme_ids), "insights_generated": len(results),
        "skipped_too_small": skipped, "grade_counts": grade_counts, "cost_usd": round(client.cost_tracker.cost_usd, 4),
        "insights": results,
    }
