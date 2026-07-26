from __future__ import annotations

import hashlib
import json

from aisle.db.connection import get_conn


def content_hash(*, prompt: str, model: str, prompt_version: str) -> str:
    payload = f"{model}|{prompt_version}|{prompt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_cached(hash_: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT response_json, tokens_in, tokens_out FROM llm_cache WHERE content_hash = %s",
            (hash_,),
        ).fetchone()
    if row is None:
        return None
    return {
        "response": row["response_json"],
        "tokens_in": row["tokens_in"],
        "tokens_out": row["tokens_out"],
    }


def put_cache(
    *, hash_: str, prompt_version: str, model: str, response: dict, tokens_in: int, tokens_out: int
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO llm_cache (content_hash, prompt_version, model, response_json, tokens_in, tokens_out)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (content_hash) DO NOTHING
            """,
            (hash_, prompt_version, model, json.dumps(response), tokens_in, tokens_out),
        )
        conn.commit()
