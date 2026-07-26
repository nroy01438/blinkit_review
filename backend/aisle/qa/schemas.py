from __future__ import annotations

from pydantic import BaseModel


class Citation(BaseModel):
    document_id: int
    quote: str


class AgentAnswer(BaseModel):
    answer: str  # every factual sentence should reference a citation inline, e.g. "...[doc #123]"
    citations: list[Citation]
    refused: bool
