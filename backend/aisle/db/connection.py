from __future__ import annotations

import contextlib

import psycopg
from psycopg.rows import dict_row

from aisle.settings import get_settings


@contextlib.contextmanager
def get_conn():
    settings = get_settings()
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn
