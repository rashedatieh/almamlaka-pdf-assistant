"""Answer step 4 and the support judge V5 (PROJECT_PLAN §4.1).

The answer model receives the standalone question, the original question, the reply language and the
retrieved passages, never the conversation history (non-negotiable 1). Passages are wrapped in
<source> tags as untrusted data (non-negotiable 8); text that could close a tag is escaped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.llm.client import LLMClient, LLMResult
from app.llm.schemas import AnswerClaim, AnswerOutput, Judgment, VerifierOutput
from app.pipeline.verify import Judge

PROMPTS = Path(__file__).resolve().parents[1] / "llm" / "prompts"
ANSWER_PROMPT = (PROMPTS / "answer.md").read_text(encoding="utf-8")
VERIFIER_PROMPT = (PROMPTS / "verifier.md").read_text(encoding="utf-8")
_TAG = re.compile(r"</?\s*(source|question|reply_language|feedback|claim|evidence|passage)\b", re.IGNORECASE)


def _escape(text: str) -> str:
    return _TAG.sub(lambda m: m.group(0).replace("<", "&lt;"), text)


def passages(chunks: list[dict[str, Any]]) -> str:
    return "\n".join(
        f'<source id="{c["chunk_id"]}" document="{c["doc_subtitle"]}" section="{_escape(c["section"])}">\n'
        f"{_escape(c['text'])}\n</source>"
        for c in chunks
    )


def answer_input(
    question: str, standalone: str, reply_lang: str, chunks: list[dict[str, Any]], feedback: list[str]
) -> str:
    parts = [
        f"<question>\n{_escape(question)}\n</question>",
        f'<question kind="standalone">\n{_escape(standalone)}\n</question>',
        f"<reply_language>{reply_lang}</reply_language>",
        passages(chunks),
    ]
    if feedback:
        notes = "\n".join(f"- {_escape(f)}" for f in feedback)
        parts.append(
            f"<feedback>\nYour previous answer failed verification. Fix these problems:\n{notes}\n</feedback>"
        )
    return "\n\n".join(parts)


def generate(
    client: LLMClient,
    model: str,
    question: str,
    standalone: str,
    reply_lang: str,
    chunks: list[dict[str, Any]],
    feedback: list[str] | None = None,
) -> LLMResult:
    return client.call(
        route="answer",
        model=model,
        system=ANSWER_PROMPT,
        user=answer_input(question, standalone, reply_lang, chunks, feedback or []),
        output=AnswerOutput,
        effort="low",
        max_tokens=8000,
    )


def judge_input(claims: list[tuple[int, AnswerClaim]], retrieved: dict[str, dict[str, Any]]) -> str:
    blocks = []
    for index, claim in claims:
        # document, initiative and section come from the index (trusted metadata, not passage text), so
        # "The Team & Governance Document states ..." can be checked like any other detail of a claim.
        evidence = "\n".join(
            f'<evidence chunk="{ev.chunk_id}" document="{retrieved[ev.chunk_id]["doc_subtitle"]}" '
            f'initiative="{retrieved[ev.chunk_id]["doc_title"]}" '
            f'section="{_escape(retrieved[ev.chunk_id]["section"])}">\n'
            f"<quote>{_escape(ev.quote)}</quote>\n"
            f"<passage>{_escape(retrieved[ev.chunk_id]['text'])}</passage>\n</evidence>"
            for ev in claim.evidence
        )
        blocks.append(
            f'<claim index="{index}" kind="{claim.kind}">\n{_escape(claim.text)}\n{evidence}\n</claim>'
        )
    return "\n\n".join(blocks)


_SEVERITY = {"SUPPORTED": 0, "PARTIAL": 1, "UNSUPPORTED": 2}


def _verdicts(judgments: list[Judgment], wanted: list[int]) -> dict[int, str]:
    """One verdict per claim sent, failing closed.

    A claim the judge skipped is UNSUPPORTED; a claim judged more than once keeps its most severe verdict
    (any PARTIAL or UNSUPPORTED beats SUPPORTED); judgments for indexes that weren't sent are ignored.
    """
    seen: dict[int, list[str]] = {i: [] for i in wanted}
    for j in judgments:
        if j.claim_index in seen:
            seen[j.claim_index].append(j.verdict)
    return {i: max(v, key=_SEVERITY.__getitem__) if v else "UNSUPPORTED" for i, v in seen.items()}


def make_judge(
    client: LLMClient, model: str, retrieved: dict[str, dict[str, Any]], costs: list[LLMResult]
) -> Judge:
    """V5 as one model call per batch of claims, validated fail-closed (`_verdicts`)."""

    def judge(claims: list[tuple[int, AnswerClaim]]) -> dict[int, str]:
        result = client.call(
            route="verifier",
            model=model,
            system=VERIFIER_PROMPT,
            user=judge_input(claims, retrieved),
            output=VerifierOutput,
            effort="medium",
            max_tokens=6000,
        )
        costs.append(result)
        return _verdicts(result.parsed.judgments, [i for i, _ in claims])  # type: ignore[attr-defined]

    return judge
