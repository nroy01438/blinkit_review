"""EmbeddingProvider interface (per the top-level brief's tech-stack table:
"pluggable via an EmbeddingProvider interface"). Two implementations:

- `SentenceTransformerEmbeddingProvider` — the real, production default
  (`sentence-transformers/all-MiniLM-L12-v2`, 384-dim, local/free).
- `HashingEmbeddingProvider` — a deterministic feature-hashing ("hashing
  trick") fallback used in this sandbox, which has no network egress to
  Hugging Face. It projects word-shingle hashes into the same 384-dim space
  via random unit vectors keyed by a fixed seed per token, so cosine
  similarity is still a meaningful (if cruder) proxy for lexical overlap —
  enough to cluster the synthetic corpus's templated discovery-language
  reviews sensibly. It is NOT a semantic embedding and must never be
  presented as one; every place that uses it logs which provider ran.

Selection is explicit, not silently automatic: `get_embedding_provider()`
reads `AISLE_EMBEDDING_PROVIDER` (`sentence-transformer` | `hashing`),
defaulting to `hashing` only when `MOCK_MODE=true` — a real deployment must
set the env var or flip MOCK_MODE off to get real embeddings.
"""
from __future__ import annotations

import abc
import hashlib

import numpy as np

from aisle.db.connection import get_conn
from aisle.settings import get_settings

EMBEDDING_DIM = 384


class EmbeddingProvider(abc.ABC):
    model_name: str

    @abc.abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """Returns an (n, EMBEDDING_DIM) float32 array, L2-normalised rows."""
        raise NotImplementedError


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str | None = None):
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # deferred: network/heavyweight import

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)


class HashingEmbeddingProvider(EmbeddingProvider):
    """See module docstring. Deterministic: the same text always yields the
    same vector, and unrelated processes/runs agree because each token's
    projection direction is derived from a hash of the token itself, not
    from any random seed drawn at runtime.
    """

    model_name = "hashing-trick-v1"

    def __init__(self, dim: int = EMBEDDING_DIM, ngram: int = 2):
        self.dim = dim
        self.ngram = ngram

    def _token_vector(self, token: str) -> np.ndarray:
        seed = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = np.random.default_rng(seed)
        return rng.standard_normal(self.dim).astype(np.float32)

    def _shingles(self, text: str) -> list[str]:
        tokens = text.lower().split()
        if len(tokens) < self.ngram:
            return tokens or [""]
        return [" ".join(tokens[i : i + self.ngram]) for i in range(len(tokens) - self.ngram + 1)]

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            vec = np.zeros(self.dim, dtype=np.float32)
            for shingle in self._shingles(text):
                vec += self._token_vector(shingle)
            norm = np.linalg.norm(vec)
            out[i] = vec / norm if norm > 0 else vec
        return out


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    provider_name = getattr(settings, "aisle_embedding_provider", None) or (
        "hashing" if settings.mock_mode else "sentence-transformer"
    )
    if provider_name == "hashing":
        return HashingEmbeddingProvider()
    return SentenceTransformerEmbeddingProvider()


def embed_pending_documents(*, relevance_floor: int = 2, batch_size: int = 64) -> dict:
    """Embeds every non-junk, non-dupe, relevance-eligible document that
    doesn't already have an `embeddings` row. Idempotent: re-running only
    picks up new documents.
    """
    provider = get_embedding_provider()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.raw_text FROM documents d
            JOIN classifications c ON c.document_id = d.id
            LEFT JOIN embeddings e ON e.document_id = d.id
            WHERE e.document_id IS NULL
              AND d.dupe_of_id IS NULL
              AND c.is_junk = false
              AND c.discovery_relevance >= %s
            ORDER BY d.id
            """,
            (relevance_floor,),
        ).fetchall()

    embedded = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        vectors = provider.embed([r["raw_text"] for r in batch])
        with get_conn() as conn:
            for r, vec in zip(batch, vectors):
                conn.execute(
                    """
                    INSERT INTO embeddings (document_id, vector, model_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (document_id) DO NOTHING
                    """,
                    (r["id"], vec.tolist(), provider.model_name),
                )
            conn.commit()
        embedded += len(batch)

    return {"embedded": embedded, "provider": provider.model_name, "pending_before_run": len(rows)}
