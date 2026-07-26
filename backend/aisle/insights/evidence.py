"""Assembles the evidence pack a theme's insight is drafted from: exemplar
(medoid) documents first, then a random sample of the remaining members, up
to a cap. The brief's §8 target is "20 medoid + 10 random member docs" at
25k+-corpus scale; at this corpus's actual size (tens of eligible docs per
theme, not thousands) that would just mean "every member", so the cap below
degrades gracefully rather than padding with duplicates.
"""
from __future__ import annotations

import random

from aisle.db.connection import get_conn

EVIDENCE_PACK_CAP = 30
RNG_SEED = 20260726


def assemble_evidence_pack(theme_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id AS document_id, d.raw_text, d.posted_at, d.rating, d.meta_json,
                   s.name AS source_name, s.brand, c.segment_label, c.categories_mentioned,
                   td.is_exemplar
            FROM theme_documents td
            JOIN documents d ON d.id = td.document_id
            JOIN sources s ON s.id = d.source_id
            JOIN classifications c ON c.document_id = d.id
            WHERE td.theme_id = %s
            ORDER BY td.is_exemplar DESC, d.id
            """,
            (theme_id,),
        ).fetchall()

    exemplars = [r for r in rows if r["is_exemplar"]]
    rest = [r for r in rows if not r["is_exemplar"]]
    rng = random.Random(RNG_SEED + theme_id)
    rng.shuffle(rest)

    pack = exemplars + rest
    return pack[:EVIDENCE_PACK_CAP]


def segment_cohort_rate(segment_label: str, theme_id: int, relevance_floor: int = 2) -> tuple[int, int]:
    """(successes, n) for "of all relevance-eligible, non-junk documents in
    this segment cohort, how many belong to this theme" — the denominator
    the brief's §7/§8 two-proportion z-test needs.
    """
    with get_conn() as conn:
        n = conn.execute(
            """
            SELECT count(*) AS n FROM documents d JOIN classifications c ON c.document_id = d.id
            WHERE d.dupe_of_id IS NULL AND c.is_junk = false AND c.discovery_relevance >= %s AND c.segment_label = %s
            """,
            (relevance_floor, segment_label),
        ).fetchone()["n"]
        successes = conn.execute(
            """
            SELECT count(*) AS n FROM theme_documents td
            JOIN classifications c ON c.document_id = td.document_id
            WHERE td.theme_id = %s AND c.segment_label = %s
            """,
            (theme_id, segment_label),
        ).fetchone()["n"]
    return successes, n
