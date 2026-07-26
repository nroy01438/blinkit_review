from aisle.db.connection import get_conn
from aisle.ingest.runner import run_ingestion


def test_dry_run_never_persists_and_reports_per_source():
    with get_conn() as conn:
        before = conn.execute("SELECT count(*) AS n FROM documents").fetchone()["n"]

    result = run_ingestion(trigger="manual", limit_per_source=5, dry_run=True, only="playstore_blinkit")

    with get_conn() as conn:
        after = conn.execute("SELECT count(*) AS n FROM documents").fetchone()["n"]

    assert after == before
    assert result["per_source"]["playstore_blinkit"]["dry_run"] is True


def test_one_bad_source_does_not_block_others(monkeypatch):
    import aisle.ingest.runner as runner_mod

    calls = []

    def fake_run_source_ingestion(source_id, source_name, kind, config, *, since, limit, dry_run):
        calls.append(source_name)
        if source_name == "appstore_blinkit":
            raise RuntimeError("simulated connector failure")
        return {"fetched": 0, "inserted": 0}

    monkeypatch.setattr(runner_mod, "run_source_ingestion", fake_run_source_ingestion)
    result = run_ingestion(trigger="manual", limit_per_source=5, dry_run=True)

    assert "appstore_blinkit" in result["errors"]
    assert len(calls) > 1, "a failure in one source must not stop the runner from trying the rest"
