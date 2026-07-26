"""Reddit connector — PRAW, read-only. Pulls both submissions AND comments
(§4 — comments carry the richest reasoning) across the configured
subreddits, searching the configured query terms. Disabled by default in
config/sources.yaml until REDDIT_CLIENT_ID/SECRET are set.
"""
from __future__ import annotations

from datetime import datetime, timezone

from aisle.ingest.connectors._mock_pool import mock_fetch
from aisle.ingest.connectors.base import Connector
from aisle.ingest.schema import RawDoc


class RedditConnector(Connector):
    kind = "reddit"

    def fetch(self, since: datetime | None, limit: int, dry_run: bool = False) -> list[RawDoc]:
        from aisle.settings import get_settings

        settings = get_settings()
        if settings.mock_mode:
            return mock_fetch(self.source_name, since, limit)
        return self._fetch_live(since, limit, dry_run, settings)

    def _fetch_live(self, since, limit, dry_run, settings) -> list[RawDoc]:
        client_id = settings.require("reddit_client_id")
        client_secret = settings.require("reddit_client_secret")

        if dry_run:
            subs = self.config.get("subreddits", [])
            terms = self.config.get("query_terms", [])
            return [
                RawDoc(
                    external_id="dryrun",
                    raw_text=f"[dry-run] would search r/{'+'.join(subs)} for {terms}",
                    author="dry-run",
                    source_name=self.source_name,
                    meta={"dry_run": True},
                )
            ]

        import praw

        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=settings.reddit_user_agent,
        )
        docs: list[RawDoc] = []
        subreddits = self.config.get("subreddits", [])
        terms = self.config.get("query_terms", [])
        include_comments = self.config.get("include_comments", True)

        for sub_name in subreddits:
            subreddit = reddit.subreddit(sub_name)
            for term in terms:
                for submission in subreddit.search(term, sort="new", limit=limit // max(1, len(terms))):
                    posted_at = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
                    if since is not None and posted_at <= since:
                        continue
                    docs.append(
                        RawDoc(
                            external_id=submission.id,
                            raw_text=f"{submission.title}\n\n{submission.selftext}",
                            author=str(submission.author) if submission.author else "deleted",
                            source_name=self.source_name,
                            posted_at=posted_at,
                            url=f"https://reddit.com{submission.permalink}",
                            meta={"subreddit": sub_name, "kind": "submission", "score": submission.score},
                        )
                    )
                    if include_comments:
                        submission.comments.replace_more(limit=0)
                        for comment in submission.comments.list():
                            c_posted_at = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc)
                            if since is not None and c_posted_at <= since:
                                continue
                            docs.append(
                                RawDoc(
                                    external_id=comment.id,
                                    raw_text=comment.body,
                                    author=str(comment.author) if comment.author else "deleted",
                                    source_name=self.source_name,
                                    posted_at=c_posted_at,
                                    url=f"https://reddit.com{comment.permalink}",
                                    meta={"subreddit": sub_name, "kind": "comment", "score": comment.score},
                                )
                            )
                    if len(docs) >= limit:
                        return docs[:limit]
        return docs[:limit]
