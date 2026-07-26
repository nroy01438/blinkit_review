"""Deterministic MOCK_LLM response generators for every PM-Gate stage.

These are NOT randomly canned — they read the actual document text (regex/
keyword heuristics) to decide what a plausible model response would look
like, the same way the sibling Frontier app's MOCK_LLM returns "canned but
realistic text" instead of calling Claude. The one exception worth being
explicit about: `meta.bucket_hint`, written by the synthetic-corpus
generator, is used as a *hint* to pick which heuristic branch applies (junk
vs ops vs discovery-signal) — a real LLM would infer the same branch from
the text itself, since the synthetic templates were written to be
unambiguous in exactly the same way. Nothing here reads `negative_control`
or any other "answer key" field — the negative-control experiment (§9,
Phase 5) only works as a real test if this mock cannot see that flag.
"""
from __future__ import annotations

import re

PROMO_RE = re.compile(r"referral code|% ?off|hiring|apply now", re.IGNORECASE)
PURE_RATING_RE = re.compile(r"^(good|nice|nice app|bad|worst|meh|superb( superb)*)\W*$", re.IGNORECASE)
REPEATED_WORD_RE = re.compile(r"\b(\w+)\b(\s+\1\b){2,}", re.IGNORECASE)
OPS_KEYWORDS = re.compile(r"crash|deliver(y|ed)|refund|payment fail|logged? me out|reinstall", re.IGNORECASE)
DISCOVERY_KEYWORDS = re.compile(
    r"reorder|usual|browse|search|new category|new brand|try(ing)? (a |new )|compare|freshness|expiry|"
    r"return policy|origin|explore|basket|habit", re.IGNORECASE
)

CATEGORY_WORDS = [
    "fresh produce", "dairy", "personal care", "packaged snacks", "baby care", "pet supplies",
    "home cleaning", "electronics accessories", "stationery", "meat and seafood", "bakery",
    "beverages", "frozen food", "ayurveda wellness",
]


def mock_junk_verdict(text: str) -> dict:
    stripped = text.strip()
    if len(stripped) < 15 and not re.search(r"[.!?]", stripped):
        return {"is_junk": True, "junk_reason": "too_short_no_rating_context"}
    if PROMO_RE.search(stripped):
        reason = "job_seeking_spam" if re.search(r"hiring|apply now", stripped, re.IGNORECASE) else "promo_spam"
        return {"is_junk": True, "junk_reason": reason}
    if PURE_RATING_RE.match(stripped) or re.fullmatch(r"[\W\s]{1,10}", stripped):
        return {"is_junk": True, "junk_reason": "pure_rating_text"}
    if REPEATED_WORD_RE.search(stripped):
        return {"is_junk": True, "junk_reason": "bot_repetition"}
    if OPS_KEYWORDS.search(stripped) and not DISCOVERY_KEYWORDS.search(stripped):
        return {"is_junk": True, "junk_reason": "ops_off_topic"}
    return {"is_junk": False, "junk_reason": None}


def _keyword_density_score(text: str, pattern: re.Pattern, cap: int = 4) -> int:
    hits = len(pattern.findall(text))
    return min(cap, hits)


def mock_utility_scores(text: str) -> dict:
    specificity = 1
    if re.search(r"\d", text) or len(text.split()) > 25:
        specificity += 1
    if DISCOVERY_KEYWORDS.search(text):
        specificity += 1
    if any(cat in text.lower() for cat in CATEGORY_WORDS):
        specificity += 1
    specificity = min(4, specificity)

    actionability = min(4, 1 + _keyword_density_score(text, re.compile(r"search|browse|reorder|compare|return policy|expiry|origin", re.IGNORECASE)))
    evidence_strength = min(4, 1 + _keyword_density_score(text, re.compile(r"every week|always|usual|third time|again|once more|compared to", re.IGNORECASE)))
    emotional_intensity = min(4, _keyword_density_score(text, re.compile(r"never|honestly|wish|overwhelmed|worst|love|hate", re.IGNORECASE)) + (1 if "!" in text else 0))

    return {
        "specificity": specificity,
        "actionability": actionability,
        "evidence_strength": evidence_strength,
        "emotional_intensity": emotional_intensity,
        "confidence": 0.85 if specificity >= 2 else 0.55,
    }


def mock_relevance_verdict(text: str) -> dict:
    hits = len(DISCOVERY_KEYWORDS.findall(text))
    if hits == 0:
        return {"discovery_relevance": 0, "rationale": "no discovery/exploration/habit language found", "confidence": 0.8}
    score = min(4, 1 + hits)
    return {
        "discovery_relevance": score,
        "rationale": f"found {hits} discovery/habit/exploration keyword(s)",
        "confidence": 0.75 if hits >= 2 else 0.55,
    }


def _find_supporting_span(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for s in sentences:
        if DISCOVERY_KEYWORDS.search(s):
            return s.strip()[:280]
    return text.strip()[:200]


def mock_extraction(text: str) -> dict:
    lower = text.lower()
    categories = [c.replace(" ", "_") for c in CATEGORY_WORDS if c in lower]

    behaviour_codes = []
    if re.search(r"reorder|usual list|saved list", lower):
        behaviour_codes.append("reorders_from_saved_list")
    if re.search(r"search(ed)? .*never (browse|open)|search.*seedha", lower):
        behaviour_codes.append("searches_never_browses")
    if re.search(r"compare", lower):
        behaviour_codes.append("compares_across_apps_before_buying")

    barrier_codes = []
    if re.search(r"freshness|fresh nahi", lower):
        barrier_codes.append("cannot_assess_freshness")
    if re.search(r"return policy", lower):
        barrier_codes.append("unclear_return_policy")
    if re.search(r"price|cheaper|compare.*price", lower):
        barrier_codes.append("no_price_comparison")
    if re.search(r"trust|risk", lower):
        barrier_codes.append("trust_deficit_new_category")
    if re.search(r"origin|expiry|authenticity|size", lower):
        barrier_codes.append("insufficient_product_info")

    segment_label = "explorer" if re.search(r"love trying|browse.*most weekends|experiment", lower) else (
        "new_user" if re.search(r"new user|overwhelmed|first time", lower) else "habitual_replenisher"
    )
    sentiment = "negative" if re.search(r"never|worst|wish|overwhelmed|risk", lower) else (
        "positive" if re.search(r"love|great|amazing", lower) else "neutral"
    )
    severity = 4 if sentiment == "negative" and len(barrier_codes) >= 2 else (2 if sentiment == "positive" else 3)

    return {
        "categories_mentioned": categories[:3],
        "behaviour_codes": behaviour_codes,
        "barrier_codes": barrier_codes,
        "jtbd_statement": "When I need groceries fast, I want to reorder my usual basket without thinking, so I can get on with my day."
        if "habitual_replenisher" == segment_label else None,
        "unmet_need": "Wants confidence about a new category before committing to it" if barrier_codes else None,
        "segment_label": segment_label,
        "lifecycle_stage": "new_user" if segment_label == "new_user" else "established_user",
        "sentiment": sentiment,
        "severity": severity,
        "confidence": 0.8 if (behaviour_codes or barrier_codes) else 0.5,
        "supporting_span": _find_supporting_span(text),
    }
