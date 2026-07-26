"""Loads config/sources.yaml into `sources` and data/samples/reviews.jsonl
into `documents`. This is the Phase-1 path that makes the synthetic corpus
queryable; Phase 2's upload utility (aisle.ingest.upload) generalises the
document-insert half of this to arbitrary CSV/XLSX/JSON/JSONL/TXT files.

Usage: python -m aisle.db.seed
"""
from __future__ import annotations

import json

from aisle.db.connection import get_conn
from aisle.ingest.dedupe import content_hash
from aisle.ingest.pii import hash_author, redact_pii_regex
from aisle.settings import DATA_DIR, get_settings, sources_config

SAMPLES_PATH = DATA_DIR / "samples" / "reviews.jsonl"


def seed_sources() -> dict[str, int]:
    cfg = sources_config()
    ids: dict[str, int] = {}
    with get_conn() as conn:
        for s in cfg["sources"]:
            row = conn.execute(
                """
                INSERT INTO sources (name, kind, brand, config_json, is_active)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET config_json = EXCLUDED.config_json
                RETURNING id
                """,
                (s["name"], s["kind"], s.get("brand", "blinkit"), json.dumps(s.get("config", {})), s.get("enabled", True)),
            ).fetchone()
            ids[s["name"]] = row["id"]
        conn.commit()
    return ids


def seed_documents(source_ids: dict[str, int]) -> tuple[int, int]:
    if not SAMPLES_PATH.exists():
        raise FileNotFoundError(
            f"{SAMPLES_PATH} not found — run `python -m aisle.ingest.generate_synthetic_corpus` first."
        )
    inserted, skipped = 0, 0
    with get_conn() as conn, open(SAMPLES_PATH) as f:
        for line in f:
            row = json.loads(line)
            source_id = source_ids.get(row["source_name"])
            if source_id is None:
                skipped += 1
                continue
            text = redact_pii_regex(row["raw_text"])
            meta = dict(row.get("meta", {}))
            meta["brand"] = row["brand"]
            result = conn.execute(
                """
                INSERT INTO documents
                    (source_id, external_id, raw_text, author_hash, rating, posted_at, url, meta_json, content_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id, external_id) DO NOTHING
                RETURNING id
                """,
                (
                    source_id,
                    row["external_id"],
                    text,
                    hash_author(row["author"]),
                    row.get("rating"),
                    row.get("posted_at"),
                    row.get("url"),
                    json.dumps(meta),
                    content_hash(text),
                ),
            ).fetchone()
            if result is not None:
                inserted += 1
            else:
                skipped += 1
        conn.commit()
    return inserted, skipped


def main() -> None:
    get_settings()  # fail loudly here if env is broken, before touching the DB
    source_ids = seed_sources()
    inserted, skipped = seed_documents(source_ids)
    print(f"Seeded {len(source_ids)} sources; documents inserted={inserted} skipped(dupe/unknown-source)={skipped}")


if __name__ == "__main__":
    main()
