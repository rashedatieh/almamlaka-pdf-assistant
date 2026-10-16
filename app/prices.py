"""Claude API prices per million tokens, from docs/adr/0001-stack-and-models.md §3.1 (verified 2026-10-15).

Used for the in-app daily budget guard and for cost estimates printed before any live run.
Haiku 5.5 is priced for prompts up to 100k tokens; our prompts are a few thousand (ADR D5).
`inference_geo="us"` multiplies every category by 1.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

US_GEO_MULTIPLIER = 1.1
BATCH_DISCOUNT = 0.5


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_write_5m: float
    cache_read: float


PRICES = {
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_write_5m=5.00, cache_read=0.20),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_write_5m=2.50, cache_read=0.10),
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_write_5m=0.125, cache_read=0.01),
}


def cost_usd(model: str, usage: dict[str, Any], inference_geo: str = "global", batch: bool = False) -> float:
    """Dollar cost of one response's `usage` (input, output, cache write and cache read tokens)."""
    price = PRICES[model]
    total = (
        usage.get("input_tokens", 0) * price.input
        + usage.get("output_tokens", 0) * price.output
        + (usage.get("cache_creation_input_tokens") or 0) * price.cache_write_5m
        + (usage.get("cache_read_input_tokens") or 0) * price.cache_read
    ) / 1_000_000
    if inference_geo == "us":
        total *= US_GEO_MULTIPLIER
    return total * (BATCH_DISCOUNT if batch else 1.0)
