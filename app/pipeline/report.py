"""Executive report (ADR D24): one branded report across all three documents, on Claude Opus 5.5.

The report model receives every chunk (the corpus is about 4,000 characters) and places each claim in a
fixed template section. The claims then go through the chat verifier unchanged (J-01, V2-V8): a sentence
that fails is regenerated once with feedback, then removed; conflicts are reported, never resolved.
Citations come from chunk metadata (app.pipeline.render.citation), never from the model.

The corpus is fixed, so a report is generated once per (corpus, template version, model, language) by the
operator (`make report`, a live, paid call) and saved in data/reports/, which ships with the app. The
API only serves saved reports, so the Executive report button never spends anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.llm.client import CassetteMissing, LLMClient, LLMError, LLMResult
from app.llm.schemas import AnswerClaim, AnswerConflict, AnswerOutput, ReportOutput
from app.pipeline import answer as answer_step
from app.pipeline.render import citation
from app.pipeline.verify import Verification, verify

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "data" / "index"
REPORTS = ROOT / "data" / "reports"
REPORT_PROMPT = (answer_step.PROMPTS / "report.md").read_text(encoding="utf-8")
TEMPLATE_VERSION = "exec-v1"
REPORT_MODEL = "claude-opus-5-5"
VERIFIER_MODEL = "claude-sonnet-5-5"

SECTIONS = ["summary", "glance", "budget", "timeline", "team_governance", "disagreements", "risks"]
TITLES = {
    "en": {
        "report": "Executive report: Almamlaka TV Digital Expansion Initiative",
        "summary": "Executive summary",
        "glance": "Project at a glance",
        "budget": "Budget",
        "timeline": "Timeline",
        "team_governance": "Team & governance",
        "disagreements": "Where the documents disagree",
        "risks": "Risks",
    },
    "ar": {
        "report": "التقرير التنفيذي: مبادرة التوسع الرقمي لقناة المملكة",
        "summary": "الملخص التنفيذي",
        "glance": "المشروع في لمحة",
        "budget": "الميزانية",
        "timeline": "الجدول الزمني",
        "team_governance": "الفريق والحوكمة",
        "disagreements": "مواضع اختلاف الوثائق",
        "risks": "المخاطر",
    },
}
EMPTY = {
    "en": "No statement in this section passed verification against the documents.",
    "ar": "لم تجتز أي عبارة في هذا القسم التحقق من الوثائق.",
}


def load_chunks(index_dir: Path = INDEX) -> dict[str, dict[str, Any]]:
    lines = (index_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    return {c["chunk_id"]: c for c in map(json.loads, lines)}


def cache_key(chunks_sha256: str, model: str, lang: str, template: str = TEMPLATE_VERSION) -> str:
    return hashlib.sha256(f"{chunks_sha256}|{template}|{model}|{lang}".encode()).hexdigest()[:16]


def report_path(
    lang: str, model: str = REPORT_MODEL, index_dir: Path = INDEX, reports: Path = REPORTS
) -> Path:
    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    return reports / f"executive-{lang}-{cache_key(manifest['chunks_sha256'], model, lang)}.json"


def load(
    lang: str, model: str = REPORT_MODEL, index_dir: Path = INDEX, reports: Path = REPORTS
) -> dict | None:
    """The saved report for the current corpus, template and model, or None (the UI shows the outline)."""
    path = report_path(lang, model, index_dir, reports)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def report_input(chunks: Iterable[dict[str, Any]], lang: str, feedback: list[str]) -> str:
    parts = [f"<report_language>{lang}</report_language>", answer_step.passages(list(chunks))]
    if feedback:
        notes = "\n".join(f"- {answer_step._escape(f)}" for f in feedback)
        parts.append(
            f"<feedback>\nThese sentences of your previous report failed verification. "
            f"Fix or remove them:\n{notes}\n</feedback>"
        )
    return "\n\n".join(parts)


def conflicts_by_paragraph(report: ReportOutput) -> list[AnswerConflict]:
    """One conflict per paragraph of conflict_position claims, built from the template structure.

    The report prints each disagreement as one paragraph, so the paragraph is the conflict. The model's own
    claim_indexes are not used: an off-by-one index there silently dropped the budget conflict from a real
    Arabic report. V6 still checks every conflict (two documents at least, one document per side).
    """
    groups: dict[tuple[str, int], list[int]] = {}
    for index, claim in enumerate(report.claims):
        if claim.kind == "conflict_position":
            groups.setdefault((claim.section, claim.paragraph), []).append(index)
    return [AnswerConflict(topic="", claim_indexes=sides) for sides in groups.values()]


def _as_answer(report: ReportOutput) -> AnswerOutput:
    claims = [AnswerClaim(text=c.text, kind=c.kind, evidence=c.evidence) for c in report.claims]
    return AnswerOutput(
        status="answered",
        premise="none",
        claims=claims,
        conflicts=conflicts_by_paragraph(report),
        missing=[],
        clarifying_question="",
        clarify_options=[],
    )


def assemble(
    report: ReportOutput, checked: Verification, chunks: dict[str, dict[str, Any]], lang: str, model: str
) -> dict[str, Any]:
    """The ExecutiveReport the UI renders (web/src/components/report/executive-report.tsx)."""
    kept = dict(checked.kept)  # verified claims as verify returned them (framing/absence without evidence)
    numbers: dict[tuple[str, str], int] = {}
    citations: list[dict[str, Any]] = []
    sections = []
    for section in SECTIONS:
        paragraphs: dict[int, dict[str, Any]] = {}
        for index, claim in enumerate(report.claims):
            if index not in kept or claim.section != section:
                continue
            refs = []
            for ev in kept[index].evidence:
                key = (ev.chunk_id, ev.quote)
                if key not in numbers:
                    numbers[key] = len(numbers) + 1
                    citations.append(citation(numbers[key], chunks[ev.chunk_id], ev.quote))
                if numbers[key] not in refs:
                    refs.append(numbers[key])
            para = paragraphs.setdefault(claim.paragraph, {"text": [], "citations": []})
            para["text"].append(claim.text)
            para["citations"] += [n for n in refs if n not in para["citations"]]
        rendered = [
            {"text": " ".join(p["text"]), "citations": p["citations"]} for _, p in sorted(paragraphs.items())
        ]
        sections.append(
            {
                "id": section,
                "title": TITLES[lang][section],
                "paragraphs": rendered or [{"text": EMPTY[lang], "citations": []}],
            }
        )
    return {
        "lang": lang,
        "title": TITLES[lang]["report"],
        "sections": sections,
        "citations": citations,
        "model": model,
        "templateVersion": TEMPLATE_VERSION,
        "claimsVerified": len(checked.kept),
        "claimsRemoved": len(checked.dropped),
    }


def generate(
    client: LLMClient,
    chunks: dict[str, dict[str, Any]],
    lang: str,
    model: str = REPORT_MODEL,
    verifier_model: str = VERIFIER_MODEL,
) -> tuple[dict[str, Any], float]:
    """Write and verify one report; returns it with its cost in USD (0 for cassette replays).

    A failed call (V1: schema, max_tokens, refusal; report or judge) gets the one regeneration too, and a
    failed regeneration keeps the verified first report. Failed calls are billed: an LLMError raised here
    carries everything this report spent in `cost_usd`.
    """
    spent: list[LLMResult] = []
    failed = 0.0
    feedback: list[str] = []
    best: tuple[ReportOutput, Verification] | None = None

    def total() -> float:
        return failed + sum(0.0 if r.from_cassette else r.cost_usd for r in spent)

    for attempt in range(2):
        try:
            draft, checked = _attempt(client, chunks, lang, model, verifier_model, feedback, spent)
        except LLMError as exc:
            failed += 0.0 if exc.from_cassette else exc.cost_usd
            if isinstance(exc, CassetteMissing) or (attempt == 1 and best is None):
                raise LLMError(str(exc), cost_usd=total()) from exc
            if best is not None:
                break  # keep the verified first report
            feedback = [f"Your previous report could not be used ({exc}). Return one complete JSON object."]
            continue
        best = (draft, checked)
        if not checked.dropped and checked.language_ok:
            break
        feedback = [f"{d.reason} (claim: {d.claim.text})" for d in checked.dropped]
        if not checked.language_ok:
            feedback.append(f"Write every claim in the report language '{lang}'.")
    if best is None:
        raise LLMError("no report was produced", cost_usd=total())
    report, checked = best
    if not checked.language_ok:
        raise LLMError("report language check failed after regeneration", cost_usd=total())
    return assemble(report, checked, chunks, lang, model), total()


def _attempt(
    client: LLMClient,
    chunks: dict[str, dict[str, Any]],
    lang: str,
    model: str,
    verifier_model: str,
    feedback: list[str],
    spent: list[LLMResult],
) -> tuple[ReportOutput, Verification]:
    """One report call and its verification; successful calls are appended to `spent`."""
    result = client.call(
        route="report",
        model=model,
        system=REPORT_PROMPT,
        user=report_input(chunks.values(), lang, feedback),
        output=ReportOutput,
        effort="medium",
        max_tokens=16000,
    )
    spent.append(result)
    if not isinstance(result.parsed, ReportOutput):
        raise LLMError("report step returned an unexpected type")
    judge = answer_step.make_judge(client, verifier_model, chunks, spent)
    return result.parsed, verify(_as_answer(result.parsed), chunks, lang, judge)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate and save the executive report (LIVE, paid Opus call)."
    )
    parser.add_argument("--lang", choices=["en", "ar"], required=True)
    parser.add_argument("--model", default=REPORT_MODEL)
    parser.add_argument("--yes", action="store_true", help="confirm the live call (about $0.10-0.20)")
    args = parser.parse_args(argv)
    path = report_path(args.lang, args.model)
    if path.is_file():
        print(f"{path.relative_to(ROOT)} already exists for this corpus, template and model; nothing to do.")
        return 0
    client = LLMClient(timeout_s=300)
    if client.mode != "replay" and not args.yes:
        print(
            f"Dry run: would call {args.model} live. Confirm with: "
            f"make report REPORT_LANG={args.lang} CONFIRM=--yes"
        )
        return 0
    try:
        report, cost = generate(client, load_chunks(), args.lang, args.model)
    except LLMError as exc:
        print(f"report failed: {exc} (${exc.cost_usd:.4f} spent)", file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(
        f"saved {path.relative_to(ROOT)}: {report['claimsVerified']} claims kept, "
        f"{report['claimsRemoved']} removed, ${cost:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
