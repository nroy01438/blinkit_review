from aisle.ingest.pii import hash_author, redact_pii_regex


def test_hash_author_never_returns_raw_input():
    h = hash_author("realusername123")
    assert h != "realusername123"
    assert len(h) == 64  # sha256 hex digest


def test_hash_author_is_deterministic():
    assert hash_author("same_user") == hash_author("same_user")


def test_redact_email_and_phone():
    text = "call me at 9876543210 or email me at foo@bar.com about order ORDER-AB12CD"
    redacted = redact_pii_regex(text)
    assert "9876543210" not in redacted
    assert "foo@bar.com" not in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_EMAIL]" in redacted


def test_redact_preserves_non_pii_text():
    text = "the pomegranates were split and dry, third time this month"
    assert redact_pii_regex(text) == text
