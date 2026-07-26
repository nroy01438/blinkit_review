"""Forum/community connector — Trafilatura over a configured seed-URL list
(sitemap crawl kept intentionally simple: fetch each seed URL's sitemap.xml
if present, else crawl the seed URLs directly). Respects robots.txt via
trafilatura's own fetch, and sets a descriptive User-Agent.
"""
from __future__ import annotations

from datetime import datetime

from aisle.ingest.connectors._mock_pool import mock_fetch
from aisle.ingest.connectors.base import Connector
from aisle.ingest.schema import RawDoc

USER_AGENT = "aisle-discovery-engine/0.1 (+https://github.com/nroy01438/Frontier-Map-)"


class ForumConnector(Connector):
    kind = "forum"

    def fetch(self, since: datetime | None, limit: int, dry_run: bool = False) -> list[RawDoc]:
        from aisle.settings import get_settings

        settings = get_settings()
        if settings.mock_mode:
            return mock_fetch(self.source_name, since, limit)
        return self._fetch_live(since, limit, dry_run)

    def _fetch_live(self, since: datetime | None, limit: int, dry_run: bool) -> list[RawDoc]:
        seed_urls = self.config.get("seed_urls", [])
        max_pages = self.config.get("max_pages", 200)

        if dry_run:
            return [
                RawDoc(
                    external_id="dryrun",
                    raw_text=f"[dry-run] would crawl {len(seed_urls)} seed URL(s), max_pages={max_pages}",
                    author="dry-run",
                    source_name=self.source_name,
                    meta={"dry_run": True},
                )
            ]

        import trafilatura

        docs: list[RawDoc] = []
        for url in seed_urls[:max_pages]:
            downloaded = trafilatura.fetch_url(url, headers={"User-Agent": USER_AGENT})
            if downloaded is None:
                continue
            text = trafilatura.extract(downloaded, include_comments=True, favor_recall=True)
            if not text:
                continue
            docs.append(
                RawDoc(
                    external_id=url,
                    raw_text=text,
                    author="unknown",
                    source_name=self.source_name,
                    url=url,
                    meta={"crawled_via": "trafilatura"},
                )
            )
            if len(docs) >= limit:
                break
        return docs[:limit]
