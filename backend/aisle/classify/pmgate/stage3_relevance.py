"""Stage 3 — Discovery Relevance. Deliberately independent of Stage 2's
utility score — a document can be high-utility and zero-relevance (a
precise, actionable delivery-time complaint) and stays in the corpus for
the ops bucket, just excluded from discovery denominators. Collapsing this
axis into "useful" is exactly what shrank the prior engine's corpus from
5,000 to 166 (§6) — keeping them orthogonal is the fix.
"""
from __future__ import annotations

from aisle.classify.pmgate import mock as mock_module
from aisle.classify.schemas import RelevanceVerdict
from aisle.llm.client import LLMClient
from aisle.settings import get_settings, scoring_config

PROMPT_VERSION = "discovery_relevance.v1"

PROMPT_TEMPLATE = """Does this Blinkit user-feedback text say anything about category discovery, \
exploration, browsing, habit/repeat-purchase behaviour, trying something new, or reasons for NOT \
trying something new? Score 0-4: 0=nothing on this topic, 4=directly and specifically about it. \
This is independent of whether the text is otherwise useful — a precise delivery complaint scores 0 here.

Text: {text}

Respond with strict JSON: {{"discovery_relevance": int, "rationale": string, "confidence": float}}"""


def run_relevance(text: str, client: LLMClient, *, document_id: int) -> tuple[RelevanceVerdict | None, dict]:
    settings = get_settings()
    result = client.complete_json(
        prompt=PROMPT_TEMPLATE.format(text=text),
        response_model=RelevanceVerdict,
        prompt_version=PROMPT_VERSION,
        model=settings.aisle_bulk_model,
        document_id=document_id,
        stage="stage3_relevance",
        mock_response_factory=lambda: mock_module.mock_relevance_verdict(text),
    )
    meta = {"cached": result.cached, "cost_usd": result.cost_usd, "needs_human_review": result.parsed is None}
    return result.parsed, meta


def relevance_floor() -> int:
    return scoring_config()["discovery_relevance"]["relevant_floor"]
