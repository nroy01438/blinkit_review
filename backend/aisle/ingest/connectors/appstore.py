"""App Store connector — iTunes RSS JSON feed (no auth required), paginated
by the `page` query param since a single page caps at ~50 reviews and the
feed caps at ~500 total (§4). No Python `app-store-scraper` equivalent is
needed since the RSS feed is public JSON.
"""
from __future__ import annotations

from datetime import datetime

from aisle.ingest.connectors._mock_pool import mock_fetch
from aisle.ingest.connectors.base import Connector
from aisle.ingest.schema import RawDoc

RSS_URL_TEMPLATE = (
    "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
)
MAX_PAGES = 10  # iTunes RSS caps around page 10 (~500 reviews)


class AppStoreConnector(Connector):
    kind = "appstore"

    def fetch(self, since: datetime | None, limit: int, dry_run: bool = False) -> list[RawDoc]:
        from aisle.settings import get_settings

        settings = get_settings()
        if settings.mock_mode:
            return mock_fetch(self.source_name, since, limit)
        return self._fetch_live(since, limit, dry_run)

    def _fetch_live(self, since: datetime | None, limit: int, dry_run: bool) -> list[RawDoc]:
        import httpx

        app_id = self.config["app_id"]
        country = self.config.get("country", "in")

        if dry_run:
            return [
                RawDoc(
                    external_id="dryrun",
                    raw_text=f"[dry-run] would page through up to {MAX_PAGES} RSS pages for app {app_id}",
                    author="dry-run",
                    source_name=self.source_name,
                    meta={"dry_run": True},
                )
            ]

        docs: list[RawDoc] = []
        with httpx.Client(timeout=15, headers={"User-Agent": "aisle-discovery-engine/0.1"}) as client:
            for page in range(1, MAX_PAGES + 1):
                if len(docs) >= limit:
                    break
                url = RSS_URL_TEMPLATE.format(country=country, page=page, app_id=app_id)
                resp = client.get(url)
                if resp.status_code == 429:
                    break
                resp.raise_for_status()
                entries = resp.json().get("feed", {}).get("entry", [])
                if not entries or (page == 1 and len(entries) <= 1):
                    break  # first "entry" on page 1 is often just feed metadata
                for entry in entries:
                    if "im:rating" not in entry:
                        continue  # skip the feed-metadata pseudo-entry
                    external_id = entry.get("id", {}).get("label", "")
                    posted_at_raw = entry.get("updated", {}).get("label")
                    posted_at = (
                        datetime.fromisoformat(posted_at_raw.replace("Z", "+00:00"))
                        if posted_at_raw
                        else None
                    )
                    if since is not None and posted_at is not None and posted_at <= since:
                        continue
                    docs.append(
                        RawDoc(
                            external_id=external_id or f"appstore-{page}-{len(docs)}",
                            raw_text=entry.get("content", {}).get("label", ""),
                            author=entry.get("author", {}).get("name", {}).get("label", "unknown"),
                            source_name=self.source_name,
                            rating=int(entry.get("im:rating", {}).get("label", 0)) or None,
                            posted_at=posted_at,
                            url=entry.get("link", {}).get("attributes", {}).get("href"),
                            meta={"app_version": entry.get("im:version", {}).get("label")},
                        )
                    )
        return docs[:limit]
