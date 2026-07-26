import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("MOCK_MODE", "true")
os.environ.setdefault("MOCK_LLM", "true")
os.environ.setdefault("DATABASE_URL", "postgresql://aisle:aisle@localhost:5433/aisle_dev")


@pytest.fixture(autouse=True)
def _clear_llm_cache():
    """llm_cache is content-addressed and persists in the real DB across test
    runs — clear it first so cache-hit/cache-miss assertions are hermetic."""
    from aisle.db.connection import get_conn

    with get_conn() as conn:
        conn.execute("TRUNCATE llm_cache")
        conn.commit()
    yield


# Every table with a document_id (or document_id-derived) FK, in an order
# that clears leaves before the tables they reference. Extend this list —
# don't hand-roll a new DELETE — whenever a new table gains a document_id
# FK (e.g. Phase 5's insight_evidence), so cross-test-file cleanup never
# regresses into another FK violation like the classifications/embeddings
# ones this list already fixed.
_DOCUMENT_DEPENDENT_TABLES = [
    ("theme_documents", "document_id"),
    ("insight_evidence", "document_id"),
    ("classifications", "document_id"),
    ("golden_labels", "document_id"),
    ("embeddings", "document_id"),
    ("needs_human_review", "document_id"),
]


def delete_documents_for_source(conn, source_name: str) -> None:
    """Deletes every document for a (test-owned) source, first clearing rows
    in every table with a document_id FK so this never trips a FK violation
    — safe to call even after other test files' suite-wide fixtures (e.g.
    Phase 3's classify-everything pass, Phase 4's embed-everything pass)
    have attached rows to these documents.
    """
    for table, fk_column in _DOCUMENT_DEPENDENT_TABLES:
        conn.execute(
            f"DELETE FROM {table} WHERE {fk_column} IN "
            "(SELECT id FROM documents WHERE source_id = (SELECT id FROM sources WHERE name = %s))",
            (source_name,),
        )
    conn.execute(
        "DELETE FROM documents WHERE source_id = (SELECT id FROM sources WHERE name = %s)", (source_name,)
    )
