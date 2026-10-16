"""Verification step 5 (PROJECT_PLAN §4.1): no claim is shown unless it passes every check (non-negotiable 3).

  J-01  fact / derived / conflict_position claims carry at least one piece of evidence
  V2    every cited chunk_id was in this turn's retrieved set
  V3    every quote is in its chunk (app.textnorm.quote_in: one line, whole words and numbers)
  V4    every number, amount, percentage and date in the claim is in its quotes, or, for a derived claim,
        recomputable from them (app.pipeline.numbers); no claim may contain an invisible format character
        (Unicode Cf: bidi overrides and isolates, zero-width characters), which could hide or reorder text
  V8    framing and absence claims pass the meta gate: no facts, no URL, domain or e-mail address, no
        format character
  V5    the support judge (an LLM call, injected as `judge`) says SUPPORTED, in one batch for every claim
        that passed the checks above: evidence claims against their quotes, framing and absence claims
        (sent without evidence) against the framing/absence rules in prompts/verifier.md;
        PARTIAL, UNSUPPORTED and a missing verdict are dropped. A kept framing or absence claim is
        returned without its evidence, so it never shows a citation it was not judged against
  V6    a reported conflict has at least two distinct conflict_position sides, each citing exactly one
        document, no two citing the same one; the sweep repeats until stable, so a conflict that ends
        with fewer than two kept sides is dropped with its surviving sides whatever the order of the
        conflicts, and a kept conflict_position claim outside every valid conflict is dropped as well
  V7    the claims are in the reply language (≥70% of letters in its script; app.lang counts letters only,
        never digits or punctuation; quotes, the three document titles, names in parentheses and amounts
        are excluded, as L-01 specifies)
V1 (schema and stop_reason) is enforced by the LLM client. The orchestrator regenerates once on any drop
or V7 failure, then downgrades (partial / not_in_documents) or errors.
`meta_ok` applies the V8 gate and the V5 judge to free sentences outside an answer (absence or framing).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.lang import arabic_letters, is_letter, latin_letters
from app.llm.schemas import AnswerClaim, AnswerConflict, AnswerOutput
from app.pipeline.numbers import facts, format_chars, supported_by
from app.textnorm import quote_in

EVIDENCE_KINDS = {"fact", "derived", "conflict_position"}
META_KINDS = {"absence", "framing"}
Judge = Callable[[list[tuple[int, AnswerClaim]]], dict[int, str]]

# A URL, a bare domain ("almamlakatv.com", "موقع.كوم") or an e-mail address: a framing or absence sentence
# must not point the reader anywhere. "e.g." and "2.5" don't match (the last label needs two letters).
_LINK = re.compile(r"http|www\.|@|://|(?<![\w-])[\w-]+(?:\.[\w-]+)*\.[^\W\d_]{2,}(?![\w-])", re.IGNORECASE)
# Checked after NFKC (fullwidth letters and dots become ASCII), with the other full stops read as dots:
# ideographic, halfwidth ideographic and Arabic.
_DOTS = str.maketrans({"\u3002": ".", "\uff61": ".", "\u06d4": "."})
# What L-01 excludes from the letter count: quoted wording and the three document titles. Straight single
# quotes count only outside words, so the apostrophes in "don't" and "vendor's" are not quotes.
_QUOTED = re.compile(
    r'"[^"]*"'
    r"|[\u201c\u201d\u201e][^\u201c\u201d\u201e]*[\u201c\u201d]"
    r"|\u00ab[^\u00bb]*\u00bb"
    r"|\u2018[^\u2018\u2019]*\u2019"
    r"|(?<!\w)'[^']*'(?!\w)"
)
_TITLES = re.compile(
    r"project\s+overview\s+document|budget\s*(?:&|and)\s*timeline\s+breakdown|team\s*(?:&|and)\s*governance"
    r"\s+document",
    re.IGNORECASE,
)


@dataclass
class Dropped:
    index: int
    claim: AnswerClaim
    reason: str


@dataclass
class Verification:
    kept: list[tuple[int, AnswerClaim]]
    dropped: list[Dropped] = field(default_factory=list)
    conflicts: list[AnswerConflict] = field(default_factory=list)
    language_ok: bool = True


def _doc(chunk_id: str) -> str:
    return chunk_id.split("-")[0]


def meta_problem(text: str) -> str:
    """Why a framing or absence sentence fails the deterministic gate (V8), or "" if it passes."""
    found = facts(text)
    if found:
        return "carries facts: " + ", ".join(sorted(f.text for f in found))
    link = _LINK.search(unicodedata.normalize("NFKC", text).translate(_DOTS))
    if link:
        return f"contains a link or address: {link.group(0)}"
    hidden = format_chars(text)
    if hidden:
        return "contains invisible format characters: " + ", ".join(hidden)
    return ""


def structural_problem(claim: AnswerClaim, retrieved: dict[str, dict[str, Any]]) -> str:
    """The first deterministic check (J-01, V2, V3, V4, V8) this claim fails, or "" if none."""
    if claim.kind in META_KINDS:
        problem = meta_problem(claim.text)
        if problem:
            return f"V8: {claim.kind} claim {problem}"
    else:
        hidden = format_chars(claim.text)
        if hidden:
            return "V4: claim contains invisible format characters: " + ", ".join(hidden)
    if claim.kind in EVIDENCE_KINDS and not claim.evidence:
        return "J-01: claim has no evidence"
    for ev in claim.evidence:
        if ev.chunk_id not in retrieved:
            return f"V2: chunk {ev.chunk_id} was not retrieved this turn"
        if not quote_in(ev.quote, retrieved[ev.chunk_id]["text"]):
            return f"V3: quote not found in {ev.chunk_id}"
    if claim.kind in EVIDENCE_KINDS:
        missing = supported_by(
            claim.text, [ev.quote for ev in claim.evidence], derived=claim.kind == "derived"
        )
        if missing:
            return "V4: not in the quotes: " + ", ".join(f.text for f in missing)
    return ""


def _for_judge(claim: AnswerClaim) -> AnswerClaim:
    """Framing and absence claims are judged on their wording alone (verifier.md rules), never on evidence."""
    if claim.kind in META_KINDS:
        return AnswerClaim(text=claim.text, kind=claim.kind, evidence=[])
    return claim


def meta_ok(items: list[tuple[str, str]], judge: Judge) -> list[bool]:
    """V8 then V5 for free (kind, text) sentences, kind "absence" or "framing"; one bool per item.

    The deterministic gate (`meta_problem`) runs first; the items that pass go to the support judge in
    one batch, numbered 0..n-1, and are True only if it says SUPPORTED. No item passes: no judge call.
    """
    for kind, _ in items:
        if kind not in META_KINDS:
            raise ValueError(f"meta_ok takes absence or framing items, not {kind!r}")
    passed = [n for n, (_, text) in enumerate(items) if not meta_problem(text)]
    if not passed:
        return [False] * len(items)
    batch = [
        (fresh, AnswerClaim(text=items[n][1], kind=items[n][0], evidence=[]))  # type: ignore[arg-type]
        for fresh, n in enumerate(passed)
    ]
    verdicts = judge(batch)
    ok = [False] * len(items)
    for fresh, n in enumerate(passed):
        ok[n] = verdicts.get(fresh) == "SUPPORTED"
    return ok


def language_ok(claims: list[AnswerClaim], reply_lang: str) -> bool:
    """V7: at least 70% of the letters are in the reply language's script (L-01).

    Quoted wording, the three document titles, names in parentheses and amounts are removed first, and only
    letters count (app.lang), so Arabic-Indic digits and Arabic punctuation never tip the balance.
    """
    text = " ".join(c.text for c in claims)
    text = _QUOTED.sub(" ", text)
    text = _TITLES.sub(" ", text)
    text = re.sub(r"\([^)]*\)|\$\s*[\d,.]+", " ", text)  # names in parentheses, amounts
    letters = sum(1 for ch in text if is_letter(ch))
    if not letters:
        return True
    expected = arabic_letters(text) if reply_lang == "ar" else latin_letters(text)
    return expected / letters >= 0.7


def _conflict_problem(sides: list[int], claims: list[AnswerClaim]) -> str:
    """Why a conflict's (distinct, in-range) sides can't form a cross-document conflict, or "" if they can."""
    if len(sides) < 2:
        return "conflict has fewer than two distinct sides"
    if any(claims[i].kind != "conflict_position" for i in sides):
        return "a conflict side is not a conflict_position claim"
    docs = [{_doc(ev.chunk_id) for ev in claims[i].evidence} for i in sides]
    if any(len(d) != 1 for d in docs):
        return "a conflict side must cite exactly one document"
    if len({next(iter(d)) for d in docs}) < 2:
        return ONE_DOCUMENT
    return ""


ONE_DOCUMENT = "conflict sides cite only one document"


def _single_documents(sides: list[int], claims: list[AnswerClaim]) -> list[str] | None:
    """The one document each side cites, or None if some side cites none or several."""
    docs = [{_doc(ev.chunk_id) for ev in claims[i].evidence} for i in sides]
    return None if any(len(d) != 1 for d in docs) else [next(iter(d)) for d in docs]


def _sweep_conflicts(answer: AnswerOutput, result: Verification) -> None:
    """V6: keep only conflicts whose kept sides span ≥2 documents, repeating until stable.

    Dropping a side of one conflict can break another that shares it, so the check repeats over the final
    kept set until nothing changes; the outcome doesn't depend on the order of the conflicts. A conflict that
    loses a side loses all of it, so no disagreement is ever shown one-sided.
    Two cases keep verified claims instead of dropping them:
      * a reported conflict whose sides all cite ONE document and share no side with another conflict is a
        document reporting its own revision ("originally $2,400,000, adjusted to $2,600,000"): kept as facts;
      * `conflict_position` claims the model left out of `conflicts` become one reported conflict when they
        span ≥2 documents (topic filled in by the caller), facts when ≥2 of them cite one document, and are
        dropped when a lone side remains.
    """
    claims = answer.claims
    kept_ids = {i for i, _ in result.kept}
    demote: set[int] = set()

    def drop(i: int, reason: str) -> None:
        if i in kept_ids:
            kept_ids.discard(i)
            result.dropped.append(Dropped(i, claims[i], f"V6: {reason}"))

    groups = [
        list(dict.fromkeys(i for i in c.claim_indexes if 0 <= i < len(claims))) for c in answer.conflicts
    ]
    shared = {
        i for n, g in enumerate(groups) for i in g if any(i in h for m, h in enumerate(groups) if m != n)
    }
    candidates: list[tuple[AnswerConflict, list[int]]] = []
    for conflict, sides in zip(answer.conflicts, groups, strict=True):
        problem = _conflict_problem(sides, claims)
        if problem == ONE_DOCUMENT and not shared.intersection(sides):
            demote.update(sides)
        elif problem:
            for i in sides:
                drop(i, problem)
        else:
            candidates.append((conflict, sides))

    changed = True
    while changed:
        changed = False
        for _, sides in candidates:
            alive = [i for i in sides if i in kept_ids]
            if alive and _conflict_problem(alive, claims):
                for i in alive:
                    drop(i, "conflict lost a side, so it is not a two-sided cross-document conflict")
                changed = True

    for conflict, sides in candidates:
        alive = [i for i in sides if i in kept_ids]
        if alive:
            result.conflicts.append(AnswerConflict(topic=conflict.topic, claim_indexes=alive))
    in_conflict = {i for c in result.conflicts for i in c.claim_indexes} | demote
    orphans = [
        i for i, c in result.kept if c.kind == "conflict_position" and i in kept_ids and i not in in_conflict
    ]
    docs = _single_documents(orphans, claims) if orphans else None
    if docs is not None and len(set(docs)) >= 2:
        result.conflicts.append(AnswerConflict(topic="", claim_indexes=orphans))
    elif docs is not None and len(orphans) >= 2:
        demote.update(orphans)
    else:
        for i in orphans:
            drop(i, "conflict_position claim is not part of a reported conflict")
    result.kept = [
        (i, c.model_copy(update={"kind": "fact"}) if i in demote else c)
        for i, c in result.kept
        if i in kept_ids
    ]


def verify(
    answer: AnswerOutput, retrieved: dict[str, dict[str, Any]], reply_lang: str, judge: Judge
) -> Verification:
    result = Verification(kept=[])
    for index, claim in enumerate(answer.claims):
        problem = structural_problem(claim, retrieved)
        if problem:
            result.dropped.append(Dropped(index, claim, problem))
        else:
            result.kept.append((index, claim))

    if result.kept:
        verdicts = judge([(i, _for_judge(c)) for i, c in result.kept])
        survivors = []
        for index, claim in result.kept:
            verdict = verdicts.get(index, "UNSUPPORTED")
            if verdict == "SUPPORTED":
                survivors.append((index, _for_judge(claim)))  # what was judged is what is shown
            else:
                result.dropped.append(Dropped(index, claim, f"V5: support judge said {verdict}"))
        result.kept = survivors

    _sweep_conflicts(answer, result)
    result.dropped.sort(key=lambda d: d.index)
    result.language_ok = language_ok([c for _, c in result.kept], reply_lang)
    return result
