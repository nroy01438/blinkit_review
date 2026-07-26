"""Marketplace / product-review connector — same Trafilatura approach as
ForumConnector (§4 lists both as Trafilatura-based), kept as a separate
class because the two are independently configured/rate-limited sources
even though the fetch mechanics are identical today.
"""
from __future__ import annotations

from aisle.ingest.connectors.forum import ForumConnector


class MarketplaceConnector(ForumConnector):
    kind = "marketplace"
