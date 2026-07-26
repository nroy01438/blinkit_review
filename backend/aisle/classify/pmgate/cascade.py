"""The five-stage PM-Gate cascade (§6), run per document. Cheap stages run
first so junk dies before any expensive model call. `schema_version` is
bumped whenever a prompt version changes in a way that should force
reclassification of already-classified documents (see §12's cache-by-
content_hash-+-prompt_version rule).
"""
from __future__ import annotations

import json

from aisle.classify.pmgate import stage1_junk, stage2_utility, stage3_relevance, stage4_extraction
from aisle.classify.pmgate.stage0_normalise import normalise
from aisle.classify.pmgate.stage5_confidence import near_threshold, self_consistency_majority, should_abstain_on_confidence
from aisle.classify.schemas import ExtractionResult
from aisle.db.connection import get_conn
from aisle.llm.client import LLMClient
from aisle.llm.cost import CostTracker
from aisle.settings import get_settings, scoring_config

SCHEMA_VERSION = "pmgate.v1"


def classify_document(document_id: int, raw_text: str, client: LLMClient) -> dict:
    """Runs the full cascade for one document and writes a `classifications`
    row. Returns the row's field dict (for logging/aggregation by the caller)
    plus a `_meta` key with cost/cache bookkeeping, never persisted verbatim.
    """
    normalised = normalise(raw_text)
    text = normalised.clean_text
    row: dict = {
        "document_id": document_id,
        "schema_version": SCHEMA_VERSION,
        "stage_reached": 0,
        "model_used": get_settings().aisle_bulk_model,
        "prompt_version": stage1_junk.PROMPT_VERSION,
        "abstained": False,
    }
    total_cost = 0.0

    junk_verdict, junk_meta = stage1_junk.run_junk_gate(text, client, document_id=document_id)
    total_cost += junk_meta.get("cost_usd", 0.0)
    row["stage_reached"] = 1
    row["is_junk"] = junk_verdict.is_junk
    row["junk_reason"] = junk_verdict.junk_reason
    row["confidence"] = junk_verdict.confidence

    if junk_verdict.is_junk:
        _persist(row)
        return {**row, "_meta": {"cost_usd": total_cost}}

    utility_scores, pm_score, pm_verdict, utility_meta = stage2_utility.run_pm_utility(text, client, document_id=document_id)
    total_cost += utility_meta.get("cost_usd", 0.0)
    row["stage_reached"] = 2
    row["prompt_version"] = stage2_utility.PROMPT_VERSION
    if utility_scores is not None:
        row.update(
            specificity=utility_scores.specificity,
            actionability=utility_scores.actionability,
            evidence_strength=utility_scores.evidence_strength,
            emotional_intensity=utility_scores.emotional_intensity,
            pm_utility_score=pm_score,
            pm_verdict=pm_verdict,
        )
        utility_confidence = utility_scores.confidence
    else:
        utility_confidence = 0.0
        row["abstained"] = True

    thresholds_cfg = scoring_config()["pm_utility"]["thresholds"]
    if utility_scores is not None and near_threshold(pm_score, [thresholds_cfg["high_signal"], thresholds_cfg["medium"]]):
        samples = [pm_score]
        for _ in range(2):
            _, resampled_score, _, _ = stage2_utility.run_pm_utility(text, client, document_id=document_id)
            if resampled_score:
                samples.append(resampled_score)
        majority, disagreement = self_consistency_majority(samples)
        if disagreement:
            row["abstained"] = True

    relevance_verdict, relevance_meta = stage3_relevance.run_relevance(text, client, document_id=document_id)
    total_cost += relevance_meta.get("cost_usd", 0.0)
    row["stage_reached"] = 3
    if relevance_verdict is not None:
        row["discovery_relevance"] = relevance_verdict.discovery_relevance
        row["relevance_verdict"] = "relevant" if relevance_verdict.discovery_relevance >= stage3_relevance.relevance_floor() else "not_relevant"
        relevance_confidence = relevance_verdict.confidence
    else:
        relevance_confidence = 0.0
        row["abstained"] = True

    extraction: ExtractionResult | None = None
    if relevance_verdict is not None and relevance_verdict.discovery_relevance >= stage3_relevance.relevance_floor():
        extraction, extraction_meta = stage4_extraction.run_extraction(text, client, document_id=document_id)
        total_cost += extraction_meta.get("cost_usd", 0.0)
        row["stage_reached"] = 4
        if extraction is not None:
            row.update(
                categories_mentioned=extraction.categories_mentioned,
                behaviour_codes=extraction.behaviour_codes,
                barrier_codes=extraction.barrier_codes,
                jtbd_statement=extraction.jtbd_statement,
                unmet_need=extraction.unmet_need,
                segment_label=extraction.segment_label,
                lifecycle_stage=extraction.lifecycle_stage,
                sentiment=extraction.sentiment,
                severity=extraction.severity,
                supporting_span=extraction.supporting_span,
            )
            extraction_confidence = extraction.confidence
        else:
            extraction_confidence = 0.0
            row["abstained"] = True
    else:
        extraction_confidence = None

    confidences = [c for c in (utility_confidence, relevance_confidence, extraction_confidence) if c is not None]
    row["confidence"] = min(confidences) if confidences else 0.0
    row["stage_reached"] = 5

    if should_abstain_on_confidence(row["confidence"]):
        row["abstained"] = True

    _persist(row)
    return {**row, "_meta": {"cost_usd": total_cost}}


def _persist(row: dict) -> None:
    columns = [
        "document_id", "schema_version", "stage_reached", "is_junk", "junk_reason",
        "specificity", "actionability", "evidence_strength", "emotional_intensity",
        "pm_utility_score", "pm_verdict", "discovery_relevance", "relevance_verdict",
        "categories_mentioned", "behaviour_codes", "barrier_codes", "jtbd_statement",
        "unmet_need", "segment_label", "lifecycle_stage", "sentiment", "severity",
        "supporting_span", "confidence", "abstained", "model_used", "prompt_version",
    ]
    array_columns = {"categories_mentioned", "behaviour_codes", "barrier_codes"}
    values = [(row.get(c) if row.get(c) is not None else ([] if c in array_columns else None)) for c in columns]
    placeholders = ", ".join(["%s"] * len(columns))
    col_list = ", ".join(columns)
    with get_conn() as conn:
        conn.execute(
            f"""
            INSERT INTO classifications ({col_list})
            VALUES ({placeholders})
            ON CONFLICT (document_id, schema_version) DO UPDATE SET
                stage_reached = EXCLUDED.stage_reached,
                is_junk = EXCLUDED.is_junk,
                junk_reason = EXCLUDED.junk_reason,
                pm_utility_score = EXCLUDED.pm_utility_score,
                discovery_relevance = EXCLUDED.discovery_relevance,
                confidence = EXCLUDED.confidence,
                abstained = EXCLUDED.abstained
            """,
            values,
        )
        conn.commit()
