"""The one insert path every connector and the upload utility share:
normalise → PII redact → exact-dupe check (content_hash) → near-dupe check
(simhash against the rest of the batch + existing corpus) → insert.

Near-dupe matches get a `dupe_of_id` and are still inserted (kept for audit)
but excluded from every downstream denominator by virtue of `dupe_of_id
IS NULL` filters in classify/cluster/insights queries.
"""
from __future__ import annotations

import json

from langdetect import LangDetectException, detect

from aisle.db.connection import get_conn
from aisle.ingest.dedupe import content_hash, is_near_duplicate_text, simhash
from aisle.ingest.pii import hash_author, redact_pii_llm, redact_pii_regex
from aisle.ingest.schema import RawDoc

NEAR_DUP_SIMILARITY_THRESHOLD = 0.9


def detect_lang(text: str) -> str | None:
    try:
        return detect(text)
    except LangDetectException:
        return None


def persist_docs(docs: list[RawDoc], source_id: int) -> dict:
    """Returns counts: fetched, exact_dupe_skipped, near_dupe_flagged, inserted."""
    counts = {"fetched": len(docs), "exact_dupe_skipped": 0, "near_dupe_flagged": 0, "inserted": 0}
    with get_conn() as conn:
        existing_texts = {
            r["id"]: r["raw_text"]
            for r in conn.execute("SELECT id, raw_text FROM documents WHERE source_id = %s", (source_id,)).fetchall()
        }
        for doc in docs:
            clean_text = redact_pii_llm(redact_pii_regex(doc.raw_text))
            c_hash = content_hash(clean_text)
            s_hash = simhash(clean_text)  # stored for future LSH-bucketing; not the decision itself

            dupe_of_id = None
            for existing_id, existing_text in existing_texts.items():
                if is_near_duplicate_text(clean_text, existing_text, similarity_threshold=NEAR_DUP_SIMILARITY_THRESHOLD):
                    dupe_of_id = existing_id
                    break

            meta = dict(doc.meta)
            meta["brand"] = doc.brand
            if doc.lang_hint:
                meta["lang_hint"] = doc.lang_hint

            row = conn.execute(
                """
                INSERT INTO documents
                    (source_id, external_id, raw_text, lang_detected, author_hash, rating,
                     posted_at, url, meta_json, content_hash, dupe_of_id, simhash)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id, external_id) DO NOTHING
                RETURNING id
                """,
                (
                    source_id,
                    doc.external_id,
                    clean_text,
                    detect_lang(clean_text),
                    hash_author(doc.author),
                    doc.rating,
                    doc.posted_at,
                    doc.url,
                    json.dumps(meta),
                    c_hash,
                    dupe_of_id,
                    s_hash,
                ),
            ).fetchone()

            if row is not None:
                counts["inserted"] += 1
                if dupe_of_id is not None:
                    counts["near_dupe_flagged"] += 1
                existing_texts[row["id"]] = clean_text
            else:
                counts["exact_dupe_skipped"] += 1
        conn.commit()
    return counts


def run_source_ingestion(source_id: int, source_name: str, kind: str, config: dict, *, since, limit: int, dry_run: bool = False) -> dict:
    from aisle.ingest.connectors.registry import build_connector

    connector = build_connector(source_name, kind, config)
    docs = connector.fetch(since=since, limit=limit, dry_run=dry_run)

    if dry_run:
        return {"fetched": len(docs), "dry_run": True, "sample": [d.raw_text[:120] for d in docs[:5]]}

    counts = persist_docs(docs, source_id)
    with get_conn() as conn:
        conn.execute("UPDATE sources SET last_fetched_at = now() WHERE id = %s", (source_id,))
        conn.commit()
    return counts
