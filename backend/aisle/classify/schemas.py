"""Pydantic response schemas for each PM-Gate LLM stage (§6). These are the
`response_model` passed to `LLMClient.complete_json()` — the strict
validation gate mentioned in the top-level brief lives entirely in the
generic LLM client; this file only defines the shapes.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class JunkVerdict(BaseModel):
    is_junk: bool
    junk_reason: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.9)


class PMUtilityScores(BaseModel):
    specificity: int = Field(ge=0, le=4)
    actionability: int = Field(ge=0, le=4)
    evidence_strength: int = Field(ge=0, le=4)
    emotional_intensity: int = Field(ge=0, le=4)
    confidence: float = Field(ge=0.0, le=1.0)


class RelevanceVerdict(BaseModel):
    discovery_relevance: int = Field(ge=0, le=4)
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    categories_mentioned: list[str] = []
    behaviour_codes: list[str] = []
    barrier_codes: list[str] = []
    jtbd_statement: str | None = None
    unmet_need: str | None = None
    segment_label: str | None = None
    lifecycle_stage: str | None = None
    sentiment: str | None = None
    severity: int = Field(ge=1, le=5, default=3)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_span: str
