"""Bookkeeping-only connector for the `manual_upload` source kind. Documents
of this kind are created by `aisle.ingest.upload`, never by `.fetch()` —
same rationale as SocialConnector.
"""
from __future__ import annotations

from datetime import datetime

from aisle.ingest.connectors.base import Connector
from aisle.ingest.schema import RawDoc


class ManualUploadConnector(Connector):
    kind = "manual_upload"

    def fetch(self, since: datetime | None, limit: int, dry_run: bool = False) -> list[RawDoc]:
        raise NotImplementedError(
            "manual_upload has no fetch path — documents arrive via `python -m aisle.ingest.upload` "
            "or POST /upload, never via the scheduled connector runner."
        )
