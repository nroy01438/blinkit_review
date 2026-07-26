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


def delete_documents_for_source(conn, source_name: str) -> None:
    """Deletes every document for a (test-owned) source, first clearing rows
    in tables with a document_id FK (classifications, golden_labels) so this
    never trips a FK violation — safe to call even after other test files'
    suite-wide fixtures (e.g. Phase 3's classify-everything pass) have
    attached classifications to these documents.
    """
    conn.execute(
        "DELETE FROM classifications WHERE document_id IN (SELECT id FROM documents WHERE source_id = "
        "(SELECT id FROM sources WHERE name = %s))",
        (source_name,),
    )
    conn.execute(
        "DELETE FROM golden_labels WHERE document_id IN (SELECT id FROM documents WHERE source_id = "
        "(SELECT id FROM sources WHERE name = %s))",
        (source_name,),
    )
    conn.execute(
        "DELETE FROM documents WHERE source_id = (SELECT id FROM sources WHERE name = %s)", (source_name,)
    )
