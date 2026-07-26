"""Cost accounting + the --max-cost-usd hard-stop guardrail.

Pricing is approximate (USD per 1K tokens) and intentionally centralised here
so it's the one place to update when list prices change — never hardcode a
price anywhere else in the codebase.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PRICING_PER_1K_TOKENS_USD = {
    "claude-sonnet-5": {"input": 0.003, "output": 0.015},
    "claude-opus-5": {"input": 0.015, "output": 0.075},
    "claude-haiku-4-5-20251001": {"input": 0.001, "output": 0.005},
    # mock model used by MockResponder — always free.
    "mock": {"input": 0.0, "output": 0.0},
}
DEFAULT_PRICE = {"input": 0.003, "output": 0.015}


class MaxCostExceededError(RuntimeError):
    pass


@dataclass
class CostTracker:
    """One instance per pipeline run (a `runs` row). Every LLMClient call on
    that run's behalf reports into the same tracker so `--max-cost-usd` can
    hard-stop mid-run rather than only being checked at the end.
    """

    max_cost_usd: float
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    calls: int = 0
    by_model: dict[str, float] = field(default_factory=dict)

    def price_for(self, model: str, tokens_in: int, tokens_out: int) -> float:
        price = PRICING_PER_1K_TOKENS_USD.get(model, DEFAULT_PRICE)
        return (tokens_in / 1000) * price["input"] + (tokens_out / 1000) * price["output"]

    def check_before_call(self, model: str, est_tokens_in: int, est_tokens_out: int) -> None:
        projected = self.cost_usd + self.price_for(model, est_tokens_in, est_tokens_out)
        if projected > self.max_cost_usd:
            raise MaxCostExceededError(
                f"Projected cost ${projected:.4f} would exceed --max-cost-usd ${self.max_cost_usd:.4f}. "
                f"Spent so far: ${self.cost_usd:.4f} across {self.calls} call(s)."
            )

    def record(self, model: str, tokens_in: int, tokens_out: int) -> float:
        cost = self.price_for(model, tokens_in, tokens_out)
        self.cost_usd += cost
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.calls += 1
        self.by_model[model] = self.by_model.get(model, 0.0) + cost
        return cost
