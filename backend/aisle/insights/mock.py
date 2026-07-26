"""Deterministic MOCK_LLM generators for insight drafting, the adversarial
counter-evidence pass, and IQS verification. Like `aisle/classify/pmgate/mock.py`,
these read only the text/stats actually available to a real LLM call — never
`meta_json.negative_control` or any other ground-truth flag — so the §9
negative-control experiment stays a real test of the pipeline, not a test
the mock is rigged to pass.
"""
from __future__ import annotations

import re

from aisle.ingest.dedupe import jaccard_similarity, shingles

OBVIOUS_PHRASES = re.compile(r"users? (like|want|prefer) (fast|good|nice|quick)", re.IGNORECASE)


def mock_draft(*, theme_label: str, theme_description: str, doc_count: int, doc_total: int,
               prevalence: float, ci_low: float, ci_high: float, evidence_snippets: list[str],
               segment_stats: list[dict], categories: list[str]) -> dict:
    title = theme_label[:80] if theme_label else "Untitled theme"
    statement = (
        f"{theme_description} This pattern appears in {doc_count} of {doc_total} discovery-relevant "
        f"documents ({prevalence:.1%}, 95% CI [{ci_low:.1%}, {ci_high:.1%}])."
    )
    so_what = (
        "If this holds, it directly bears on why users don't explore beyond their usual basket — "
        "worth scoping a product change rather than treating it as anecdotal."
    )
    seg_names = [s["segment_label"] for s in segment_stats if s.get("rate", 0) > 0][:3]
    opportunity = (
        f"If we surface clearer {categories[0] if categories else 'category'}-level information at the "
        f"point users hesitate, then discovery attempts from affected segments should rise, "
        f"measured by a lift in category-page-to-cart conversion for new-to-user categories over 4 weeks."
    )
    confident = doc_count >= 15 and (ci_high - ci_low) < 0.25
    return {
        "title": title,
        "statement": statement,
        "so_what": so_what,
        "opportunity": opportunity,
        "affected_segments": seg_names,
        "affected_categories": categories[:5],
        "confident": confident,
    }


def mock_adversarial(evidence_texts: list[str], source_names: list[str]) -> dict:
    """No access to the draft's reasoning — only the raw evidence, exactly
    per §8's adversarial-pass isolation requirement.
    """
    if len(evidence_texts) < 2:
        return {
            "counter_evidence": f"No counter-evidence found in n={len(evidence_texts)} searched — too few documents to assess sampling risk.",
            "undermines_insight": False,
        }

    pairs = 0
    total_sim = 0.0
    sample = evidence_texts[:15]
    for i in range(len(sample)):
        for j in range(i + 1, len(sample)):
            total_sim += jaccard_similarity(shingles(sample[i]), shingles(sample[j]))
            pairs += 1
    avg_sim = total_sim / pairs if pairs else 0.0

    n_distinct_sources = len(set(source_names))

    flags = []
    if avg_sim > 0.35:
        flags.append(
            f"the {len(sample)} evidence documents sampled are unusually lexically similar to each other "
            f"(avg pairwise trigram-Jaccard {avg_sim:.2f}) — consistent with a templated complaint format or "
            f"coordinated posting rather than independently-written accounts; treat corroboration as weaker "
            f"than the raw document count suggests"
        )
    if n_distinct_sources <= 1:
        flags.append(f"every document comes from a single source ({source_names[0] if source_names else 'unknown'}) — this could be a platform-specific artifact, not a general finding")

    if flags:
        return {"counter_evidence": "Strongest case against this insight: " + "; and ".join(flags) + ".", "undermines_insight": True}
    return {
        "counter_evidence": f"No strong counter-evidence found in n={len(evidence_texts)} searched (evidence is lexically varied and spans {n_distinct_sources} source(s)).",
        "undermines_insight": False,
    }


def mock_verify(statement: str, so_what: str, opportunity: str, evidence_texts: list[str], distinct_codes: int) -> dict:
    claim_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", f"{statement} {so_what}") if len(s.strip()) > 8]
    evidence_tokens = [set(t.lower() for t in re.findall(r"[a-z]{3,}", text)) for text in evidence_texts]

    claims = []
    for sentence in claim_sentences:
        sentence_tokens = set(t.lower() for t in re.findall(r"[a-z]{3,}", sentence))
        supported = any(len(sentence_tokens & ev) >= 3 for ev in evidence_tokens) if evidence_tokens else False
        claims.append({"claim": sentence, "supported": supported})

    has_surface = bool(re.search(r"page|banner|search|listing|checkout|home feed|category", opportunity, re.IGNORECASE))
    has_mechanism = "if we" in opportunity.lower()
    has_outcome = bool(re.search(r"measured by|lift|conversion|rate|%", opportunity, re.IGNORECASE))
    actionability_score = sum([has_surface, has_mechanism, has_outcome]) + (1 if "then" in opportunity.lower() else 0)

    is_obvious = bool(OBVIOUS_PHRASES.search(statement) or OBVIOUS_PHRASES.search(so_what))
    novelty_score = 0 if is_obvious else min(4, 1 + distinct_codes)

    return {
        "claims": claims,
        "actionability_score": min(4, actionability_score),
        "novelty_score": novelty_score,
        "actionability_rationale": f"surface={has_surface}, mechanism={has_mechanism}, measurable_outcome={has_outcome}",
        "novelty_rationale": "obvious/generic phrasing detected" if is_obvious else f"references {distinct_codes} distinct behaviour/barrier code(s)",
    }
