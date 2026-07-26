"""Tiny forward-only SQL migration runner — no ORM migration framework
needed for a handful of files. Usage: `python -m aisle.db.migrate`.
"""
from __future__ import annotations

from pathlib import Path

from aisle.db.connection import get_conn

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def applied_migrations(conn) -> set[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())"
    )
    rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    return {r["filename"] for r in rows}


def run_migrations() -> list[str]:
    applied_now = []
    with get_conn() as conn:
        already = applied_migrations(conn)
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in already:
                continue
            sql = path.read_text()
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
            conn.commit()
            applied_now.append(path.name)
    return applied_now


if __name__ == "__main__":
    applied = run_migrations()
    if applied:
        print(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        print("No pending migrations.")
