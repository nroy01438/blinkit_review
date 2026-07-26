from __future__ import annotations

import contextlib

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from aisle.settings import get_settings


@contextlib.contextmanager
def get_conn():
    settings = get_settings()
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        register_vector(conn)  # so `vector` columns round-trip as numpy arrays, not strings
        yield conn
