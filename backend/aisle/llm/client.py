"""The ONLY place in the codebase that may call the Groq API.

Every caller goes through `LLMClient.complete_json()`: content-hash cache
lookup, cost-guardrail check, the actual call (or a deterministic mock),
strict Pydantic schema validation with a single corrective retry, and —
on repeated failure — a row in `needs_human_review` instead of a silent
coercion or a crash.

Originally written against the Anthropic API (the brief's specified
stack); switched to Groq because that's the key actually available for
this deployment. Groq's chat-completions endpoint is OpenAI-shaped
(`chat.completions.create`, `resp.choices[0].message.content`,
`resp.usage.prompt_tokens`/`completion_tokens`) rather than Anthropic's
`messages.create`/`resp.content`/`input_tokens`/`output_tokens` shape —
that's the only real difference `_real_call` below has to bridge. Every
other stage in the codebase calls `complete_json()` and never touches a
provider SDK directly, which is the whole point of centralising this here.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from aisle.db.connection import get_conn
from aisle.llm.cache import content_hash, get_cached, put_cache
from aisle.llm.cost import CostTracker, MaxCostExceededError
from aisle.settings import MissingConfigError, get_settings

T = TypeVar("T", bound=BaseModel)

MAX_API_RETRIES = 4
BACKOFF_BASE_SECONDS = 1.5


@dataclass
class LLMResult:
    parsed: BaseModel | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    cached: bool
    needs_human_review: bool
    latency_ms: int
    model: str
    error: str | None = None


class LLMClient:
    def __init__(self, cost_tracker: CostTracker | None = None):
        self.settings = get_settings()
        self.cost_tracker = cost_tracker or CostTracker(max_cost_usd=self.settings.aisle_max_cost_usd)
        self._groq = None

    @property
    def groq(self):
        if self._groq is None:
            import groq

            api_key = self.settings.require("groq_api_key")
            self._groq = groq.Groq(api_key=api_key)
        return self._groq

    def complete_json(
        self,
        *,
        prompt: str,
        response_model: type[T],
        prompt_version: str,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        document_id: int | None = None,
        stage: str = "unknown",
        mock_response_factory: Callable[[], dict] | None = None,
    ) -> LLMResult:
        model = model or self.settings.aisle_bulk_model
        hash_ = content_hash(prompt=prompt, model=model, prompt_version=prompt_version)

        cached = get_cached(hash_)
        if cached is not None:
            parsed, err = self._validate(cached["response"], response_model)
            return LLMResult(
                parsed=parsed,
                tokens_in=cached["tokens_in"],
                tokens_out=cached["tokens_out"],
                cost_usd=0.0,
                cached=True,
                needs_human_review=parsed is None,
                latency_ms=0,
                model=model,
                error=err,
            )

        t0 = time.monotonic()
        if self.settings.mock_llm:
            raw, tokens_in, tokens_out = self._mock_call(prompt, mock_response_factory)
            model_for_cost = "mock"
        else:
            self.cost_tracker.check_before_call(model, est_tokens_in=len(prompt) // 4, est_tokens_out=max_tokens)
            raw, tokens_in, tokens_out = self._real_call(prompt, model, temperature, max_tokens)
            model_for_cost = model
        latency_ms = int((time.monotonic() - t0) * 1000)

        parsed, err = self._validate(raw, response_model)

        if parsed is None and err is not None:
            # single corrective retry with the validation error appended
            retry_prompt = (
                f"{prompt}\n\n---\nYour previous response failed schema validation with this "
                f"error:\n{err}\n\nReturn ONLY corrected JSON matching the required schema."
            )
            if self.settings.mock_llm:
                raw2, ti2, to2 = self._mock_call(retry_prompt, mock_response_factory)
            else:
                raw2, ti2, to2 = self._real_call(retry_prompt, model, temperature, max_tokens)
            tokens_in += ti2
            tokens_out += to2
            parsed, err = self._validate(raw2, response_model)
            raw = raw2 if parsed is not None else raw

        cost = self.cost_tracker.record(model_for_cost, tokens_in, tokens_out)
        put_cache(
            hash_=hash_, prompt_version=prompt_version, model=model, response=raw,
            tokens_in=tokens_in, tokens_out=tokens_out,
        )

        needs_review = parsed is None
        if needs_review and document_id is not None:
            self._flag_for_human_review(document_id, stage, err or "unknown validation failure", raw)

        return LLMResult(
            parsed=parsed,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            cached=False,
            needs_human_review=needs_review,
            latency_ms=latency_ms,
            model=model,
            error=err,
        )

    @staticmethod
    def _validate(raw: dict, response_model: type[T]) -> tuple[T | None, str | None]:
        try:
            return response_model.model_validate(raw), None
        except ValidationError as e:
            return None, str(e)

    def _mock_call(self, prompt: str, factory: Callable[[], dict] | None) -> tuple[dict, int, int]:
        raw = factory() if factory is not None else {}
        return raw, len(prompt) // 4, len(json.dumps(raw)) // 4

    def _real_call(self, prompt: str, model: str, temperature: float, max_tokens: int) -> tuple[dict, int, int]:
        last_exc: Exception | None = None
        for attempt in range(MAX_API_RETRIES):
            try:
                resp = self.groq.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = resp.choices[0].message.content or ""
                raw = _extract_json(text)
                return raw, resp.usage.prompt_tokens, resp.usage.completion_tokens
            except MissingConfigError:
                # a missing GROQ_API_KEY won't fix itself between retries —
                # fail immediately instead of sleeping through 4 pointless
                # attempts before reporting the same configuration error.
                raise
            except Exception as e:  # noqa: BLE001 - broad on purpose, we retry+backoff any transient failure
                last_exc = e
                if attempt < MAX_API_RETRIES - 1:
                    time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
        raise RuntimeError(f"LLM call failed after {MAX_API_RETRIES} attempts: {last_exc}") from last_exc

    @staticmethod
    def _flag_for_human_review(document_id: int, stage: str, reason: str, payload: dict) -> None:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO needs_human_review (document_id, stage, reason, payload_json)
                VALUES (%s, %s, %s, %s)
                """,
                (document_id, stage, reason, json.dumps(payload)),
            )
            conn.commit()


def _extract_json(text: str) -> dict:
    """Responses may wrap JSON in prose or a code fence; find the
    outermost {...} block rather than assuming the whole message is JSON.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")
    return json.loads(text[start : end + 1])
