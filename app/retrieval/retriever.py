"""Retrieval step 3 (PROJECT_PLAN §4.1): BM25 and dense per query, RRF, dedupe, top-k, diversity.

Each planner search runs through both legs. Every resulting ranking (one per leg and query) goes into
one Reciprocal Rank Fusion, and the best `top_k` fused chunks are kept. Then, for each document with no
chunk among them, the best-fused chunk of that document is added. Only chunks that some leg actually
matched take part (BM25 score > 0, or dense similarity ≥ the threshold), so diversity never adds an
unrelated chunk. This keeps both sides of a cross-document conflict (C1, C2) in front of the answer model.

If the dense leg is unavailable, retrieval continues with BM25 alone and records `dense_fallback`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.retrieval.bm25 import BM25
from app.retrieval.dense import DenseLeg, DenseUnavailable
from app.retrieval.fuse import rrf

TOP_K = 8


def index_text(chunk: dict[str, Any]) -> str:
    """What BM25 sees for a chunk: document subtitle, section title and body (§4.1 step 3)."""
    return f"{chunk['doc_subtitle']}\n{chunk['section_title']}\n{chunk['text']}"


@dataclass
class Retrieval:
    chunk_ids: list[str]  # final ranked list given to the answer step
    rankings: dict[str, list[list[str]]] = field(default_factory=dict)  # leg -> one ranking per query
    diversity_added: list[str] = field(default_factory=list)
    dense_fallback: bool = False
    dense_error: str = ""


class Retriever:
    def __init__(
        self, chunks: Sequence[dict[str, Any]], dense: DenseLeg | None = None, top_k: int = TOP_K
    ) -> None:
        self.doc_of = {c["chunk_id"]: c["doc_id"] for c in chunks}
        self.doc_order = list(dict.fromkeys(c["doc_id"] for c in chunks))
        self.bm25 = BM25({c["chunk_id"]: index_text(c) for c in chunks})
        self.dense = dense
        self.top_k = top_k

    def retrieve(self, queries: Sequence[str]) -> Retrieval:
        queries = list(dict.fromkeys(q.strip() for q in queries if q and q.strip()))
        result = Retrieval(chunk_ids=[])
        result.rankings["bm25"] = [[cid for cid, _ in self.bm25.search(q)] for q in queries]
        if self.dense is not None and queries:
            try:
                result.rankings["dense"] = [[cid for cid, _ in hits] for hits in self.dense.search(queries)]
            except DenseUnavailable as exc:
                result.dense_fallback, result.dense_error = True, str(exc)

        fused = [cid for cid, _ in rrf(r for rankings in result.rankings.values() for r in rankings)]
        chosen = fused[: self.top_k]
        for doc_id in self.doc_order:
            if any(self.doc_of[cid] == doc_id for cid in chosen):
                continue
            best = next((cid for cid in fused if self.doc_of[cid] == doc_id), None)
            if best is not None:
                chosen.append(best)
                result.diversity_added.append(best)
        result.chunk_ids = chosen
        return result
