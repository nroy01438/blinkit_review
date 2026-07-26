"""Connector ABC (§4). Every connector is independently testable and
independently rate-limited, is incremental (uses `since` as a watermark —
callers pass `sources.last_fetched_at`, never refetches on their own), and
supports `dry_run` to report what it *would* fetch without persisting
anything or calling a live API.
"""
from __future__ import annotations

import abc
from datetime import datetime

from aisle.ingest.schema import RawDoc


class Connector(abc.ABC):
    kind: str
    source_name: str

    def __init__(self, source_name: str, config: dict):
        self.source_name = source_name
        self.config = config

    @abc.abstractmethod
    def fetch(self, since: datetime | None, limit: int, dry_run: bool = False) -> list[RawDoc]:
        """Return docs posted after `since` (or all, if None), capped at
        `limit`. When `dry_run=True`, must not make a live network call or
        persist anything — just report what would be fetched (a real
        connector may return a truncated/sampled preview list).
        """
        raise NotImplementedError
