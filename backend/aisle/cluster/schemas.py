from __future__ import annotations

from pydantic import BaseModel


class ThemeNaming(BaseModel):
    label: str
    description: str


class MergeDecision(BaseModel):
    should_merge: bool
    rationale: str
