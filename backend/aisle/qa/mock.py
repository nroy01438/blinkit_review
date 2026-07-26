"""Deterministic MOCK_LLM answer synthesis for the QnA agent. Templates the
answer from the *actual* retrieved evidence and *actual* computed tool
outputs passed in — never invents a number or a quote. This is the same
honesty rule every other mock module in this codebase follows.
"""
from __future__ import annotations


def mock_synthesize(question: str, evidence: list[dict], tool_outputs: dict) -> dict:
    citations = [{"document_id": e["document_id"], "quote": e["quote"][:220]} for e in evidence[:6]]

    parts = [f"Based on {len(evidence)} relevant documents in the corpus:"]

    if "compute_prevalence" in tool_outputs:
        p = tool_outputs["compute_prevalence"]
        parts.append(
            f"{p['successes']} of {p['n']} discovery-relevant documents match this "
            f"({p['rate']:.1%}, 95% CI [{p['ci_low']:.1%}, {p['ci_high']:.1%}])."
        )

    if "run_segment_comparison" in tool_outputs:
        c = tool_outputs["run_segment_comparison"]
        a, b = c["segment_a"], c["segment_b"]
        sig = "a statistically significant difference (p<0.05)" if c["significant_at_0_05"] else "no statistically significant difference (p≥0.05)"
        parts.append(
            f"{a['label']}: {a['successes']}/{a['n']} ({a['rate']:.1%}, CI [{a['ci_low']:.1%}, {a['ci_high']:.1%}]) vs. "
            f"{b['label']}: {b['successes']}/{b['n']} ({b['rate']:.1%}, CI [{b['ci_low']:.1%}, {b['ci_high']:.1%}]) — {sig}."
        )

    if "get_theme_stats" in tool_outputs and tool_outputs["get_theme_stats"]:
        t = tool_outputs["get_theme_stats"]
        parts.append(
            f"Theme \"{t['label']}\": {t['doc_count']} of {t['doc_total']} documents "
            f"({t['prevalence']:.1%}, CI [{t['ci_low']:.1%}, {t['ci_high']:.1%}])."
        )

    if "get_insight" in tool_outputs and tool_outputs["get_insight"]:
        i = tool_outputs["get_insight"]
        parts.append(f"Insight #{i['id']} \"{i['title']}\" (grade {i['grade']}, IQS {i['iqs_total']}): {i['statement']}")

    for e in evidence[:5]:
        parts.append(f"\"{e['quote'][:180]}\" [doc #{e['document_id']}]")

    return {"answer": " ".join(parts), "citations": citations, "refused": False}
