"""Social connector — deliberately NOT a scraper. §4 is explicit: do not
scrape logged-in surfaces (X/Instagram/YouTube comments). The only path in
is a documented CSV/XLSX export import, which goes through
`aisle.ingest.upload`, not `.fetch()`. `fetch()` exists only to satisfy the
Connector contract for `sources` bookkeeping and always errors with a
pointer to the real path — it must never silently return an empty list,
which would look like "checked, found nothing" instead of "wrong tool."
"""
from __future__ import annotations

from datetime import datetime

from aisle.ingest.connectors._mock_pool import mock_fetch
from aisle.ingest.connectors.base import Connector
from aisle.ingest.schema import RawDoc


class SocialConnector(Connector):
    kind = "social"

    def fetch(self, since: datetime | None, limit: int, dry_run: bool = False) -> list[RawDoc]:
        from aisle.settings import get_settings

        settings = get_settings()
        if settings.mock_mode:
            return mock_fetch(self.source_name, since, limit)
        raise NotImplementedError(
            "The social connector has no live fetch path by design (no logged-in scraping, §4). "
            "Use `python -m aisle.ingest.upload` or POST /upload with a CSV/XLSX export instead."
        )
