from __future__ import annotations

import contextlib
import functools

from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from aisle.settings import get_settings


@functools.lru_cache
def _pool() -> ConnectionPool:
    """A process-wide pool, not a fresh connection per call. Every `get_conn()`
    used to open a brand-new TCP+TLS+auth handshake to Postgres — on a
    hosted deployment (Render -> Supabase pooler, often cross-region) that's
    ~100s of ms paid again on every single query, and endpoints that made
    several sequential `get_conn()` calls (e.g. /quality/metrics, /overview)
    paid it several times over per request. Render runs this as one
    long-lived process, so a pool opened once at first use and kept warm for
    the process's lifetime amortises that cost across every request instead.
    `register_vector` only needs to run once per physical connection (it
    patches type adapters on that connection object), so it belongs in
    `configure`, called on connection creation, not on every checkout.
    """
    settings = get_settings()
    return ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row},
        configure=register_vector,
        open=True,
    )


@contextlib.contextmanager
def get_conn():
    with _pool().connection() as conn:
        yield conn
