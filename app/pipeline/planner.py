"""Planner step 2 (PROJECT_PLAN §4.1): resolve context, classify intent, produce bilingual searches.

Only the planner sees conversation history (non-negotiable 1). History is labelled as context, not
evidence, and every user text is wrapped in delimiters as untrusted data (non-negotiable 8). The
structured-output schema can't express "at most 4 searches", so the limit is applied here.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.llm.client import LLMClient, LLMError, LLMResult
from app.llm.schemas import PlannerOutput

PROMPT = (Path(__file__).resolve().parents[1] / "llm" / "prompts" / "planner.md").read_text(encoding="utf-8")
MAX_SEARCHES = 4
_DELIMITER = re.compile(r"</?\s*(user_message|conversation_context)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Turn:
    role: str  # "user" or "assistant"
    text: str


@dataclass
class Plan:
    output: PlannerOutput
    queries: list[str]  # what retrieval searches, in order
    llm: LLMResult


def _escape(text: str) -> str:
    """Stop user text from closing or opening our delimiter tags."""
    return _DELIMITER.sub(lambda m: m.group(0).replace("<", "&lt;"), text)


def planner_input(message: str, history: list[Turn], max_turns: int | None = None) -> str:
    limit = max_turns if max_turns is not None else int(os.environ.get("MAX_HISTORY_TURNS", "6"))
    recent = history[-limit:] if limit else []
    context = "\n".join(f"[{t.role}] {_escape(t.text)}" for t in recent) or "(none)"
    return (
        f"<conversation_context>\n{context}\n</conversation_context>\n\n"
        f"<user_message>\n{_escape(message)}\n</user_message>"
    )


def search_queries(output: PlannerOutput) -> list[str]:
    """Standalone English question first, then at most four planner searches; duplicates dropped."""
    if output.intent != "document_question":
        return []
    queries = [output.standalone_question_en, *(s.query for s in output.searches[:MAX_SEARCHES])]
    return list(dict.fromkeys(q.strip() for q in queries if q.strip()))


def plan(client: LLMClient, model: str, message: str, history: list[Turn] | None = None) -> Plan:
    result = client.call(
        route="planner",
        model=model,
        system=PROMPT,
        user=planner_input(message, history or []),
        output=PlannerOutput,
        effort="low",
        max_tokens=4000,
    )
    output = result.parsed
    if not isinstance(output, PlannerOutput):
        raise LLMError("planner returned an unexpected type")
    return Plan(output=output, queries=search_queries(output), llm=result)
