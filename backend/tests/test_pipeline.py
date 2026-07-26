from datetime import datetime, timezone

from aisle.db.connection import get_conn
from aisle.ingest.pipeline import persist_docs
from aisle.ingest.schema import RawDoc
from tests.conftest import delete_documents_for_source


def _make_source(name: str) -> int:
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM sources WHERE name = %s", (name,)).fetchone()
        if existing is not None:
            delete_documents_for_source(conn, name)
            conn.commit()
            return existing["id"]
        row = conn.execute(
            "INSERT INTO sources (name, kind, brand) VALUES (%s, 'manual_upload', 'blinkit') RETURNING id",
            (name,),
        ).fetchone()
        conn.commit()
        return row["id"]


def test_persist_docs_is_idempotent():
    source_id = _make_source("test_pipeline_idempotent")
    docs = [
        RawDoc(
            external_id="ext-1",
            raw_text="the pomegranates were split and dry again this week",
            author="alice",
            source_name="test_pipeline_idempotent",
            posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    ]
    first = persist_docs(docs, source_id)
    second = persist_docs(docs, source_id)
    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["exact_dupe_skipped"] == 1


def test_persist_docs_flags_near_duplicate():
    source_id = _make_source("test_pipeline_near_dup")
    docs = [
        RawDoc(
            external_id="ext-a",
            raw_text="the delivery partner could not find my address at all today near the market",
            author="bob",
            source_name="test_pipeline_near_dup",
        ),
        RawDoc(
            external_id="ext-b",
            raw_text="the delivery partner could not find my address at all today near the market entrance",
            author="carol",
            source_name="test_pipeline_near_dup",
        ),
    ]
    counts = persist_docs(docs, source_id)
    assert counts["inserted"] == 2
    assert counts["near_dupe_flagged"] == 1

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT external_id, dupe_of_id FROM documents WHERE source_id = %s ORDER BY external_id", (source_id,)
        ).fetchall()
    assert rows[0]["dupe_of_id"] is None
    assert rows[1]["dupe_of_id"] is not None


def test_persist_docs_hashes_author_never_stores_raw_username():
    source_id = _make_source("test_pipeline_pii")
    docs = [RawDoc(external_id="e1", raw_text="great app", author="realname123", source_name="test_pipeline_pii")]
    persist_docs(docs, source_id)
    with get_conn() as conn:
        row = conn.execute("SELECT author_hash FROM documents WHERE source_id = %s", (source_id,)).fetchone()
    assert row["author_hash"] != "realname123"
