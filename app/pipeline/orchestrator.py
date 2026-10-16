"""One chat turn end to end (PROJECT_PLAN §4): guard, language, planner, retrieval, answer, verify, render.

`Engine.run` yields events for the SSE endpoint (web/src/lib/api.ts StreamEvent):
  {"type": "stage", "stage": planning|retrieving|answering|verifying}
  {"type": "claim", "claim": …, "citations": […]}     each verified claim, before the final turn
  {"type": "final", "turn": AssistantTurn}
  {"type": "error", "code": …, "message": …, "lang": …}  guard refusals (too_long, turn_cap, budget_exhausted)
Guards run before any model call (Q-01, Q-02). Every billed call counts against the budget, failed ones
too (LLMError carries its cost). A failed answer call (V1: schema, max_tokens, refusal) or a verification
drop gets one regeneration with feedback; the better of the two verified attempts is rendered, downgraded
to partial / not_in_documents as needed, or the turn errors. An unverified claim is never yielded.
Text the model writes outside its claims (clarify question and options, conflict topics, missing items)
passes verify.meta_ok too; topics and missing items ride in the claims' support-judge call. Those lines
and the clarify question must also be in the reply language (L-01), else they are replaced or dropped.
Error and budget turns use the reply language once the planner has resolved it, else the guess.
"""

from __future__ import annotations

import logging
import os
import time
import unicodedata
from collections.abc import Generator, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from app import lang as language
from app.budget import BudgetExhausted, DailyBudget
from app.i18n import message as msg
from app.llm.client import CassetteMissing, LLMClient, LLMError, LLMResult
from app.llm.schemas import AnswerClaim, AnswerConflict, AnswerOutput
from app.pipeline import answer as answer_step
from app.pipeline.injection import override_attempt
from app.pipeline.planner import Turn, plan
from app.pipeline.render import render_turn
from app.pipeline.verify import EVIDENCE_KINDS, Judge, Verification, language_ok, meta_ok, verify
from app.retrieval.conflicts import expand
from app.retrieval.retriever import Retriever
from app.textnorm import for_match, quote_in

log = logging.getLogger("almamlaka.orchestrator")
DOCUMENTS = ["OVR", "BUD", "GOV"]
MetaItem = tuple[str, str]  # (kind, text) for verify.meta_ok; kind is "absence" or "framing"


@dataclass(frozen=True)
class Settings:
    planner_model: str = "claude-sonnet-5-5"
    answer_model: str = "claude-sonnet-5-5"
    verifier_model: str = "claude-sonnet-5-5"
    max_input_chars: int = 1000
    max_turns: int = 30

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            planner_model=env.get("PLANNER_MODEL", cls.planner_model),
            answer_model=env.get("ANSWER_MODEL", cls.answer_model),
            verifier_model=env.get("VERIFIER_MODEL", cls.verifier_model),
            max_input_chars=int(env.get("MAX_INPUT_CHARS", cls.max_input_chars)),
            max_turns=int(env.get("MAX_TURNS_PER_SESSION", cls.max_turns)),
        )


def clean(message: str) -> str:
    """Unicode whitespace becomes a space, so words never glue; control characters (Cc, except newline and
    tab) and format characters (Cf: bidi overrides, zero-width) are dropped."""
    kept = []
    for ch in message:
        if ch in "\n\t":
            kept.append(ch)
        elif ch.isspace():
            kept.append(" ")
        elif unicodedata.category(ch) not in {"Cc", "Cf"}:
            kept.append(ch)
    return "".join(kept).strip()


def _key(text: str) -> str:
    return for_match(text).casefold()


def _labels(chunks: Iterable[dict[str, Any]]) -> set[str]:
    """Section titles, table cells (names, roles, departments) and key-value keys and values."""
    labels: list[str] = []
    for chunk in chunks:
        labels.append(chunk.get("section_title") or "")
        for table in chunk.get("tables") or []:
            for row in [table.get("header", []), *table.get("rows", [])]:
                labels.extend(row)
        if "key-value" in chunk.get("kind", ""):
            for line in chunk["text"].split("\n"):
                labels.extend(line.split(":", 1))
    return {_key(label) for label in labels if label.strip()}


def documented_options(options: list[str], chunks: dict[str, dict[str, Any]]) -> list[str]:
    """Options that are a label of these chunks or sit verbatim in one (quote_in); first spelling kept."""
    labels = _labels(chunks.values())
    kept: dict[str, str] = {}
    for option in (o.strip() for o in options):
        if option and _key(option) not in kept:
            if _key(option) in labels or any(quote_in(option, c["text"]) for c in chunks.values()):
                kept[_key(option)] = option
    return list(kept.values())


class MetaBatch:
    """An answer's meta items (conflict topics, missing items), judged in the claims' support-judge call.

    verify.meta_ok owns the deterministic gate and the judge contract. It runs once here with a recording
    judge to learn which items reach the judge; `fold` makes the claim judge's first call carry them too;
    `results` replays those verdicts through meta_ok, or makes the one extra judge call when the claim
    judge was never called.
    """

    def __init__(self, items: list[MetaItem]) -> None:
        self.items = list(dict.fromkeys((kind, text) for kind, text in items if text.strip()))
        self.pending: list[AnswerClaim] = []
        if self.items:
            meta_ok(self.items, self._record)
        self.verdicts: dict[MetaItem, str] | None = None if self.pending else {}

    def _record(self, claims: list[tuple[int, AnswerClaim]]) -> dict[int, str]:
        self.pending = [c for _, c in claims]
        return {}

    def fold(self, judge: Judge) -> Judge:
        def folded(claims: list[tuple[int, AnswerClaim]]) -> dict[int, str]:
            if self.verdicts is not None:
                return judge(claims)
            start = max((i for i, _ in claims), default=-1) + 1
            extra = list(enumerate(self.pending, start))
            verdicts = judge([*claims, *extra])
            self.verdicts = {(c.kind, c.text): verdicts.get(i, "UNSUPPORTED") for i, c in extra}
            wanted = {i for i, _ in claims}
            return {i: v for i, v in verdicts.items() if i in wanted}

        return folded

    def results(self, judge: Judge) -> dict[MetaItem, bool]:
        if not self.items:
            return {}
        verdicts = self.verdicts
        if verdicts is None:
            ok = meta_ok(self.items, judge)
        else:
            ok = meta_ok(
                self.items,
                lambda claims: {i: verdicts.get((c.kind, c.text), "UNSUPPORTED") for i, c in claims},
            )
        return dict(zip(self.items, ok, strict=True))


def in_language(text: str, lang: str) -> bool:
    """L-01 for a model-written line outside the claims (topic, missing item, clarify question)."""
    return language_ok([AnswerClaim(text=text, kind="framing", evidence=[])], lang)


def meta_items(answer: AnswerOutput, lang: str) -> list[MetaItem]:
    """What may be shown besides the claims: lines in the reply language only (L-01), and nothing when the
    turn becomes not_in_documents. A line left out here counts as failed (replaced or dropped)."""
    if answer.status == "not_in_documents" or answer.premise == "absent":
        return []
    items = [*(("framing", c.topic) for c in answer.conflicts), *(("absence", m) for m in answer.missing)]
    return [(kind, text) for kind, text in items if in_language(text, lang)]


@dataclass
class Attempt:
    answer: AnswerOutput
    checked: Verification
    meta: MetaBatch

    @property
    def evidence(self) -> int:
        return sum(1 for _, c in self.checked.kept if c.kind in EVIDENCE_KINDS)


def better(first: Attempt, second: Attempt) -> Attempt:
    """The regeneration, unless it is worse: its language fails where the first passed, or it keeps fewer
    evidence claims."""
    if first.checked.language_ok != second.checked.language_ok:
        return first if first.checked.language_ok else second
    return first if second.evidence < first.evidence else second


@dataclass
class _State:
    lang: str  # the guess until the planner resolves the reply language


@dataclass
class Engine:
    client: LLMClient
    retriever: Retriever
    chunks: dict[str, dict[str, Any]]
    budget: DailyBudget
    settings: Settings = field(default_factory=Settings)
    conflict_groups: list[list[str]] = field(default_factory=list)  # app.retrieval.conflicts

    def _record(self, cost: float, from_cassette: bool) -> None:
        self.budget.record(0.0 if from_cassette else cost)

    def _spend(self, result: LLMResult) -> None:
        self._record(result.cost_usd, result.from_cassette)

    def _spend_failed(self, exc: LLMError) -> None:
        self._record(exc.cost_usd, exc.from_cassette)

    @contextmanager
    def _judge(self, retrieved: dict[str, dict[str, Any]]) -> Iterator[Judge]:
        """The support judge: each call is budget-checked first, and billed even if the caller raises."""
        costs: list[LLMResult] = []
        inner = answer_step.make_judge(self.client, self.settings.verifier_model, retrieved, costs)

        def judge(claims: list[tuple[int, AnswerClaim]]) -> dict[int, str]:
            self.budget.check()
            return inner(claims)

        try:
            yield judge
        finally:
            for result in costs:
                self._spend(result)

    def run(self, message: str, history: list[Turn], turns_so_far: int = 0) -> Iterator[dict[str, Any]]:
        started = time.monotonic()
        state = _State(lang=language.detect(message))
        message = clean(message)
        if len(message) > self.settings.max_input_chars:
            yield self._refusal("too_long", state.lang)
            return
        if turns_so_far >= self.settings.max_turns:
            yield self._refusal("turn_cap", state.lang)
            return
        attempt, hint = override_attempt(message)
        if attempt:  # rule-change / prompt-extraction attempts are refused before any model call
            log.info("override attempt refused")  # no message content in logs (non-negotiable 7)
            yield self._template(hint or state.lang, "out_of_scope", "injection_refused")
            return
        try:
            yield from self._turn(message, history, state, started)
        except BudgetExhausted:
            yield self._refusal("budget_exhausted", state.lang)
        except LLMError as exc:
            self._spend_failed(exc)
            log.warning("turn failed: %s", exc)  # no message content in logs (non-negotiable 7)
            yield self._template(state.lang, "error", "error")

    def _refusal(self, code: str, lang: str) -> dict[str, Any]:
        return {"type": "error", "code": code, "message": msg(code, lang), "lang": lang}

    def _template(self, lang: str, status: str, key: str) -> dict[str, Any]:
        return {
            "type": "final",
            "turn": render_turn(
                lang=lang, status=status, claims=[], conflicts=[], chunks=self.chunks, message=msg(key, lang)
            ),
        }

    def _turn(
        self, message: str, history: list[Turn], state: _State, started: float
    ) -> Iterator[dict[str, Any]]:
        self.budget.check()
        yield {"type": "stage", "stage": "planning"}
        planned = plan(self.client, self.settings.planner_model, message, history)
        self._spend(planned.llm)
        p = planned.output
        lang = state.lang = language.reply_language(message, p.requested_language, p.arabizi)

        if p.intent == "out_of_scope":
            yield self._template(lang, "out_of_scope", "out_of_scope")
            return
        if p.intent == "greeting_or_help":
            yield self._template(lang, "greeting_or_help", "greeting")
            return
        if not p.reference_resolved:
            sources = self.chunks  # nothing retrieved yet: options are checked against every chunk
            if p.searches:
                yield {"type": "stage", "stage": "retrieving"}
                found = self.retriever.retrieve(planned.queries).chunk_ids
                sources = {cid: self.chunks[cid] for cid in found} or self.chunks
            yield {"type": "stage", "stage": "verifying"}
            yield self._clarify(lang, p.clarifying_question, p.clarify_options, sources)
            return

        yield {"type": "stage", "stage": "retrieving"}
        retrieval = self.retriever.retrieve(planned.queries)
        if not retrieval.chunk_ids:
            yield self._absence(lang, planned.queries, retrieval, started)
            return
        # Conflict-aware retrieval: one side of a known disagreement brings in the other sides.
        retrieval.chunk_ids = expand(retrieval.chunk_ids, self.conflict_groups)
        retrieved = {cid: self.chunks[cid] for cid in retrieval.chunk_ids}
        standalone = p.standalone_question_ar if lang == "ar" else p.standalone_question_en
        outcome = yield from self._attempts(message, standalone, lang, retrieved)
        if isinstance(outcome, dict):  # the answer model asked to clarify
            yield outcome
            return
        yield from self._final(lang, outcome, retrieved, planned.queries, retrieval, started)

    def _attempts(
        self, message: str, standalone: str, lang: str, retrieved: dict[str, dict[str, Any]]
    ) -> Generator[dict[str, Any], None, Attempt | dict[str, Any]]:
        """Up to two answer attempts; returns the better verified Attempt, or a clarify final event."""
        passages = list(retrieved.values())
        feedback: list[str] = []
        best: Attempt | None = None
        for n in range(2):
            self.budget.check()
            yield {"type": "stage", "stage": "answering"}
            try:
                result = answer_step.generate(
                    self.client, self.settings.answer_model, message, standalone, lang, passages, feedback
                )
            except CassetteMissing:
                raise  # a replay gap is a setup problem, not a model failure
            except LLMError as exc:  # V1: schema mismatch, max_tokens or refusal
                if n == 1 and best is None:
                    raise
                self._spend_failed(exc)
                log.info("answer attempt %d failed: %s", n + 1, exc)
                if best is not None:
                    break  # keep the first verified attempt
                feedback = [
                    f"Your previous reply could not be used ({exc}). Return one complete JSON object that "
                    "matches the schema, with short claims and short quotes."
                ]
                continue
            self._spend(result)
            if not isinstance(result.parsed, AnswerOutput):
                raise LLMError("answer step returned an unexpected type")
            answer = result.parsed
            if answer.status == "clarify":
                if best is not None and best.checked.language_ok and best.evidence:
                    break  # a verified answer beats a late request to clarify
                yield {"type": "stage", "stage": "verifying"}
                return self._clarify(lang, answer.clarifying_question, answer.clarify_options, retrieved)
            self.budget.check()
            yield {"type": "stage", "stage": "verifying"}
            meta = MetaBatch(meta_items(answer, lang))
            try:
                with self._judge(retrieved) as judge:
                    checked = verify(answer, retrieved, lang, meta.fold(judge))
            except CassetteMissing:
                raise
            except LLMError as exc:
                if best is None:
                    raise
                self._spend_failed(exc)
                log.info("verification of attempt %d failed: %s", n + 1, exc)
                break
            current = Attempt(answer, checked, meta)
            best = current if best is None else better(best, current)
            if not checked.dropped and checked.language_ok:
                break
            feedback = [f"{d.reason} (claim: {d.claim.text})" for d in checked.dropped]
            if not checked.language_ok:
                feedback.append(f"Write every claim in the reply language '{lang}'.")
            log.info("verification attempt %d dropped %d claims", n + 1, len(checked.dropped))

        if best is None:
            raise LLMError("no answer was produced")
        if not best.checked.language_ok:
            raise LLMError("reply language check failed after regeneration")
        return best

    def _clarify(
        self, lang: str, question: str, options: list[str], sources: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """A clarify turn showing only checked text: options found in `sources` that pass meta_ok, and the
        question if it is in the reply language and passes meta_ok (else the fallback). One judge call at
        most. Options are document wording, so they may keep the documents' language."""
        question = question.strip() if in_language(question, lang) else ""
        candidates = documented_options(options, sources)
        items = list(
            dict.fromkeys(
                [*([("framing", question)] if question else []), *(("framing", o) for o in candidates)]
            )
        )
        verdict: dict[MetaItem, bool] = {}
        if items:
            with self._judge(sources) as judge:
                verdict = dict(zip(items, meta_ok(items, judge), strict=True))
        clarify = {
            "question": question if verdict.get(("framing", question)) else msg("clarify_fallback", lang),
            "options": [o for o in candidates if verdict.get(("framing", o))],
        }
        turn = render_turn(
            lang=lang, status="clarify", claims=[], conflicts=[], chunks=self.chunks, clarify=clarify
        )
        return {"type": "final", "turn": turn}

    def _absence(self, lang: str, queries: list[str], retrieval: Any, started: float) -> dict[str, Any]:
        claim = AnswerClaim(text=msg("not_in_documents", lang), kind="absence", evidence=[])
        trace = self._trace(queries, retrieval, 0, 0, started)
        turn = render_turn(
            lang=lang,
            status="not_in_documents",
            claims=[(0, claim)],
            conflicts=[],
            chunks=self.chunks,
            trace=trace,
        )
        return {"type": "final", "turn": turn}

    def _trace(
        self, queries: list[str], retrieval: Any, verified: int, removed: int, started: float
    ) -> dict[str, Any]:
        return {
            "documentsSearched": DOCUMENTS,
            "searches": queries,
            "retrieved": retrieval.chunk_ids,
            "claimsVerified": verified,
            "claimsRemoved": removed,
            "denseFallback": retrieval.dense_fallback,
            "ms": int((time.monotonic() - started) * 1000),
        }

    def _shown_meta(
        self, lang: str, attempt: Attempt, retrieved: dict[str, dict[str, Any]]
    ) -> tuple[list[AnswerConflict], list[str]]:
        """Verified conflicts with a checked topic (else a neutral label) and the missing items that pass."""
        with self._judge(retrieved) as judge:
            ok = attempt.meta.results(judge)
        conflicts = [
            c if ok.get(("framing", c.topic)) else c.model_copy(update={"topic": msg("conflict_topic", lang)})
            for c in attempt.checked.conflicts
        ]
        missing = [m for m in dict.fromkeys(attempt.answer.missing) if ok.get(("absence", m))]
        return conflicts, missing

    def _final(
        self,
        lang: str,
        attempt: Attempt,
        retrieved: dict[str, dict[str, Any]],
        queries: list[str],
        retrieval: Any,
        started: float,
    ) -> Iterator[dict[str, Any]]:
        answer, checked = attempt.answer, attempt.checked
        conflicts: list[AnswerConflict] = []
        missing: list[str] = []
        if answer.status == "not_in_documents" or answer.premise == "absent" or not attempt.evidence:
            status = "not_in_documents"
            kept = [(i, c) for i, c in checked.kept if c.kind == "absence"]  # verified by verify (meta_ok)
            verified = len(kept)
            if not kept:
                kept = [(0, AnswerClaim(text=msg("not_in_documents", lang), kind="absence", evidence=[]))]
        else:
            kept, verified = checked.kept, len(checked.kept)
            status = "partial" if (checked.dropped or answer.status == "partial") else "answered"
            conflicts, missing = self._shown_meta(lang, attempt, retrieved)
            if status == "partial" and not missing:
                missing = [msg("partial_removed" if checked.dropped else "partial_unstated", lang)]
        flags = []
        if conflicts:
            flags.append("conflict")
        if answer.premise == "contradicted" and status != "not_in_documents":
            flags.append("premise_contradicted")
        if any(c.kind == "derived" for _, c in kept):
            flags.append("derived")
        trace = self._trace(queries, retrieval, verified, len(checked.dropped), started)
        turn = render_turn(
            lang=lang,
            status=status,
            claims=kept,
            conflicts=conflicts,
            chunks=self.chunks,
            flags=flags,
            missing=missing,
            trace=trace,
        )
        cited = {c["n"]: c for c in turn["citations"]}
        for claim in turn["claims"]:
            yield {"type": "claim", "claim": claim, "citations": [cited[n] for n in claim["citations"]]}
        yield {"type": "final", "turn": turn}
