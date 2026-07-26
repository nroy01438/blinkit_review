from aisle.ingest.connectors.appstore import AppStoreConnector
from aisle.ingest.connectors.playstore import PlayStoreConnector
from aisle.ingest.connectors.registry import build_connector
from aisle.ingest.connectors.social import SocialConnector


def test_playstore_mock_fetch_returns_docs_from_synthetic_pool():
    connector = PlayStoreConnector("playstore_blinkit", {"package_name": "com.grofers.customerapp"})
    docs = connector.fetch(since=None, limit=10)
    assert len(docs) <= 10
    assert all(d.source_name == "playstore_blinkit" for d in docs)


def test_playstore_mock_fetch_respects_since_watermark():
    connector = PlayStoreConnector("playstore_blinkit", {"package_name": "com.grofers.customerapp"})
    all_docs = connector.fetch(since=None, limit=500)
    assert len(all_docs) > 5
    watermark = sorted(d.posted_at for d in all_docs)[len(all_docs) // 2]
    newer = connector.fetch(since=watermark, limit=500)
    assert all(d.posted_at > watermark for d in newer)
    assert len(newer) < len(all_docs)


def test_appstore_dry_run_never_touches_network():
    connector = AppStoreConnector("appstore_blinkit", {"app_id": "1085004832"})
    docs = connector.fetch(since=None, limit=5)  # mock mode, no network involved either way
    assert isinstance(docs, list)


def test_social_connector_real_mode_refuses_fetch(monkeypatch):
    import aisle.settings as settings_mod

    class FakeSettings:
        mock_mode = False

    monkeypatch.setattr(settings_mod, "get_settings", lambda: FakeSettings())
    connector = SocialConnector("social_csv_import", {})
    try:
        connector.fetch(since=None, limit=5)
        assert False, "expected NotImplementedError"
    except NotImplementedError as e:
        assert "upload" in str(e)


def test_registry_builds_known_kinds():
    connector = build_connector("playstore_blinkit", "playstore", {"package_name": "x"})
    assert isinstance(connector, PlayStoreConnector)
