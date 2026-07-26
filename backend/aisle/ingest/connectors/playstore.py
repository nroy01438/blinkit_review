"""Play Store connector — `google-play-scraper` (Python port), paginating
NEWEST and MOST_RELEVANT sort orders separately per §4, capturing rating,
thumbs-up count, app version, and any developer reply text into `meta`.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from aisle.ingest.connectors._mock_pool import mock_fetch
from aisle.ingest.connectors.base import Connector
from aisle.ingest.schema import RawDoc
from aisle.settings import get_settings


class PlayStoreConnector(Connector):
    kind = "playstore"

    def fetch(self, since: datetime | None, limit: int, dry_run: bool = False) -> list[RawDoc]:
        settings = get_settings()
        if settings.mock_mode:
            return mock_fetch(self.source_name, since, limit)
        return self._fetch_live(since, limit, dry_run)

    def _fetch_live(self, since: datetime | None, limit: int, dry_run: bool) -> list[RawDoc]:
        try:
            from google_play_scraper import Sort, reviews
        except ImportError as e:
            raise RuntimeError(
                "google-play-scraper is not installed — add it to requirements.txt (already listed) "
                "and `pip install -r requirements.txt`."
            ) from e

        package_name = self.config["package_name"]
        country = self.config.get("country", "in")
        lang = self.config.get("lang", "en")
        sort_orders = self.config.get("sort_orders", ["NEWEST"])
        per_sort_limit = max(1, limit // max(1, len(sort_orders)))

        docs: list[RawDoc] = []
        for sort_name in sort_orders:
            sort_enum = getattr(Sort, sort_name, Sort.NEWEST)
            token = None
            fetched_for_sort = 0
            while fetched_for_sort < per_sort_limit:
                if dry_run:
                    # dry-run: report intent, never call the live API
                    docs.append(
                        RawDoc(
                            external_id=f"dryrun-{sort_name}",
                            raw_text=f"[dry-run] would fetch up to {per_sort_limit} reviews sorted by {sort_name}",
                            author="dry-run",
                            source_name=self.source_name,
                            meta={"dry_run": True},
                        )
                    )
                    break
                batch, token = reviews(
                    package_name,
                    lang=lang,
                    country=country,
                    sort=sort_enum,
                    count=min(200, per_sort_limit - fetched_for_sort),
                    continuation_token=token,
                )
                if not batch:
                    break
                for r in batch:
                    posted_at = r["at"]
                    if posted_at.tzinfo is None:
                        posted_at = posted_at.replace(tzinfo=timezone.utc)
                    if since is not None and posted_at <= since:
                        continue
                    docs.append(
                        RawDoc(
                            external_id=r["reviewId"],
                            raw_text=r["content"] or "",
                            author=r.get("userName", "unknown"),
                            source_name=self.source_name,
                            rating=r.get("score"),
                            posted_at=posted_at,
                            url=None,
                            meta={
                                "thumbs_up": r.get("thumbsUpCount"),
                                "app_version": r.get("appVersion"),
                                "reply_content": r.get("replyContent"),
                                "sort_order": sort_name,
                            },
                        )
                    )
                fetched_for_sort += len(batch)
                if token is None:
                    break
                time.sleep(0.5)  # be polite; Play Store has no documented rate limit but this isn't a race
        return docs[:limit]
