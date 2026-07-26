"""Insight Quality Score (§9) — the single biggest differentiator over the
benchmark. Every weight below is read from config/scoring.yaml, never
hardcoded, and every component is computed from data actually available to
the pipeline (never from a ground-truth flag) so the score means what it
claims to mean.
"""
from __future__ import annotations

import math

import numpy as np

from aisle.db.connection import get_conn
from aisle.settings import scoring_config

BOOTSTRAP_RESAMPLES = 200


def groundedness_score(claims: list[dict], weight: float) -> tuple[float, bool]:
    if not claims:
        return 0.0, False
    supported = sum(1 for c in claims if c["supported"])
    any_unsupported = supported < len(claims)
    return weight * (supported / len(claims)), any_unsupported


def evidence_volume_score(doc_count: int, doc_total: int, weight: float) -> float:
    if doc_total <= 0 or doc_count <= 0:
        return 0.0
    ratio = math.log(1 + doc_count) / math.log(1 + doc_total)
    return weight * min(1.0, ratio)


def statistical_precision_score(ci_low: float, ci_high: float, weight: float) -> float:
    width = ci_high - ci_low
    return weight * max(0.0, 1 - min(1.0, width / 0.5))


def source_triangulation_score(source_counts: dict[str, int], n_sources_in_corpus: int, weight: float) -> float:
    total = sum(source_counts.values())
    if total == 0 or len(source_counts) <= 1:
        return 0.0
    probs = [c / total for c in source_counts.values() if c > 0]
    entropy = -sum(p * math.log(p) for p in probs)
    max_entropy = math.log(max(2, n_sources_in_corpus))
    return weight * min(1.0, entropy / max_entropy)


def bootstrap_prevalence_excludes_zero(doc_count: int, doc_total: int, resamples: int = BOOTSTRAP_RESAMPLES) -> bool:
    if doc_total == 0:
        return False
    rng = np.random.default_rng(20260726)
    population = np.zeros(doc_total, dtype=np.int8)
    population[:doc_count] = 1
    means = [rng.choice(population, size=doc_total, replace=True).mean() for _ in range(resamples)]
    ci_low = float(np.percentile(means, 2.5))
    return ci_low > 0.0


def temporal_stability_score(*, matched_prior_run: bool, doc_count: int, doc_total: int, weight: float) -> float:
    if matched_prior_run:
        return weight
    if bootstrap_prevalence_excludes_zero(doc_count, doc_total):
        return weight * 0.5
    return 0.0


def actionability_score(rubric_score_0_4: int, weight: float) -> float:
    return weight * (rubric_score_0_4 / 4)


def novelty_score(rubric_score_0_4: int, weight: float) -> float:
    return weight * (rubric_score_0_4 / 4)


def _n_sources_in_corpus() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT count(DISTINCT source_id) AS n FROM documents").fetchone()["n"] or 1


def compute_iqs(
    *, claims: list[dict], doc_count: int, doc_total: int, ci_low: float, ci_high: float,
    source_counts: dict[str, int], matched_prior_run: bool, actionability_rubric: int, novelty_rubric: int,
) -> dict:
    weights = scoring_config()["iqs"]["weights"]
    n_sources = _n_sources_in_corpus()

    groundedness, any_unsupported = groundedness_score(claims, weights["groundedness"])
    breakdown = {
        "groundedness": round(groundedness, 2),
        "evidence_volume": round(evidence_volume_score(doc_count, doc_total, weights["evidence_volume"]), 2),
        "statistical_precision": round(statistical_precision_score(ci_low, ci_high, weights["statistical_precision"]), 2),
        "source_triangulation": round(source_triangulation_score(source_counts, n_sources, weights["source_triangulation"]), 2),
        "temporal_stability": round(
            temporal_stability_score(matched_prior_run=matched_prior_run, doc_count=doc_count, doc_total=doc_total, weight=weights["temporal_stability"]),
            2,
        ),
        "actionability": round(actionability_score(actionability_rubric, weights["actionability"]), 2),
        "novelty": round(novelty_score(novelty_rubric, weights["novelty"]), 2),
    }
    total = round(sum(breakdown.values()))
    grade = grade_for_score(total)
    if any_unsupported and grade in ("A", "B"):
        grade = "C"  # §9: any unsupported claim caps the grade at C, regardless of numeric total
        breakdown["_grade_capped_reason"] = "at least one atomic claim was not supported by the evidence pack"
    return {"breakdown": breakdown, "total": total, "grade": grade}


def grade_for_score(total: int) -> str:
    bands = scoring_config()["iqs"]["grade_bands"]
    if total >= bands["A"]:
        return "A"
    if total >= bands["B"]:
        return "B"
    if total >= bands["C"]:
        return "C"
    return "D"
