"""The QnA agent (§11). Retrieves via hybrid search; refuses outright below
the evidence floor; otherwise decides which of the four *compute* tools
(beyond search itself) the question calls for, runs them for real against
the live corpus, and synthesizes a cited answer grounded in that evidence
plus those computed numbers — never in the model's own arithmetic.

Tool selection here is rule-based, not a free-form agentic loop: given this
runs under MOCK_LLM in this environment, a real multi-turn tool-call loop
would have nothing genuine driving its choices anyway. The rules below are
a deliberately legible stand-in for what a real Claude tool-use loop would
decide from the same signals (segment names, filter keywords, an explicit
theme/insight reference) — swap `_decide_tools` for a real Anthropic
tool-use loop against `aisle.qa.tools` once real credentials exist; every
tool function underneath is already real and independently callable either
way.
"""
from __future__ import annotations

import re

from aisle.llm.client import LLMClient
from aisle.qa import mock as mock_module
from aisle.qa import tools as tools_module
from aisle.qa.retrieval import hybrid_search
from aisle.qa.schemas import AgentAnswer
from aisle.settings import codes_taxonomy, get_settings

REFUSAL_MIN_DOCS = 5
PROMPT_VERSION = "qa_agent.v1"

PREVALENCE_TRIGGER = re.compile(r"how many|how much|what (percentage|fraction|proportion)|prevalence", re.IGNORECASE)
COMPARISON_TRIGGER = re.compile(r"compare|more likely|versus|\bvs\b|differ", re.IGNORECASE)
THEME_TRIGGER = re.compile(r"\btheme\b", re.IGNORECASE)
INSIGHT_ID_RE = re.compile(r"insight\s*#?\s*(\d+)", re.IGNORECASE)

BARRIER_KEYWORDS = {
    "freshness": "cannot_assess_freshness", "price": "no_price_comparison", "trust": "trust_deficit_new_category",
    "return policy": "unclear_return_policy", "origin": "insufficient_product_info", "expiry": "insufficient_product_info",
}


def _mentioned_segments(question: str) -> list[str]:
    segments = codes_taxonomy()["segments"]
    lower = question.lower()
    return [s for s in segments if s.replace("_", " ") in lower or s in lower]


def _mentioned_filter(question: str) -> dict:
    lower = question.lower()
    for keyword, code in BARRIER_KEYWORDS.items():
        if keyword in lower:
            return {"barrier_code": code}
    return {}


def _decide_tools(question: str, evidence: list[dict]) -> dict:
    outputs: dict = {}

    segments = _mentioned_segments(question)
    if COMPARISON_TRIGGER.search(question) and len(segments) >= 2:
        outputs["run_segment_comparison"] = tools_module.run_segment_comparison(
            segments[0], segments[1], filters=_mentioned_filter(question)
        )
    elif PREVALENCE_TRIGGER.search(question):
        outputs["compute_prevalence"] = tools_module.compute_prevalence(_mentioned_filter(question))

    insight_match = INSIGHT_ID_RE.search(question)
    if insight_match:
        outputs["get_insight"] = tools_module.get_insight(int(insight_match.group(1)))
    elif THEME_TRIGGER.search(question) and evidence:
        # no explicit theme id from the question — use the top retrieved
        # document's theme, the same signal a real agent would read off
        # the search results it just got back.
        top_doc_id = evidence[0]["document_id"]
        from aisle.db.connection import get_conn

        with get_conn() as conn:
            row = conn.execute(
                "SELECT theme_id FROM theme_documents WHERE document_id = %s LIMIT 1", (top_doc_id,)
            ).fetchone()
        if row:
            outputs["get_theme_stats"] = tools_module.get_theme_stats(theme_id=row["theme_id"])

    return outputs


def answer_question(question: str) -> dict:
    raw_docs = hybrid_search(question, top_k=40)
    evidence = [
        {
            "document_id": d["document_id"],
            "quote": d["raw_text"][:400],
            "source_name": d["source_name"],
            "brand": d["brand"],
            "posted_at": str(d["posted_at"]) if d["posted_at"] else None,
        }
        for d in raw_docs
    ]

    if len(evidence) < REFUSAL_MIN_DOCS:
        return {
            "answer": (
                "I don't have enough evidence in the corpus to answer that — here's what I do have: "
                + (
                    "; ".join(f"[doc #{e['document_id']}] \"{e['quote'][:150]}\"" for e in evidence)
                    if evidence
                    else "nothing relevant was retrieved at all."
                )
            ),
            "citations": [{"document_id": e["document_id"], "quote": e["quote"][:220]} for e in evidence],
            "refused": True,
        }

    tool_outputs = _decide_tools(question, evidence)

    settings = get_settings()
    client = LLMClient()
    prompt = (
        f"Answer this question using ONLY the evidence and computed tool outputs below. Cite every factual "
        f"sentence inline with [doc #ID]. If the evidence doesn't support a confident answer, say so rather "
        f"than extrapolating.\n\nQuestion: {question}\n\n"
        f"Evidence:\n" + "\n---\n".join(f"[doc #{e['document_id']}] {e['quote']}" for e in evidence[:15]) + "\n\n"
        f"Computed tool outputs: {tool_outputs}\n\n"
        'Respond with strict JSON: {"answer": string, "citations": [{"document_id": int, "quote": string}], "refused": bool}'
    )
    result = client.complete_json(
        prompt=prompt, response_model=AgentAnswer, prompt_version=PROMPT_VERSION,
        model=settings.aisle_synth_model, stage="qa_agent",
        mock_response_factory=lambda: mock_module.mock_synthesize(question, evidence, tool_outputs),
    )
    if result.parsed is None:
        return mock_module.mock_synthesize(question, evidence, tool_outputs)
    parsed = result.parsed.model_dump()
    parsed["tool_outputs"] = tool_outputs
    return parsed
