"""Verifier V2-V8 (written test-first). The support judge (V5) is a plain callable here, so these
tests need no model. Cases follow ACCEPTANCE J-01..J-06 and the §4.1 V-list."""

from __future__ import annotations

import json
import re
from itertools import permutations
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.llm.client import LLMClient, LLMResult
from app.llm.schemas import AnswerClaim, AnswerConflict, AnswerOutput, Evidence
from app.pipeline.answer import make_judge
from app.pipeline.verify import language_ok, meta_ok, verify

ROOT = Path(__file__).resolve().parents[2]
CHUNKS = {
    c["chunk_id"]: c
    for c in map(json.loads, (ROOT / "data/index/chunks.jsonl").read_text("utf-8").splitlines())
}
RETRIEVED = {cid: CHUNKS[cid] for cid in ("OVR-p1-s3", "BUD-p1-s2", "BUD-p1-s1", "GOV-p1-s3")}

OVR_BUDGET = Evidence(chunk_id="OVR-p1-s3", quote="Total Approved Budget: $2,400,000")
BUD_BUDGET = Evidence(chunk_id="BUD-p1-s2", quote="the total project budget was adjusted to $2,600,000")
GOV_LAUNCH = Evidence(chunk_id="GOV-p1-s3", quote="the public launch date was moved to April 1, 2027")
BUD_REVISION = Evidence(
    chunk_id="BUD-p1-s2", quote="Following a revision by the Finance Committee in December 2026"
)


def answer(
    *claims: AnswerClaim, conflicts: list[AnswerConflict] | None = None, status: str = "answered"
) -> AnswerOutput:
    return AnswerOutput(
        status=status,  # type: ignore[arg-type]
        premise="none",
        claims=list(claims),
        conflicts=conflicts or [],
        missing=[],
        clarifying_question="",
        clarify_options=[],
    )


def all_supported(claims: list[tuple[int, AnswerClaim]]) -> dict[int, str]:
    return {i: "SUPPORTED" for i, _ in claims}


def fact(text: str, *evidence: Evidence, kind: str = "fact") -> AnswerClaim:
    return AnswerClaim(text=text, kind=kind, evidence=list(evidence))  # type: ignore[arg-type]


def test_a_faithful_claim_is_kept() -> None:
    result = verify(
        answer(fact("The Overview states a total approved budget of $2,400,000.", OVR_BUDGET)),
        RETRIEVED,
        "en",
        all_supported,
    )
    assert [c.text for _, c in result.kept] == ["The Overview states a total approved budget of $2,400,000."]
    assert result.dropped == []


def test_j06_chunk_not_in_the_retrieved_set_is_dropped() -> None:
    ghost = Evidence(chunk_id="OVR-p7-s1", quote="Total Approved Budget: $2,400,000")
    result = verify(answer(fact("Budget is $2,400,000.", ghost)), RETRIEVED, "en", all_supported)
    assert result.kept == [] and "V2" in result.dropped[0].reason


def test_j06_quote_not_in_the_chunk_is_dropped() -> None:
    fake = Evidence(chunk_id="OVR-p1-s3", quote="Total Approved Budget: $5,000,000")
    result = verify(answer(fact("Budget is $5,000,000.", fake)), RETRIEVED, "en", all_supported)
    assert result.kept == [] and "V3" in result.dropped[0].reason


def test_v4_number_not_in_the_quotes_is_dropped() -> None:
    result = verify(answer(fact("The budget is $2,500,000.", OVR_BUDGET)), RETRIEVED, "en", all_supported)
    assert result.kept == [] and "V4" in result.dropped[0].reason


def test_v4_derived_claim_is_recomputed() -> None:
    claim = fact("The total changed by $200,000.", OVR_BUDGET, BUD_BUDGET, kind="derived")
    assert verify(answer(claim), RETRIEVED, "en", all_supported).kept
    wrong = fact("The total changed by $300,000.", OVR_BUDGET, BUD_BUDGET, kind="derived")
    assert not verify(answer(wrong), RETRIEVED, "en", all_supported).kept


def test_j05_real_chunk_that_does_not_support_the_claim_is_dropped() -> None:
    # "launch is April 1, 2027" citing OVR-p1-s3: V2-V4 can pass only with a date from the quote, so the
    # model cites the OVR chunk with an unrelated quote; the support judge says UNSUPPORTED.
    claim = fact(
        "The launch is on March 15, 2027.",
        Evidence(chunk_id="OVR-p1-s3", quote="Planned Launch Date: March 15, 2027"),
    )
    judge = lambda claims: {i: "UNSUPPORTED" for i, _ in claims}  # noqa: E731
    result = verify(answer(claim), RETRIEVED, "en", judge)
    assert result.kept == [] and "V5" in result.dropped[0].reason


def test_v5_partial_support_is_not_shown() -> None:
    claim = fact("The budget is $2,400,000.", OVR_BUDGET)
    result = verify(answer(claim), RETRIEVED, "en", lambda claims: {i: "PARTIAL" for i, _ in claims})
    assert result.kept == []


def test_j01_fact_without_evidence_is_dropped() -> None:
    result = verify(answer(fact("The budget is large.")), RETRIEVED, "en", all_supported)
    assert result.kept == [] and "J-01" in result.dropped[0].reason


def test_v8_framing_and_absence_claims_carry_no_facts() -> None:
    ok = AnswerClaim(text="The documents don't name the vendor.", kind="absence", evidence=[])
    sneaky = AnswerClaim(text="In short, the budget is $9,999,999.", kind="framing", evidence=[])
    result = verify(answer(ok, sneaky), RETRIEVED, "en", all_supported)
    assert [c.kind for _, c in result.kept] == ["absence"]
    assert "V8" in result.dropped[0].reason


def test_v5_framing_goes_to_the_judge_in_the_same_batch_without_evidence() -> None:
    # Behaviour change (review finding 1): framing and absence claims used to bypass the support judge.
    batches: list[list[tuple[int, AnswerClaim]]] = []

    def judge(claims: list[tuple[int, AnswerClaim]]) -> dict[int, str]:
        batches.append(claims)
        return {i: "SUPPORTED" for i, _ in claims}

    framing = AnswerClaim(text="Here is what the documents say.", kind="framing", evidence=[OVR_BUDGET])
    result = verify(answer(framing, fact("x $2,400,000", OVR_BUDGET)), RETRIEVED, "en", judge)
    assert [[i for i, _ in b] for b in batches] == [[0, 1]]
    assert batches[0][0][1].evidence == [] and batches[0][1][1].evidence == [OVR_BUDGET]
    # What was judged is what is kept: the framing claim is shown without the citation it carried.
    assert [c.evidence for _, c in result.kept] == [[], [OVR_BUDGET]]


def test_v6_conflict_needs_both_sides_from_different_documents() -> None:
    c1 = fact("The Overview states $2,400,000.", OVR_BUDGET, kind="conflict_position")
    c2 = fact("The Budget notes state $2,600,000.", BUD_BUDGET, kind="conflict_position")
    both = verify(
        answer(c1, c2, conflicts=[AnswerConflict(topic="Total budget", claim_indexes=[0, 1])]),
        RETRIEVED,
        "en",
        all_supported,
    )
    assert len(both.conflicts) == 1

    # One side fails verification: a one-sided "conflict" must not be shown, and neither may its survivor
    # pretend to be the whole story; the remaining position is dropped too.
    judge = lambda claims: {i: ("UNSUPPORTED" if i == 1 else "SUPPORTED") for i, _ in claims}  # noqa: E731
    one = verify(
        answer(c1, c2, conflicts=[AnswerConflict(topic="Total budget", claim_indexes=[0, 1])]),
        RETRIEVED,
        "en",
        judge,
    )
    assert one.conflicts == [] and one.kept == []
    assert any("V6" in d.reason for d in one.dropped)


def test_v6_conflict_sides_from_the_same_document_are_not_a_cross_document_conflict() -> None:
    a = fact("A says $2,400,000.", OVR_BUDGET, kind="conflict_position")
    b = fact("A also says $2,400,000.", OVR_BUDGET, kind="conflict_position")
    result = verify(
        answer(a, b, conflicts=[AnswerConflict(topic="x", claim_indexes=[0, 1])]),
        RETRIEVED,
        "en",
        all_supported,
    )
    assert result.conflicts == []


@pytest.mark.parametrize(
    ("text", "lang", "ok"),
    [
        ("تذكر وثيقة نظرة عامة أن الميزانية هي $2,400,000.", "ar", True),
        ("قائدة المشروع هي سارة الرشيد (Sara Al-Rashid).", "ar", True),  # Latin name allowed
        ("The total approved budget is $2,400,000.", "ar", False),
        ("The total approved budget is $2,400,000.", "en", True),
        ("الميزانية الإجمالية هي $2,400,000.", "en", False),
    ],
)
def test_v7_reply_language(text: str, lang: str, ok: bool) -> None:
    assert language_ok([fact(text, OVR_BUDGET)], lang) is ok  # type: ignore[arg-type]


def test_v7_failure_is_reported_for_regeneration() -> None:
    result = verify(
        answer(fact("The total approved budget is $2,400,000.", OVR_BUDGET)), RETRIEVED, "ar", all_supported
    )
    assert result.language_ok is False


# ---- review findings 2026-10-16 ------------------------------------------------------------------------


def judge_saying(verdicts: dict[int, str]) -> Any:
    """A scripted judge: the given verdicts, SUPPORTED for every other index it is sent."""
    return lambda claims: {i: verdicts.get(i, "SUPPORTED") for i, _ in claims}


def meta(text: str, kind: str = "framing") -> AnswerClaim:
    return AnswerClaim(text=text, kind=kind, evidence=[])  # type: ignore[arg-type]


def position(text: str, *evidence: Evidence) -> AnswerClaim:
    return fact(text, *evidence, kind="conflict_position")


def dropped_reasons(result: Any) -> dict[int, str]:
    return {d.index: d.reason for d in result.dropped}


# Finding 1: framing and absence claims pass the meta gate and the support judge.


def test_v5_framing_or_absence_the_judge_rejects_is_dropped() -> None:
    claims = (
        meta("The documents don't name the vendor, which was chosen in May.", "absence"),
        meta("The project is on track."),
        fact("The Overview states a total approved budget of $2,400,000.", OVR_BUDGET),
    )
    result = verify(answer(*claims), RETRIEVED, "en", judge_saying({0: "UNSUPPORTED", 1: "PARTIAL"}))
    assert [i for i, _ in result.kept] == [2]
    assert dropped_reasons(result) == {
        0: "V5: support judge said UNSUPPORTED",
        1: "V5: support judge said PARTIAL",
    }


@pytest.mark.parametrize(
    "text",
    [
        "See almamlakatv.com for details.",
        "More at https://example.org/budget.",
        "Visit www.example for details.",
        "Write to press@example for details.",
        "راجع الموقع almamlakatv.com للتفاصيل.",
        "Details at ftp://files.example for the rest.",  # any scheme, not only http
        "See \uff57\uff57\uff57\uff0eexample\uff0e\uff43\uff4f\uff4d now.",  # fullwidth letters and dots
        "See example\u3002com now.",  # ideographic full stop
        "راجع الموقع المملكة\u06d4كوم للتفاصيل.",  # Arabic full stop
        "The documents don\u202et name the vendor.",  # right-to-left override
        "The documents don't name the\u200b vendor.",  # zero-width space
        "The documents don't name the vendor\u2066.",  # left-to-right isolate
    ],
)
def test_v8_framing_and_absence_with_links_or_format_characters_are_dropped(text: str) -> None:
    seen: list[int] = []

    def judge(claims: list[tuple[int, AnswerClaim]]) -> dict[int, str]:
        seen.extend(i for i, _ in claims)
        return {i: "SUPPORTED" for i, _ in claims}

    for kind in ("absence", "framing"):
        result = verify(answer(meta(text, kind)), RETRIEVED, "en", judge)
        assert result.kept == [] and result.dropped[0].reason.startswith("V8")
    assert seen == []  # nothing passed the gate, so the judge was never called


@pytest.mark.parametrize("char", ["\u202e", "\u2067", "\u200b", "\u200d", "\u200e", "\ufeff"])
def test_v4_evidence_claim_with_a_format_character_is_dropped(char: str) -> None:
    claim = fact(f"The Overview states a total {char}approved budget of $2,400,000.", OVR_BUDGET)
    result = verify(answer(claim), RETRIEVED, "en", all_supported)
    assert result.kept == []
    assert result.dropped[0].reason.startswith("V4") and "U+" in result.dropped[0].reason


def test_meta_ok_gates_then_judges_the_rest_in_one_batch_with_fresh_indexes() -> None:
    batches: list[list[tuple[int, AnswerClaim]]] = []

    def judge(claims: list[tuple[int, AnswerClaim]]) -> dict[int, str]:
        batches.append(claims)
        return {0: "SUPPORTED", 1: "UNSUPPORTED", 2: "SUPPORTED"}

    items = [
        ("absence", "The documents don't name the vendor."),
        ("framing", "The budget is $9,000,000."),  # a fact: gated
        ("framing", "The project is on track."),  # judged UNSUPPORTED
        ("framing", "See almamlakatv.com."),  # a domain: gated
        ("framing", "Here is what the documents say, e.g. about the budget."),
        ("absence", "The documents don't name the\u202e vendor."),  # a format character: gated
    ]
    assert meta_ok(items, judge) == [True, False, False, False, True, False]
    assert len(batches) == 1
    assert [(i, c.kind, c.text, c.evidence) for i, c in batches[0]] == [
        (0, "absence", items[0][1], []),
        (1, "framing", items[2][1], []),
        (2, "framing", items[4][1], []),
    ]


def test_meta_ok_skips_the_judge_when_nothing_passes_the_gate() -> None:
    def judge(claims: list[tuple[int, AnswerClaim]]) -> dict[int, str]:
        raise AssertionError("the judge must not be called")

    items = [("absence", "The launch is on March 15, 2027."), ("framing", "www.x")]
    assert meta_ok(items, judge) == [False, False]
    assert meta_ok([], judge) == []


def test_meta_ok_counts_a_missing_or_odd_verdict_as_failed() -> None:
    items = [("framing", "Here is the answer."), ("absence", "The documents don't say.")]
    assert meta_ok(items, lambda claims: {0: "SUPPORTED"}) == [True, False]
    assert meta_ok(items, lambda claims: {0: "supported", 1: "PARTIAL"}) == [False, False]


def test_meta_ok_rejects_evidence_kinds() -> None:
    with pytest.raises(ValueError, match="absence or framing"):
        meta_ok([("fact", "The budget is large.")], all_supported)


# Findings 2 and 3: the V6 conflict sweep.

OVR_SIDE = position("The Overview states $2,400,000.", OVR_BUDGET)
BUD_SIDE = position("The Budget notes state $2,600,000.", BUD_BUDGET)
BUD_SIDE_2 = position("The Budget notes mention a revision in December 2026.", BUD_REVISION)
GOV_SIDE = position("The Governance document moved the launch to April 1, 2027.", GOV_LAUNCH)


def test_v6_duplicate_sides_are_one_side() -> None:
    result = verify(
        answer(OVR_SIDE, BUD_SIDE, conflicts=[AnswerConflict(topic="x", claim_indexes=[0, 0])]),
        RETRIEVED,
        "en",
        all_supported,
    )
    assert result.conflicts == [] and result.kept == []
    assert all(r.startswith("V6") for r in dropped_reasons(result).values())


def test_v6_each_side_cites_exactly_one_document() -> None:
    # The old union-of-documents test let one two-document side plus any other side pass.
    both = position("The documents state $2,400,000 and $2,600,000.", OVR_BUDGET, BUD_BUDGET)
    result = verify(
        answer(both, BUD_SIDE, conflicts=[AnswerConflict(topic="x", claim_indexes=[0, 1])]),
        RETRIEVED,
        "en",
        all_supported,
    )
    assert result.conflicts == [] and result.kept == []
    assert "exactly one document" in result.dropped[0].reason


def test_v6_one_document_may_add_a_second_position_when_two_documents_disagree() -> None:
    conflict = AnswerConflict(topic="x", claim_indexes=[0, 1, 2])
    result = verify(
        answer(OVR_SIDE, BUD_SIDE, BUD_SIDE_2, conflicts=[conflict]), RETRIEVED, "en", all_supported
    )
    assert [c.claim_indexes for c in result.conflicts] == [[0, 1, 2]] and len(result.kept) == 3


def test_v6_sides_from_one_document_are_not_a_conflict_but_stay_as_facts() -> None:
    # A document reporting its own revision is not a cross-document conflict; its verified claims are kept.
    conflict = AnswerConflict(topic="x", claim_indexes=[0, 1])
    result = verify(answer(BUD_SIDE, BUD_SIDE_2, conflicts=[conflict]), RETRIEVED, "en", all_supported)
    assert result.conflicts == [] and result.dropped == []
    assert [(i, c.kind) for i, c in result.kept] == [(0, "fact"), (1, "fact")]


def test_v6_a_conflict_keeps_its_surviving_sides_when_two_or_more_remain() -> None:
    conflict = AnswerConflict(topic="x", claim_indexes=[0, 1, 2, 9])  # 9 is out of range
    result = verify(
        answer(OVR_SIDE, BUD_SIDE, GOV_SIDE, conflicts=[conflict]),
        RETRIEVED,
        "en",
        judge_saying({2: "UNSUPPORTED"}),
    )
    assert result.conflicts == [AnswerConflict(topic="x", claim_indexes=[0, 1])]
    assert [i for i, _ in result.kept] == [0, 1]


CONFLICT_A = AnswerConflict(topic="A", claim_indexes=[0, 1])  # OVR vs BUD: valid on its own
CONFLICT_B = AnswerConflict(topic="B", claim_indexes=[1, 2])  # BUD vs BUD: invalid, so side 1 is dropped
CONFLICT_D = AnswerConflict(topic="D", claim_indexes=[0, 3])  # OVR vs GOV: breaks once A drops side 0


@pytest.mark.parametrize("order", list(permutations([CONFLICT_A, CONFLICT_B, CONFLICT_D])))
def test_v6_sweep_repeats_until_stable_in_any_conflict_order(order: tuple[AnswerConflict, ...]) -> None:
    result = verify(
        answer(OVR_SIDE, BUD_SIDE, BUD_SIDE_2, GOV_SIDE, conflicts=list(order)),
        RETRIEVED,
        "en",
        all_supported,
    )
    assert result.conflicts == [] and result.kept == []
    reasons = dropped_reasons(result)
    assert sorted(reasons) == [0, 1, 2, 3] and all(r.startswith("V6") for r in reasons.values())


@pytest.mark.parametrize("order", [[CONFLICT_A, CONFLICT_D], [CONFLICT_D, CONFLICT_A]])
def test_v6_two_overlapping_conflicts_lose_a_shared_side_in_either_order(order: list[AnswerConflict]) -> None:
    result = verify(
        answer(OVR_SIDE, BUD_SIDE, BUD_SIDE_2, GOV_SIDE, conflicts=order),
        RETRIEVED,
        "en",
        judge_saying({0: "UNSUPPORTED"}),
    )
    assert result.conflicts == [] and result.kept == []
    reasons = dropped_reasons(result)
    assert reasons[0].startswith("V5") and all(reasons[i].startswith("V6") for i in (1, 2, 3))


@pytest.mark.parametrize("order", [[CONFLICT_A, CONFLICT_D], [CONFLICT_D, CONFLICT_A]])
def test_v6_two_valid_overlapping_conflicts_are_both_kept(order: list[AnswerConflict]) -> None:
    claims = (OVR_SIDE, BUD_SIDE, fact("Budget: $2,400,000.", OVR_BUDGET), GOV_SIDE)
    result = verify(answer(*claims, conflicts=order), RETRIEVED, "en", all_supported)
    assert sorted(c.topic for c in result.conflicts) == ["A", "D"] and result.dropped == []


def test_v6_orphan_conflict_position_is_dropped() -> None:
    result = verify(
        answer(OVR_SIDE, fact("The Overview states a total approved budget of $2,400,000.", OVR_BUDGET)),
        RETRIEVED,
        "en",
        all_supported,
    )
    assert [i for i, _ in result.kept] == [1]
    assert dropped_reasons(result) == {0: "V6: conflict_position claim is not part of a reported conflict"}


def test_v6_orphan_positions_from_two_documents_become_a_flagged_conflict() -> None:
    result = verify(answer(OVR_SIDE, BUD_SIDE), RETRIEVED, "en", all_supported)
    assert [c.claim_indexes for c in result.conflicts] == [[0, 1]] and result.dropped == []


def test_v6_orphan_positions_from_one_document_stay_as_facts() -> None:
    result = verify(answer(BUD_SIDE, BUD_SIDE_2), RETRIEVED, "en", all_supported)
    assert result.conflicts == [] and [c.kind for _, c in result.kept] == ["fact", "fact"]


# Finding 4: the judge's output is validated fail-closed.


class JudgeSDK:
    """Returns the scripted judgments, whatever claims it is sent."""

    def __init__(self, judgments: list[tuple[int, str]]) -> None:
        self.judgments = judgments
        self.sent: list[int] = []
        self.messages = self

    def create(self, **body: Any) -> SimpleNamespace:
        self.sent = [int(i) for i in re.findall(r'<claim index="(\d+)"', body["messages"][0]["content"])]
        payload = {"judgments": [{"claim_index": i, "verdict": v, "reason": "x"} for i, v in self.judgments]}
        return SimpleNamespace(
            model="claude-sonnet-5-5",
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(payload))],
            usage=SimpleNamespace(to_dict=lambda: {"input_tokens": 10, "output_tokens": 10}),
        )


def run_judge(judgments: list[tuple[int, str]], indexes: list[int]) -> dict[int, str]:
    sdk = JudgeSDK(judgments)
    costs: list[LLMResult] = []
    judge = make_judge(LLMClient(mode="live", sdk=sdk), "claude-sonnet-5-5", RETRIEVED, costs)
    verdicts = judge([(i, fact("The budget is $2,400,000.", OVR_BUDGET)) for i in indexes])
    assert sdk.sent == indexes and len(costs) == 1
    return verdicts


def test_judge_omitted_index_is_unsupported() -> None:
    assert run_judge([(3, "SUPPORTED")], [3, 5]) == {3: "SUPPORTED", 5: "UNSUPPORTED"}
    assert run_judge([], [0]) == {0: "UNSUPPORTED"}


@pytest.mark.parametrize(
    ("repeats", "expected"),
    [
        (["SUPPORTED", "SUPPORTED"], "SUPPORTED"),
        (["SUPPORTED", "PARTIAL"], "PARTIAL"),
        (["PARTIAL", "SUPPORTED"], "PARTIAL"),
        (["UNSUPPORTED", "SUPPORTED"], "UNSUPPORTED"),
        (["SUPPORTED", "PARTIAL", "UNSUPPORTED", "SUPPORTED"], "UNSUPPORTED"),
    ],
)
def test_judge_repeated_index_keeps_the_most_severe_verdict(repeats: list[str], expected: str) -> None:
    assert run_judge([(0, v) for v in repeats], [0]) == {0: expected}


def test_judge_extra_indexes_are_ignored() -> None:
    assert run_judge([(0, "SUPPORTED"), (1, "SUPPORTED"), (-1, "SUPPORTED")], [0]) == {0: "SUPPORTED"}


def test_verify_drops_a_claim_the_judge_skips() -> None:
    claims = (
        fact("The Overview states a total approved budget of $2,400,000.", OVR_BUDGET),
        meta("Here is what the documents say."),
    )
    result = verify(answer(*claims), RETRIEVED, "en", lambda claims: {})
    assert result.kept == [] and all(d.reason == "V5: support judge said UNSUPPORTED" for d in result.dropped)


# Findings 8 and 9: V7 counts letters only, without quoted wording or the document titles.


@pytest.mark.parametrize(
    ("text", "lang", "ok"),
    [
        ('تقول الوثيقة حرفياً "Total Approved Budget" وهي $2,400,000.', "ar", True),
        ("تقول الوثيقة حرفياً “the total project budget was adjusted” إلى $2,600,000.", "ar", True),
        ("تقول الوثيقة «the public launch date was moved» إلى موعد جديد.", "ar", True),
        ("تقول الوثيقة 'the public launch date was moved to a later date' فقط.", "ar", True),
        ("تذكر وثيقة Budget & Timeline Breakdown أن الميزانية عُدّلت.", "ar", True),
        ("تذكر وثيقتا Project Overview Document و Team & Governance Document موعدين.", "ar", True),
        ('The Arabic summary says "تم تعديل الميزانية الإجمالية للمشروع" in the notes.', "en", True),
        ("The Arabic summary says «تم تعديل الميزانية الإجمالية للمشروع» in the notes.", "en", True),
        ("The Arabic summary says 'تم تعديل الميزانية الإجمالية للمشروع' in the notes.", "en", True),
        # Unquoted wording still counts, and an apostrophe inside a word is not a quote mark.
        (
            "The documents don't name the vendor's CMS والميزانية الإجمالية للمشروع غير مذكورة هنا",
            "en",
            False,
        ),
        ("تقول الوثيقة Total Approved Budget وهي $2,400,000.", "ar", False),
    ],
)
def test_v7_quoted_wording_and_titles_are_excluded(text: str, lang: str, ok: bool) -> None:
    assert language_ok([fact(text, OVR_BUDGET)], lang) is ok


@pytest.mark.parametrize(
    ("text", "lang", "ok"),
    [
        # Arabic-Indic digits and Arabic punctuation are not letters, so they can't make English look Arabic.
        ("The budget in ٢٠٢٧ was ٢٬٤٠٠٬٠٠٠، ٢٬٦٠٠٬٠٠٠؛ ٤٠٪ ١٢٣٤٥٦٧٨٩ ۱۲۳۴۵۶۷۸۹؟", "en", True),  # noqa: RUF001
        ("ok ٢٠٢٧٢٠٢٧٢٠٢٧ ،،،؛؛؛", "ar", False),
        # Letters of a third script count against the reply language.
        ("Бюджет проекта был увеличен в декабре.", "en", False),
        ("ــــــــ budget", "ar", False),  # tatweel is not a letter
    ],
)
def test_v7_counts_only_letters(text: str, lang: str, ok: bool) -> None:
    assert language_ok([fact(text, OVR_BUDGET)], lang) is ok
