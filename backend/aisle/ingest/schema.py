"""The canonical shape every connector and the upload utility normalise into
before anything touches the `documents` table. One shape, one insert path
(`aisle.ingest.pipeline.persist_docs`) — connectors and uploads differ only
in how they produce a list of these.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

# Canonical column names the upload utility's fuzzy-matcher maps arbitrary
# spreadsheet headers onto (§5).
CANONICAL_FIELDS = ["text", "rating", "posted_at", "author", "url", "source", "lang"]


class RawDoc(BaseModel):
    external_id: str
    raw_text: str
    author: str  # hashed at persist time — never before
    source_name: str
    brand: str = "blinkit"
    rating: int | None = None
    posted_at: datetime | None = None
    url: str | None = None
    lang_hint: str | None = None
    meta: dict = {}
