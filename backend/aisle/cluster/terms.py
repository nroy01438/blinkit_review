"""c-TF-IDF (class-based TF-IDF, BERTopic-style): treats each cluster's
concatenated text as one "class document" so top terms describe what makes
a cluster distinct from the *other clusters*, not just from English in
general — the sole input to theme naming, alongside medoid documents.
"""
from __future__ import annotations

import math
import re
from collections import Counter

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been", "being",
    "i", "me", "my", "you", "your", "it", "its", "we", "our", "they", "their", "he", "she",
    "to", "of", "in", "on", "at", "for", "with", "as", "this", "that", "these", "those",
    "have", "has", "had", "do", "does", "did", "not", "no", "so", "if", "than", "then",
    "just", "can", "will", "would", "could", "should", "there", "here", "from", "by", "about",
}
TOKEN_RE = re.compile(r"[a-z]{2,}")


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def c_tf_idf(cluster_texts: dict[int, list[str]], top_k: int = 10) -> dict[int, list[str]]:
    """`cluster_texts` maps cluster_id -> list of raw document texts.
    Returns cluster_id -> top_k terms by c-TF-IDF score.
    """
    cluster_term_counts: dict[int, Counter] = {}
    for cluster_id, texts in cluster_texts.items():
        counter: Counter = Counter()
        for text in texts:
            counter.update(tokenize(text))
        cluster_term_counts[cluster_id] = counter

    n_clusters = len(cluster_term_counts)
    doc_freq: Counter = Counter()
    for counter in cluster_term_counts.values():
        for term in counter:
            doc_freq[term] += 1

    result: dict[int, list[str]] = {}
    for cluster_id, counter in cluster_term_counts.items():
        total_terms = sum(counter.values()) or 1
        scored = []
        for term, count in counter.items():
            tf = count / total_terms
            idf = math.log(1 + n_clusters / (1 + doc_freq[term]))
            scored.append((term, tf * idf))
        scored.sort(key=lambda t: t[1], reverse=True)
        result[cluster_id] = [term for term, _ in scored[:top_k]]
    return result
