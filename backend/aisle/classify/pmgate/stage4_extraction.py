"""Stage 4 — Structured Extraction, run only on discovery_relevance >= floor.
Two hard anti-hallucination mechanics, both non-negotiable:

1. `supporting_span` must be a verbatim substring of the source text —
   verified programmatically; a non-verbatim span rejects the whole
   extraction rather than being silently kept.
2. `behaviour_codes`/`barrier_codes` are filtered against the controlled
   vocabulary in taxonomy/codes.yaml. Anything outside it is dropped from
   the aggregation-facing columns and logged as a *proposed* code for human
   review in /admin — free-text codes make aggregation meaningless (§6).
"""
from __future__ import annotations

from aisle.classify.pmgate import mock as mock_module
from aisle.classify.schemas import ExtractionResult
from aisle.llm.client import LLMClient
from aisle.settings import codes_taxonomy, get_settings

PROMPT_VERSION = "extraction.v1"

PROMPT_TEMPLATE = """Extract structured fields from this Blinkit user-feedback text about category \
discovery/habits/barriers. `supporting_span` MUST be an exact, verbatim substring copied from the \
text below — do not paraphrase it.

Text: {text}

Respond with strict JSON matching:
{{"categories_mentioned": [string], "behaviour_codes": [string], "barrier_codes": [string], \
"jtbd_statement": string|null, "unmet_need": string|null, "segment_label": string|null, \
"lifecycle_stage": string|null, "sentiment": string|null, "severity": int(1-5), "confidence": float, \
"supporting_span": string}}"""


class SpanNotVerbatimError(ValueError):
    pass


def filter_controlled_vocab(codes: list[str], vocab: list[str]) -> tuple[list[str], list[str]]:
    kept = [c for c in codes if c in vocab]
    proposed = [c for c in codes if c not in vocab]
    return kept, proposed


def run_extraction(text: str, client: LLMClient, *, document_id: int) -> tuple[ExtractionResult | None, dict]:
    settings = get_settings()
    result = client.complete_json(
        prompt=PROMPT_TEMPLATE.format(text=text),
        response_model=ExtractionResult,
        prompt_version=PROMPT_VERSION,
        model=settings.aisle_bulk_model,
        document_id=document_id,
        stage="stage4_extraction",
        mock_response_factory=lambda: mock_module.mock_extraction(text),
    )
    meta = {"cached": result.cached, "cost_usd": result.cost_usd, "needs_human_review": False, "proposed_codes": []}

    if result.parsed is None:
        meta["needs_human_review"] = True
        return None, meta

    extraction = result.parsed
    if extraction.supporting_span not in text:
        meta["needs_human_review"] = True
        meta["rejection_reason"] = "supporting_span is not a verbatim substring of the source text"
        return None, meta

    taxonomy = codes_taxonomy()
    behaviour_kept, behaviour_proposed = filter_controlled_vocab(extraction.behaviour_codes, taxonomy["behaviour_codes"])
    barrier_kept, barrier_proposed = filter_controlled_vocab(extraction.barrier_codes, taxonomy["barrier_codes"])
    extraction.behaviour_codes = behaviour_kept
    extraction.barrier_codes = barrier_kept
    meta["proposed_codes"] = behaviour_proposed + barrier_proposed

    if extraction.segment_label and extraction.segment_label not in taxonomy["segments"]:
        meta["proposed_codes"].append(f"segment:{extraction.segment_label}")
        extraction.segment_label = None

    return extraction, meta
