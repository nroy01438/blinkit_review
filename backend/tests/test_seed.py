"""Phase-1 checkpoint: 'sample data is queryable' — requires a live Postgres
(docker-compose up db) with migrations applied. Run:
    python -m aisle.db.migrate && python -m aisle.ingest.generate_synthetic_corpus \
        && pytest tests/test_seed.py

Deliberately does NOT truncate documents/sources first: those are shared,
suite-wide fixture data that later phases' tests (classifications, golden
labels) build on top of across the whole pytest session — a blanket
TRUNCATE ... CASCADE here would silently wipe that state for every test
file that happens to run afterwards (pytest collects alphabetically, and
`test_seed` sorts after e.g. `test_metrics`/`test_pmgate_cascade`, so this
bit exactly that way once). Idempotency is instead verified by seeding
twice in a row and asserting the second pass is a no-op, regardless of
whatever state the corpus was already in.
"""
from aisle.db.connection import get_conn
from aisle.db.seed import seed_documents, seed_sources


def test_seed_is_idempotent_and_corpus_is_queryable():
    source_ids = seed_sources()
    seed_documents(source_ids)  # ensure the corpus is present at least once
    inserted_2, skipped_2 = seed_documents(source_ids)

    assert inserted_2 == 0, "re-seeding must be idempotent (ON CONFLICT DO NOTHING)"
    assert skipped_2 > 0

    with get_conn() as conn:
        row = conn.execute("SELECT count(*) AS n FROM documents").fetchone()
        assert row["n"] >= skipped_2

        by_brand = conn.execute(
            "SELECT meta_json->>'brand' AS brand, count(*) AS n FROM documents GROUP BY 1 ORDER BY 1"
        ).fetchall()
        brands = {r["brand"] for r in by_brand}
        assert {"blinkit", "zepto", "instamart"}.issubset(brands)

        no_pii_leak = conn.execute(
            "SELECT count(*) AS n FROM documents WHERE raw_text ~ '[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z]+'"
        ).fetchone()
        assert no_pii_leak["n"] == 0
