from __future__ import annotations

from aisle.ingest.connectors.appstore import AppStoreConnector
from aisle.ingest.connectors.base import Connector
from aisle.ingest.connectors.forum import ForumConnector
from aisle.ingest.connectors.manual_upload import ManualUploadConnector
from aisle.ingest.connectors.marketplace import MarketplaceConnector
from aisle.ingest.connectors.playstore import PlayStoreConnector
from aisle.ingest.connectors.reddit import RedditConnector
from aisle.ingest.connectors.social import SocialConnector

CONNECTOR_REGISTRY: dict[str, type[Connector]] = {
    "playstore": PlayStoreConnector,
    "appstore": AppStoreConnector,
    "reddit": RedditConnector,
    "forum": ForumConnector,
    "marketplace": MarketplaceConnector,
    "social": SocialConnector,
    "manual_upload": ManualUploadConnector,
}


def build_connector(source_name: str, kind: str, config: dict) -> Connector:
    cls = CONNECTOR_REGISTRY.get(kind)
    if cls is None:
        raise ValueError(f"No connector registered for source kind '{kind}'")
    return cls(source_name, config)
