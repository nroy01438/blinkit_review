"""The eight mandated Discovery Question Packs (§10) — each a first-class
object with its own retrieval strategy and analysis method (not a generic
chat prompt). Config lives in config/question_packs.yaml; this module is
where each `method` name is actually implemented. Every pack returns the
same envelope: {answer_summary, n, ci, top_quotes, segment_breakdown,
chart_data, generated_at} so the frontend can render all eight uniformly.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from aisle.db.connection import get_conn
from aisle.insights.stats import two_proportion_z_test, wilson_ci
from aisle.settings import question_packs_config

RELEVANCE_FLOOR = 2

HABIT_LEXICON = re.compile(r"\balways\b|every week|same list|\busual\b|as usual|routine|every time", re.IGNORECASE)
EXPLORATION_LEXICON = re.compile(r"\btry(ing)?\b.*\bnew\b|\bexplore\b|\bexperiment\b|\bbrowse\b", re.IGNORECASE)
SURFACE_PATTERNS = {
    "search": re.compile(r"\bsearch(ed|ing)?\b", re.IGNORECASE),
    "home_feed": re.compile(r"home (feed|page|screen)", re.IGNORECASE),
    "banner": re.compile(r"\bbanner\b", re.IGNORECASE),
    "notification": re.compile(r"notification", re.IGNORECASE),
    "word_of_mouth": re.compile(r"friend|recommend(ed)?|word of mouth", re.IGNORECASE),
    "offline": re.compile(r"local store|offline|physical store", re.IGNORECASE),
}
INFO_GAP_PATTERNS = {
    "freshness": re.compile(r"freshness|fresh nahi", re.IGNORECASE),
    "size": re.compile(r"\bsize\b|exact size", re.IGNORECASE),
    "origin": re.compile(r"\borigin\b", re.IGNORECASE),
    "expiry": re.compile(r"expiry", re.IGNORECASE),
    "authenticity": re.compile(r"authentic", re.IGNORECASE),
    "fit": re.compile(r"\bfit\b", re.IGNORECASE),
    "return_policy": re.compile(r"return polic", re.IGNORECASE),
}


def _corpus() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id AS document_id, d.raw_text, d.rating, s.name AS source_name, s.brand,
                   c.segment_label, c.categories_mentioned, c.barrier_codes, c.behaviour_codes,
                   c.severity, c.is_junk, c.junk_reason, c.discovery_relevance
            FROM documents d JOIN classifications c ON c.document_id = d.id JOIN sources s ON s.id = d.source_id
            WHERE d.dupe_of_id IS NULL
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _top_quotes(docs: list[dict], n: int = 5) -> list[dict]:
    return [{"document_id": d["document_id"], "quote": d["raw_text"][:220], "source_name": d["source_name"]} for d in docs[:n]]


def _envelope(**kwargs) -> dict:
    return {"generated_at": datetime.now(timezone.utc).isoformat(), **kwargs}


def _relevant(raw_corpus: list[dict] | None) -> list[dict]:
    raw_corpus = raw_corpus if raw_corpus is not None else _corpus()
    return [d for d in raw_corpus if not d["is_junk"] and d["discovery_relevance"] >= RELEVANCE_FLOOR]


def q1_repeat_categories(raw_corpus: list[dict] | None = None) -> dict:
    corpus = _relevant(raw_corpus)
    replenishers = [d for d in corpus if d["segment_label"] == "habitual_replenisher"]
    code_counts: dict[str, int] = {}
    for d in replenishers:
        for code in d["behaviour_codes"] or []:
            code_counts[code] = code_counts.get(code, 0) + 1
    successes, n = len(replenishers), len(corpus)
    rate, ci_low, ci_high = wilson_ci(successes, n)
    jtbd_examples = list({d["raw_text"][:150] for d in replenishers})[:5]
    return _envelope(
        answer_summary=f"{successes} of {n} discovery-relevant documents show habitual-replenisher behaviour ({rate:.1%}).",
        n=n, successes=successes, rate=rate, ci_low=ci_low, ci_high=ci_high,
        top_quotes=_top_quotes(replenishers), chart_data=sorted(code_counts.items(), key=lambda kv: -kv[1]),
        segment_breakdown={"habitual_replenisher": successes, "other": n - successes},
        jtbd_examples=jtbd_examples,
    )


def q2_exploration_barriers(raw_corpus: list[dict] | None = None) -> dict:
    corpus = _relevant(raw_corpus)
    barrier_counts: dict[str, int] = {}
    barrier_docs: dict[str, list[dict]] = {}
    for d in corpus:
        for code in d["barrier_codes"] or []:
            barrier_counts[code] = barrier_counts.get(code, 0) + 1
            barrier_docs.setdefault(code, []).append(d)
    n = len(corpus)
    ranked = sorted(barrier_counts.items(), key=lambda kv: -kv[1])
    with_ci = [{"barrier_code": code, "n_matching": count, **dict(zip(("rate", "ci_low", "ci_high"), wilson_ci(count, n)))} for code, count in ranked]
    top_code = ranked[0][0] if ranked else None
    return _envelope(
        answer_summary=f"Top barrier: {top_code or 'none found'} ({barrier_counts.get(top_code, 0) if top_code else 0}/{n} documents).",
        n=n, chart_data=with_ci,
        top_quotes=_top_quotes(barrier_docs.get(top_code, [])) if top_code else [],
    )


def q3_discovery_surfaces(raw_corpus: list[dict] | None = None) -> dict:
    corpus = _relevant(raw_corpus)
    n = len(corpus)
    counts = {}
    docs_by_surface: dict[str, list[dict]] = {}
    for surface, pattern in SURFACE_PATTERNS.items():
        matched = [d for d in corpus if pattern.search(d["raw_text"])]
        counts[surface] = len(matched)
        docs_by_surface[surface] = matched
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    with_ci = [{"surface": s, "n_matching": c, **dict(zip(("rate", "ci_low", "ci_high"), wilson_ci(c, n)))} for s, c in ranked]
    top_surface = ranked[0][0] if ranked and ranked[0][1] > 0 else None
    return _envelope(
        answer_summary=f"Most-mentioned discovery surface: {top_surface or 'none clearly mentioned'}.",
        n=n, chart_data=with_ci,
        top_quotes=_top_quotes(docs_by_surface.get(top_surface, [])) if top_surface else [],
    )


def q4_habit_role(raw_corpus: list[dict] | None = None) -> dict:
    corpus = _relevant(raw_corpus)
    n = len(corpus)
    habit_docs = [d for d in corpus if HABIT_LEXICON.search(d["raw_text"])]
    crosstab: dict[str, int] = {}
    for d in habit_docs:
        seg = d["segment_label"] or "unknown"
        crosstab[seg] = crosstab.get(seg, 0) + 1
    successes = len(habit_docs)
    rate, ci_low, ci_high = wilson_ci(successes, n)
    return _envelope(
        answer_summary=f"{successes} of {n} documents ({rate:.1%}) use habit language (\"always\", \"every week\", \"usual\").",
        n=n, successes=successes, rate=rate, ci_low=ci_low, ci_high=ci_high,
        segment_breakdown=crosstab, top_quotes=_top_quotes(habit_docs),
    )


def q5_information_gap(raw_corpus: list[dict] | None = None) -> dict:
    corpus = _relevant(raw_corpus)
    n = len(corpus)
    counts, docs_by_dim = {}, {}
    for dim, pattern in INFO_GAP_PATTERNS.items():
        matched = [d for d in corpus if pattern.search(d["raw_text"])]
        counts[dim] = len(matched)
        docs_by_dim[dim] = matched
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    with_ci = [{"dimension": dim, "n_matching": c, **dict(zip(("rate", "ci_low", "ci_high"), wilson_ci(c, n)))} for dim, c in ranked]
    top_dim = ranked[0][0] if ranked and ranked[0][1] > 0 else None
    return _envelope(
        answer_summary=f"Most commonly missing pre-purchase information: {top_dim or 'none clearly identified'}.",
        n=n, chart_data=with_ci, top_quotes=_top_quotes(docs_by_dim.get(top_dim, [])) if top_dim else [],
    )


def q6_frequent_frustrations(raw_corpus: list[dict] | None = None) -> dict:
    corpus = raw_corpus if raw_corpus is not None else _corpus()  # includes ops bucket per §10 (include_ops_bucket: true)
    with get_conn() as conn:
        # One query for every current-run theme's avg severity instead of a
        # round trip per theme (was N+1 — one connection+query per theme).
        theme_rows_raw = conn.execute(
            """
            SELECT t.id, t.label, t.doc_count, avg(c.severity) AS avg_severity
            FROM themes t
            LEFT JOIN theme_documents td ON td.theme_id = t.id
            LEFT JOIN classifications c ON c.document_id = td.document_id
            WHERE t.run_id = (SELECT run_id FROM themes ORDER BY run_id DESC LIMIT 1)
            GROUP BY t.id, t.label, t.doc_count
            """
        ).fetchall()
    theme_rows = [dict(t) for t in theme_rows_raw]
    for t in theme_rows:
        t["avg_severity"] = float(t["avg_severity"]) if t["avg_severity"] is not None else 3.0
        t["severity_x_frequency"] = t["avg_severity"] * t["doc_count"]

    ops_docs = [d for d in corpus if d["is_junk"] and d["junk_reason"] == "ops_off_topic"]
    low_rating_share = sum(1 for d in ops_docs if (d["rating"] or 3) <= 2) / len(ops_docs) if ops_docs else 0
    ops_entry = {"label": "Operational complaints (ops bucket)", "doc_count": len(ops_docs), "avg_severity": 1 + 4 * low_rating_share, "severity_x_frequency": (1 + 4 * low_rating_share) * len(ops_docs)}

    ranked = sorted(theme_rows + [ops_entry], key=lambda t: -t["severity_x_frequency"])
    return _envelope(
        answer_summary=f"Top frustration by severity×frequency: {ranked[0]['label']}." if ranked else "No themes yet.",
        n=len(corpus), chart_data=ranked, top_quotes=_top_quotes(ops_docs),
    )


def q7_segment_experimentation(raw_corpus: list[dict] | None = None) -> dict:
    corpus = _relevant(raw_corpus)
    n = len(corpus)
    by_segment: dict[str, list[dict]] = {}
    for d in corpus:
        by_segment.setdefault(d["segment_label"] or "unknown", []).append(d)

    rates = {}
    for seg, docs in by_segment.items():
        exploring = sum(1 for d in docs if EXPLORATION_LEXICON.search(d["raw_text"]))
        rates[seg] = {"n": len(docs), "successes": exploring, **dict(zip(("rate", "ci_low", "ci_high"), wilson_ci(exploring, len(docs))))}

    ranked_segments = sorted(rates.items(), key=lambda kv: -kv[1]["rate"])
    z_tests = []
    if len(ranked_segments) >= 2:
        (seg_a, a), (seg_b, b) = ranked_segments[0], ranked_segments[1]
        z, p = two_proportion_z_test(a["successes"], a["n"], b["successes"], b["n"])
        z_tests.append({"segment_a": seg_a, "segment_b": seg_b, "z": round(z, 3), "p_value": round(p, 4), "significant_at_0_05": p < 0.05})

    return _envelope(
        answer_summary=f"Most exploration-language use: {ranked_segments[0][0]} ({ranked_segments[0][1]['rate']:.1%})." if ranked_segments else "No data.",
        n=n, chart_data=dict(rates), z_tests=z_tests,
        top_quotes=_top_quotes(by_segment.get(ranked_segments[0][0], [])) if ranked_segments else [],
    )


def q8_unmet_needs() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT c.unmet_need, d.id AS document_id, d.raw_text, s.name AS source_name, i.grade, i.iqs_total
            FROM classifications c
            JOIN documents d ON d.id = c.document_id
            JOIN sources s ON s.id = d.source_id
            JOIN theme_documents td ON td.document_id = d.id
            JOIN themes t ON t.id = td.theme_id
            JOIN insights i ON t.id = ANY(i.theme_ids)
            WHERE c.unmet_need IS NOT NULL AND i.iqs_total >= 65
            """
        ).fetchall()
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        grouped.setdefault(r["unmet_need"], []).append(dict(r))
    filtered = {need: docs for need, docs in grouped.items() if len({d["source_name"] for d in docs}) >= 2}
    ranked = sorted(filtered.items(), key=lambda kv: -len(kv[1]))
    return _envelope(
        answer_summary=f"{len(ranked)} unmet need(s) recur across ≥2 sources at IQS≥65." if ranked else "No unmet needs clear ≥2-source/IQS≥65 bar yet.",
        n=sum(len(v) for v in filtered.values()),
        chart_data=[{"unmet_need": need, "n": len(docs), "n_sources": len({d["source_name"] for d in docs})} for need, docs in ranked],
        top_quotes=_top_quotes([d for docs in filtered.values() for d in docs]),
    )


PACK_FUNCTIONS = {
    "q1_repeat_categories": q1_repeat_categories,
    "q2_exploration_barriers": q2_exploration_barriers,
    "q3_discovery_surfaces": q3_discovery_surfaces,
    "q4_habit_role": q4_habit_role,
    "q5_information_gap": q5_information_gap,
    "q6_frequent_frustrations": q6_frequent_frustrations,
    "q7_segment_experimentation": q7_segment_experimentation,
    "q8_unmet_needs": q8_unmet_needs,
}


def list_packs() -> list[dict]:
    cfg = question_packs_config()["packs"]
    return cfg


def run_pack(pack_id: str) -> dict:
    if pack_id not in PACK_FUNCTIONS:
        raise ValueError(f"Unknown question pack: {pack_id}")
    return PACK_FUNCTIONS[pack_id]()


def run_all_packs() -> list[dict]:
    """Runs all eight packs for one page load (the discovery-questions home
    page). Fetches the classified corpus once and hands it to every pack
    that needs it instead of each independently re-running the same
    documents+classifications+sources join — was 6 redundant full-corpus
    queries per call to this function.
    """
    raw_corpus = _corpus()
    results = []
    for pack in list_packs():
        fn = PACK_FUNCTIONS[pack["id"]]
        result = fn(raw_corpus) if fn is not q8_unmet_needs else fn()
        results.append({"id": pack["id"], "question": pack["question"], **result})
    return results
