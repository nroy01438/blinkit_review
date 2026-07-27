import time

import pytest
from pydantic import BaseModel

from aisle.llm.client import LLMClient
from aisle.llm.cost import CostTracker
from aisle.settings import MissingConfigError, get_settings


class Verdict(BaseModel):
    is_junk: bool
    junk_reason: str


def test_mock_call_returns_schema_valid_result():
    client = LLMClient(cost_tracker=CostTracker(max_cost_usd=10.0))
    result = client.complete_json(
        prompt="classify: 'nice app'",
        response_model=Verdict,
        prompt_version="v1",
        mock_response_factory=lambda: {"is_junk": True, "junk_reason": "pure_rating_text"},
    )
    assert result.error is None
    assert result.needs_human_review is False
    assert isinstance(result.parsed, Verdict)
    assert result.parsed.is_junk is True
    assert result.cost_usd == 0.0  # mock calls are free


def test_second_identical_call_is_served_from_cache():
    client = LLMClient(cost_tracker=CostTracker(max_cost_usd=10.0))
    kwargs = dict(
        prompt="classify: 'terrible delivery experience'",
        response_model=Verdict,
        prompt_version="v1",
        mock_response_factory=lambda: {"is_junk": False, "junk_reason": "n/a"},
    )
    first = client.complete_json(**kwargs)
    second = client.complete_json(**kwargs)
    assert first.cached is False
    assert second.cached is True
    assert second.parsed.is_junk is False


def test_validation_failure_retries_then_flags_for_human_review():
    client = LLMClient(cost_tracker=CostTracker(max_cost_usd=10.0))
    result = client.complete_json(
        prompt="classify: 'garbled input that never validates'",
        response_model=Verdict,
        prompt_version="v1",
        mock_response_factory=lambda: {"is_junk": "not-a-bool", "wrong_field": 1},
    )
    assert result.parsed is None
    assert result.needs_human_review is True
    assert result.error is not None


def test_missing_groq_api_key_fails_fast_without_retrying(monkeypatch):
    """A missing GROQ_API_KEY can't be fixed by retrying — this must raise
    immediately (MissingConfigError propagated from `_real_call`), not sleep
    through MAX_API_RETRIES exponential-backoff attempts (~10s) before
    reporting the same configuration error wrapped in a generic RuntimeError.
    """
    monkeypatch.setattr(get_settings(), "mock_llm", False, raising=False)
    client = LLMClient(cost_tracker=CostTracker(max_cost_usd=10.0))

    start = time.monotonic()
    with pytest.raises(MissingConfigError):
        client.complete_json(prompt="anything", response_model=Verdict, prompt_version="v1")
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"took {elapsed:.1f}s — looks like it retried instead of failing fast"
