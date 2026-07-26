"""Exact-dupe (content_hash) and near-dupe (simhash/Jaccard) detection.

Phase 1 only needs content_hash to exist and be correct — full near-dupe
clustering across the corpus (the `dupe_of_id` backfill pass) is a Phase 2
ingestion-pipeline concern once real, high-volume sources are wired up.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

WHITESPACE_RE = re.compile(r"\s+")


def normalise_for_hash(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.strip().lower()
    text = WHITESPACE_RE.sub(" ", text)
    return text


def content_hash(text: str) -> str:
    normalised = normalise_for_hash(text)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


SIMHASH_BITS = 63  # not 64: Postgres BIGINT is signed, and a 64th set bit
                    # overflows it. 63 bits of hash space is still plenty.


def shingles(text: str, n: int = 3) -> set[str]:
    tokens = normalise_for_hash(text).split()
    if len(tokens) < n:
        return set(tokens)
    return {" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def is_near_duplicate_text(text_a: str, text_b: str, *, similarity_threshold: float = 0.9) -> bool:
    """The authoritative near-dupe decision: exact Jaccard similarity over
    trigram shingles. `simhash()` below is a fast *approximation* of this —
    fine as a future LSH-bucketing pre-filter to avoid O(n^2) scans once the
    corpus is large, but too noisy on short texts with few shingles to be
    the decision itself (verified: it misjudged a genuine ~92%-similar pair
    as ~80% similar), so the pipeline compares raw text directly at the
    corpus sizes this build runs at.
    """
    return jaccard_similarity(shingles(text_a), shingles(text_b)) >= similarity_threshold


def simhash(text: str, *, bits: int = SIMHASH_BITS) -> int:
    """A minimal SimHash over word shingles — a cheap approximate index for
    future LSH-style bucketing at scale; see `is_near_duplicate_text` for the
    actual near-dupe decision this pipeline relies on today.
    """
    shingle_set = shingles(text)
    v = [0] * bits
    for shingle in shingle_set:
        h = int(hashlib.md5(shingle.encode("utf-8")).hexdigest(), 16)
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(bits):
        if v[i] > 0:
            out |= 1 << i
    return out


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def is_near_duplicate(hash_a: int, hash_b: int, *, bits: int = SIMHASH_BITS, similarity_threshold: float = 0.9) -> bool:
    """Approximate near-dupe check from two simhash values only (no text
    access) — see the accuracy caveat on `simhash()`/`is_near_duplicate_text`.
    """
    dist = hamming_distance(hash_a, hash_b)
    similarity = 1 - (dist / bits)
    return similarity >= similarity_threshold
