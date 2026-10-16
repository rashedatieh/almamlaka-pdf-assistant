"""Pydantic models for every LLM input/output (ENGINEERING_RULES.md) and their structured-output schemas.

Structured outputs (ADR-0001 §3.1 row 3) require `additionalProperties: false` on every object and reject
min/max/length constraints, so limits such as "at most 4 searches" are enforced in code after parsing.
`output_schema()` inlines nested models (no $ref) and refuses unsupported keywords.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

UNSUPPORTED_KEYWORDS = {
    "minimum",
    "maximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "maxItems",
    "exclusiveMinimum",
    "exclusiveMaximum",
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Search(Strict):
    query: str
    lang: Literal["en", "ar"]


class PlannerOutput(Strict):
    """Planner step 2 (PROJECT_PLAN §4.1): context resolution, intent and bilingual search queries."""

    intent: Literal["document_question", "greeting_or_help", "out_of_scope"]
    requested_language: Literal["ar", "en", "none"]  # an explicit "answer in …" request, else "none"
    arabizi: bool  # the message is Arabic written in Latin letters
    reference_resolved: bool  # false when a reference ("he", "it") or the subject can't be resolved
    clarifying_question: str  # "" unless reference_resolved is false
    clarify_options: list[str]  # labels copied from the document map; [] unless reference_resolved is false
    standalone_question_en: str
    standalone_question_ar: str
    searches: list[Search]
    subquestions: list[str]


ClaimKind = Literal["fact", "derived", "conflict_position", "absence", "framing"]


class Evidence(Strict):
    chunk_id: str  # must be one of the passages given to the model (V2)
    quote: str  # verbatim from that passage (V3)


class AnswerClaim(Strict):
    """One sentence of the answer.

    fact, derived and conflict_position claims need evidence; absence and framing claims carry no facts.
    """

    text: str
    kind: ClaimKind
    evidence: list[Evidence]


class AnswerConflict(Strict):
    topic: str
    claim_indexes: list[int]  # the conflict_position claims, one per side


class AnswerOutput(Strict):
    """Answer step 4 (PROJECT_PLAN §4.1).

    The model never supplies page numbers or titles (non-negotiable 2).
    """

    status: Literal["answered", "partial", "not_in_documents", "clarify"]
    premise: Literal["none", "contradicted", "absent"]
    claims: list[AnswerClaim]
    conflicts: list[AnswerConflict]
    missing: list[str]  # what the question asks that the passages don't state
    clarifying_question: str  # "" unless status is clarify
    clarify_options: list[str]


ReportSectionId = Literal[
    "summary", "glance", "budget", "timeline", "team_governance", "disagreements", "risks"
]


class ReportClaim(Strict):
    """One sentence of the executive report (ADR D24): an AnswerClaim placed in a template section."""

    section: ReportSectionId
    paragraph: int  # claims with the same section and paragraph print as one paragraph
    text: str
    kind: ClaimKind
    evidence: list[Evidence]


class ReportOutput(Strict):
    claims: list[ReportClaim]
    conflicts: list[AnswerConflict]  # claim_indexes point into `claims`


class Judgment(Strict):
    claim_index: int
    verdict: Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED"]
    reason: str


class VerifierOutput(Strict):
    """Support judge V5: does the cited evidence support each claim on its own (any language)?"""

    judgments: list[Judgment]


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline(defs[node["$ref"].split("/")[-1]], defs)
        return {k: _inline(v, defs) for k, v in node.items() if k not in {"$defs", "title"}}
    if isinstance(node, list):
        return [_inline(item, defs) for item in node]
    return node


def _check(node: Any, path: str = "$") -> None:
    if isinstance(node, dict):
        bad = UNSUPPORTED_KEYWORDS & node.keys()
        if bad:
            raise ValueError(f"{path}: unsupported structured-output keywords {sorted(bad)}")
        if node.get("type") == "object" and node.get("additionalProperties") is not False:
            raise ValueError(f"{path}: objects must set additionalProperties: false")
        for key, value in node.items():
            _check(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _check(item, f"{path}[{i}]")


def output_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The JSON schema to send as output_config.format.schema, validated against the API's limits."""
    raw = model.model_json_schema()
    schema = _inline(raw, raw.get("$defs", {}))
    _check(schema)
    return schema
