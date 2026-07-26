"""Shared MOCK_MODE data source for every connector: the synthetic seed
corpus, filtered by `source_name`. Mirrors the sibling Frontier app's
MOCK_MODE fixture pattern. Not used when `settings.mock_mode` is False —
each connector's real path is independent of this file.
"""
from __future__ import annotations

import json
from datetime import datetime

from aisle.ingest.schema import RawDoc
from aisle.settings import DATA_DIR

_POOL_PATH = DATA_DIR / "samples" / "reviews.jsonl"
_cache: list[dict] | None = None


def _load_pool() -> list[dict]:
    global _cache
    if _cache is None:
        if not _POOL_PATH.exists():
            _cache = []
        else:
            with open(_POOL_PATH) as f:
                _cache = [json.loads(line) for line in f]
    return _cache


def mock_fetch(source_name: str, since: datetime | None, limit: int) -> list[RawDoc]:
    rows = [r for r in _load_pool() if r["source_name"] == source_name]
    docs = []
    for r in rows:
        posted_at = datetime.fromisoformat(r["posted_at"])
        if since is not None and posted_at <= since:
            continue
        docs.append(
            RawDoc(
                external_id=r["external_id"],
                raw_text=r["raw_text"],
                author=r["author"],
                source_name=r["source_name"],
                brand=r["brand"],
                rating=r.get("rating"),
                posted_at=posted_at,
                url=r.get("url"),
                meta=r.get("meta", {}),
            )
        )
    docs.sort(key=lambda d: d.posted_at)
    return docs[:limit]
