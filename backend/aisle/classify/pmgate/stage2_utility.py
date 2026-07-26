"""Stage 2 — PM Utility Scoring. Weights and verdict thresholds live in
config/scoring.yaml (never hardcoded), so they can be tuned against the
golden set without a code change. Specificity/actionability/evidence are
scored independently of emotional_intensity by design — the anti-pattern
this guards against is an angry-but-vague review outranking a calm,
precise one.
"""
from __future__ import annotations

from aisle.classify.pmgate import mock as mock_module
from aisle.classify.schemas import PMUtilityScores
from aisle.llm.client import LLMClient
from aisle.settings import get_settings, scoring_config

PROMPT_VERSION = "pm_utility.v1"

PROMPT_TEMPLATE = """Score this Blinkit user-feedback text on four 0-4 dimensions, using these anchors:

specificity: 0="it's bad" (no detail) ... 4="the pomegranates I ordered Tuesday were split and dry, \
third time this month" (concrete, dated, repeated).
actionability: 0=pure emotion, no scopeable problem ... 4=names the exact surface/moment where the \
experience broke.
evidence_strength: 0=bare assertion ... 4=repeated behaviour, comparison to an alternative, or a \
described workaround.
emotional_intensity: signal of severity, NOT of usefulness — score this independently; a calm precise \
review can score low here and still score high on the other three.

Text: {text}

Respond with strict JSON: {{"specificity": int, "actionability": int, "evidence_strength": int, \
"emotional_intensity": int, "confidence": float}}"""


def compute_pm_utility_score(scores: PMUtilityScores) -> int:
    weights = scoring_config()["pm_utility"]["weights"]
    raw = (
        weights["specificity"] * scores.specificity
        + weights["actionability"] * scores.actionability
        + weights["evidence_strength"] * scores.evidence_strength
        + weights["emotional_intensity"] * scores.emotional_intensity
    )
    return round(100 * raw / 4)


def verdict_for_score(score: int) -> str:
    thresholds = scoring_config()["pm_utility"]["thresholds"]
    if score >= thresholds["high_signal"]:
        return "high_signal"
    if score >= thresholds["medium"]:
        return "medium"
    return "low"


def run_pm_utility(text: str, client: LLMClient, *, document_id: int) -> tuple[PMUtilityScores | None, int, str, dict]:
    settings = get_settings()
    result = client.complete_json(
        prompt=PROMPT_TEMPLATE.format(text=text),
        response_model=PMUtilityScores,
        prompt_version=PROMPT_VERSION,
        model=settings.aisle_bulk_model,
        document_id=document_id,
        stage="stage2_pm_utility",
        mock_response_factory=lambda: mock_module.mock_utility_scores(text),
    )
    if result.parsed is None:
        return None, 0, "low", {"cached": result.cached, "cost_usd": result.cost_usd, "needs_human_review": True}
    score = compute_pm_utility_score(result.parsed)
    verdict = verdict_for_score(score)
    return result.parsed, score, verdict, {"cached": result.cached, "cost_usd": result.cost_usd, "needs_human_review": False}
