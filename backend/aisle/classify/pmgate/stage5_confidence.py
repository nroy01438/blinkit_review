"""Stage 5 — Confidence & Abstention. `confidence < 0.6` abstains outright.
For scores within `threshold_margin` of a verdict boundary, self-consistency
resamples 3x at temperature 0.3 and takes the majority; disagreement
abstains. NOTE: in MOCK_LLM mode the mock generators are deterministic
functions of the text, so 3 resamples are always identical — the
self-consistency *code path* is exercised but can never itself produce a
disagreement-abstention until run against a real, sampling LLM.
"""
from __future__ import annotations

from aisle.settings import scoring_config


def should_abstain_on_confidence(confidence: float) -> bool:
    return confidence < scoring_config()["confidence"]["abstain_below"]


def near_threshold(score: int, thresholds: list[int]) -> bool:
    margin = scoring_config()["confidence"]["self_consistency"]["threshold_margin"]
    return any(abs(score - t) <= margin for t in thresholds)


def self_consistency_majority(samples: list[int]) -> tuple[int | None, bool]:
    """Returns (majority_value, disagreement). Disagreement is True when no
    value has a strict majority among the samples.
    """
    if not samples:
        return None, True
    counts: dict[int, int] = {}
    for s in samples:
        counts[s] = counts.get(s, 0) + 1
    best_value, best_count = max(counts.items(), key=lambda kv: kv[1])
    disagreement = best_count <= len(samples) / 2
    return best_value, disagreement
