from __future__ import annotations

from pydantic import BaseModel, Field


class InsightDraft(BaseModel):
    title: str
    statement: str
    so_what: str
    opportunity: str
    affected_segments: list[str] = []
    affected_categories: list[str] = []
    confident: bool  # the drafting instruction: "if evidence doesn't support a
    # confident claim, say so and lower your confidence" — surfaced as this flag


class AdversarialCritique(BaseModel):
    counter_evidence: str
    undermines_insight: bool


class ClaimCheck(BaseModel):
    claim: str
    supported: bool


class IQSVerification(BaseModel):
    claims: list[ClaimCheck]
    actionability_score: int = Field(ge=0, le=4)  # does opportunity name a surface+mechanism+measurable outcome
    novelty_score: int = Field(ge=0, le=4)  # 4 = a PM would NOT already know this; 0 = obvious
    actionability_rationale: str
    novelty_rationale: str
