"""Reciprocal Rank Fusion across legs and queries (PROJECT_PLAN §3.1: k = 50)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

RRF_K = 50


def rrf(rankings: Iterable[Sequence[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Fuse ranked ID lists: score = Σ 1 / (k + rank). Best first; ties broken by ID for determinism."""
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
