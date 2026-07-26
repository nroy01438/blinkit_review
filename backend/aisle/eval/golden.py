"""Golden-set sampling + label submission (§6). Sampling is stratified
across source, detected language, and PM-utility band so the 300-doc sample
isn't accidentally all-English or all-one-source. Label submission is a
thin upsert — the actual human judgement happens in the /admin/label UI
(Phase 6), never here.
"""
from __future__ import annotations

import json
import random

from aisle.db.connection import get_conn

GOLDEN_SAMPLE_SIZE = 300
SYNTHETIC_PROXY_ANNOTATOR_ID = "synthetic_proxy_v1"


def stratified_sample(n: int = GOLDEN_SAMPLE_SIZE, seed: int = 20260726) -> list[dict]:
    """Buckets candidate documents by (source, lang_detected, pm_verdict) and
    samples roughly evenly across buckets, so no single stratum dominates.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.raw_text, d.lang_detected, s.name AS source_name,
                   c.pm_verdict, c.is_junk, c.discovery_relevance
            FROM documents d
            JOIN sources s ON s.id = d.source_id
            LEFT JOIN classifications c ON c.document_id = d.id
            WHERE d.dupe_of_id IS NULL
            """
        ).fetchall()

    buckets: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r["source_name"], r["lang_detected"], r["pm_verdict"])
        buckets.setdefault(key, []).append(r)

    rng = random.Random(seed)
    for bucket in buckets.values():
        rng.shuffle(bucket)

    sample: list[dict] = []
    bucket_keys = list(buckets.keys())
    i = 0
    while len(sample) < n and any(buckets.values()):
        key = bucket_keys[i % len(bucket_keys)]
        if buckets[key]:
            sample.append(buckets[key].pop())
        i += 1
        if i > n * 10:  # safety valve if buckets exhaust before reaching n
            break
    return sample[:n]


def submit_golden_label(document_id: int, human_label: dict, *, annotator_id: str, label_round: int = 1) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO golden_labels (document_id, human_label_json, annotator_id, round)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (document_id, annotator_id, round) DO UPDATE SET human_label_json = EXCLUDED.human_label_json
            """,
            (document_id, json.dumps(human_label), annotator_id, label_round),
        )
        conn.commit()


def generate_synthetic_proxy_labels(n: int = GOLDEN_SAMPLE_SIZE) -> int:
    """NOT a real golden set. Uses the synthetic corpus's `bucket_hint` (the
    generator's own ground truth, see aisle/ingest/generate_synthetic_corpus.py)
    as a stand-in "annotator" so the metrics pipeline (P/R/F1, kappa,
    calibration, the acceptance gate) can be exercised end-to-end without
    real human labelling. Tagged with a distinct annotator_id specifically
    so it can never be mistaken for real human agreement, and every caller
    that reports these numbers must say so — see aisle/README.md.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, meta_json->>'bucket_hint' AS bucket_hint, meta_json->>'category_hint' AS category_hint
            FROM documents WHERE dupe_of_id IS NULL AND meta_json->>'bucket_hint' IS NOT NULL
            ORDER BY id LIMIT %s
            """,
            (n,),
        ).fetchall()

    written = 0
    for r in rows:
        bucket = r["bucket_hint"]
        is_junk = bucket in ("junk", "ops")
        is_relevant = bucket in ("discovery_low", "discovery_high", "discovery_explorer", "negative_control")
        human_label = {
            "is_junk": is_junk,
            "discovery_relevance": (0 if not is_relevant else (2 if bucket == "discovery_low" else 3)),
            "source": "synthetic_bucket_hint_proxy",
        }
        submit_golden_label(r["id"], human_label, annotator_id=SYNTHETIC_PROXY_ANNOTATOR_ID, label_round=1)
        written += 1
    return written
