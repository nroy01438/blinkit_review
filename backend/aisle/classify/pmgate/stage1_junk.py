"""Stage 1 — Junk Gate. Heuristics first (cheap, catch ~90% of junk before
any LLM call); anything heuristics can't confidently resolve falls through
to a cheap LLM call. Every kill reason is returned so the caller can log
counts — this table is the data-cleansing story shown in the demo.
"""
from __future__ import annotations

from aisle.classify.pmgate import mock as mock_module
from aisle.classify.schemas import JunkVerdict
from aisle.llm.client import LLMClient
from aisle.settings import get_settings

PROMPT_VERSION = "junk_gate.v1"

PROMPT_TEMPLATE = """You are a data-cleansing classifier for Blinkit (Indian quick-commerce) user \
feedback. Decide whether the text below is JUNK — meaning it carries no usable product-management \
signal (empty/too short, pure star-rating text with no content, promo/referral spam, delivery-partner \
job-seeking posts, obvious bot/repetition text) OR is purely an off-topic operational complaint with \
zero discovery/exploration signal (app crashes, delivery timing, payment failures) — mark those \
is_junk=true with junk_reason="ops_off_topic" (they are kept, just excluded from discovery analysis). \
Otherwise is_junk=false.

Text: {text}

Respond with strict JSON: {{"is_junk": bool, "junk_reason": string|null}}"""


def run_junk_gate(text: str, client: LLMClient, *, document_id: int) -> tuple[JunkVerdict, dict]:
    heuristic = mock_module.mock_junk_verdict(text)
    if heuristic["is_junk"]:
        # heuristics only ever assert a *positive* junk call with high precision;
        # a heuristic "not junk" is not trusted alone and always goes to the LLM.
        return JunkVerdict.model_validate(heuristic), {"cached": False, "cost_usd": 0.0, "heuristic_only": True}

    settings = get_settings()
    result = client.complete_json(
        prompt=PROMPT_TEMPLATE.format(text=text),
        response_model=JunkVerdict,
        prompt_version=PROMPT_VERSION,
        model=settings.aisle_bulk_model,
        document_id=document_id,
        stage="stage1_junk",
        mock_response_factory=lambda: mock_module.mock_junk_verdict(text),
    )
    if result.parsed is None:
        # validation failed twice — do not silently coerce; treat as needing review
        return JunkVerdict(is_junk=False, junk_reason=None), {
            "cached": result.cached, "cost_usd": result.cost_usd, "needs_human_review": True,
        }
    return result.parsed, {"cached": result.cached, "cost_usd": result.cost_usd, "needs_human_review": False}
