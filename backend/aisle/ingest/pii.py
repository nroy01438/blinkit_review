"""PII handling: author hashing (never store raw usernames) and text
redaction. The regex pass here is the cheap first line of defence; §2 also
calls for an LLM PII pass before persisting at full ingestion scale — that
hook is `redact_pii_llm` below, left as a deliberate no-op stub in mock/no-key
environments rather than silently skipped without a trace.
"""
from __future__ import annotations

import hashlib
import re

from aisle.settings import get_settings

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"(?:\+?91[-\s]?)?[6-9]\d{9}\b")
ORDER_ID_RE = re.compile(r"\b(?:order|txn|transaction)[\s#:-]*[A-Z0-9]{6,}\b", re.IGNORECASE)


def hash_author(author: str) -> str:
    settings = get_settings()
    salted = f"{settings.author_hash_salt}:{author}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def redact_pii_regex(text: str) -> str:
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = ORDER_ID_RE.sub("[REDACTED_ORDER_ID]", text)
    return text


def redact_pii_llm(text: str) -> str:
    """Placeholder for the LLM PII pass called out in §2. Not wired to a real
    call yet (Phase 2 ingestion pipeline) — returns input unchanged so the
    absence of this pass is visible in a diff/test rather than silently
    assumed equivalent to the regex pass.
    """
    return text
