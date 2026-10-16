"""Render step 6 (PROJECT_PLAN §4.1): the verified answer as the UI's AssistantTurn (web/src/lib/api.ts).

Citations are built from chunk metadata only (non-negotiable 2): document, file, PDF page, printed label
and section come from the index, never from the model. Each quote is shown as the exact span of the
chunk text that the model's quote matched, with its character offsets for the evidence spotlight.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.llm.schemas import AnswerClaim, AnswerConflict
from app.textnorm import locate


def citation(n: int, chunk: dict[str, Any], quote: str) -> dict[str, Any]:
    span = locate(quote, chunk["text"])
    start, end = span if span else (0, 0)
    return {
        "n": n,
        "chunkId": chunk["chunk_id"],
        "docId": chunk["doc_id"],
        "docSubtitle": chunk["doc_subtitle"],
        "file": chunk["file"],
        "pdfPage": chunk["pdf_page"],
        "printedLabel": chunk["printed_label"],
        "section": chunk["section"],
        "quote": chunk["text"][start:end] if span else quote,
        "start": start,
        "end": end,
    }


def render_turn(
    *,
    lang: str,
    status: str,
    claims: list[tuple[int, AnswerClaim]],
    conflicts: list[AnswerConflict],
    chunks: dict[str, dict[str, Any]],
    flags: list[str] | None = None,
    missing: list[str] | None = None,
    clarify: dict[str, Any] | None = None,
    message: str = "",
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    numbers: dict[tuple[str, str], int] = {}
    citations: list[dict[str, Any]] = []
    rendered: list[dict[str, Any]] = []
    by_index: dict[int, dict[str, Any]] = {}
    for index, claim in claims:
        refs = []
        for ev in claim.evidence:
            key = (ev.chunk_id, ev.quote)
            if key not in numbers:
                numbers[key] = len(numbers) + 1
                citations.append(citation(numbers[key], chunks[ev.chunk_id], ev.quote))
            refs.append(numbers[key])
        item = {"text": claim.text, "kind": claim.kind, "citations": refs}
        rendered.append(item)
        by_index[index] = item
    return {
        "id": str(uuid.uuid4()),
        "lang": lang,
        "status": status,
        "flags": flags or [],
        "claims": rendered,
        "conflicts": [
            {
                "topic": c.topic,
                "positions": [
                    {"text": by_index[i]["text"], "citations": by_index[i]["citations"]}
                    for i in c.claim_indexes
                    if i in by_index
                ],
            }
            for c in conflicts
        ],
        "missing": missing or [],
        "clarify": clarify,
        "message": message,
        "citations": citations,
        "trace": trace,
        "signature": "",  # signed by the API layer (HMAC, M4)
    }
