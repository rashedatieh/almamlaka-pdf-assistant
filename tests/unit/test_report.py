"""Executive report (ADR D24): template assembly, verification, regeneration and the operator cache."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.llm.client import LLMClient, LLMError
from app.pipeline import report
from app.prices import cost_usd

CHUNKS = report.load_chunks()
OVR = {"chunk_id": "OVR-p1-s3", "quote": "Total Approved Budget: $2,400,000"}
BUD = {"chunk_id": "BUD-p1-s2", "quote": "the total project budget was adjusted to $2,600,000"}


def rc(
    section: str, paragraph: int, text: str, kind: str = "fact", *evidence: dict[str, str]
) -> dict[str, Any]:
    return {
        "section": section,
        "paragraph": paragraph,
        "text": text,
        "kind": kind,
        "evidence": list(evidence),
    }


GOOD = {
    "claims": [
        rc("summary", 0, "This report covers the Digital Expansion Initiative.", "framing"),
        rc("budget", 0, "The Overview lists a total approved budget of $2,400,000.", "fact", OVR),
        rc(
            "disagreements",
            0,
            "The Project Overview states a total approved budget of $2,400,000.",
            "conflict_position",
            OVR,
        ),
        rc(
            "disagreements",
            0,
            "The Budget & Timeline Breakdown states it was adjusted to $2,600,000.",
            "conflict_position",
            BUD,
        ),
    ],
    "conflicts": [{"topic": "Total project budget", "claim_indexes": [2, 3]}],
}
BAD_CLAIM = rc(
    "budget",
    1,
    "The budget was $9,000,000.",
    "fact",
    {"chunk_id": "OVR-p1-s3", "quote": "Total Approved Budget: $9,000,000"},
)


USAGE = {"input_tokens": 3000, "output_tokens": 2000}


class FakeSDK:
    """`stops` gives one stop_reason per report call (later calls end normally)."""

    def __init__(self, reports: list[dict[str, Any]], stops: list[str] | None = None) -> None:
        self.reports = reports
        self.stops = stops or []
        self.calls: list[str] = []
        self.messages = self

    def create(self, **body: Any) -> SimpleNamespace:
        stop = "end_turn"
        if body["system"][0]["text"].startswith("You write an executive report"):
            route, n = "report", self.calls.count("report")
            payload = self.reports[min(n, len(self.reports) - 1)]
            stop = self.stops[n] if n < len(self.stops) else stop
        else:
            route = "verifier"
            indexes = [int(i) for i in re.findall(r'<claim index="(\d+)"', body["messages"][0]["content"])]
            payload = {
                "judgments": [{"claim_index": i, "verdict": "SUPPORTED", "reason": "ok"} for i in indexes]
            }
        self.calls.append(route)
        return SimpleNamespace(
            model=body["model"],
            stop_reason=stop,
            content=[SimpleNamespace(type="text", text=json.dumps(payload, ensure_ascii=False))],
            usage=SimpleNamespace(to_dict=lambda: USAGE),
        )


def run(
    reports: list[dict[str, Any]], lang: str = "en", stops: list[str] | None = None
) -> tuple[dict[str, Any], float, FakeSDK]:
    sdk = FakeSDK(reports, stops)
    built, cost = report.generate(LLMClient(mode="live", inference_geo="global", sdk=sdk), CHUNKS, lang)
    return built, cost, sdk


REPORT_CALL = cost_usd(report.REPORT_MODEL, USAGE)
JUDGE_CALL = cost_usd(report.VERIFIER_MODEL, USAGE)


def test_a_failed_report_call_is_retried_once_and_billed() -> None:
    built, cost, sdk = run([GOOD], stops=["max_tokens"])
    assert sdk.calls == ["report", "report", "verifier"] and built["claimsVerified"] == 4
    assert cost == pytest.approx(2 * REPORT_CALL + JUDGE_CALL)  # the failed call was billed too


def test_two_failed_report_calls_fail_with_what_they_cost() -> None:
    with pytest.raises(LLMError) as failed:
        run([GOOD], stops=["max_tokens", "refusal"])
    assert failed.value.cost_usd == pytest.approx(2 * REPORT_CALL)


def test_a_failed_regeneration_keeps_the_verified_first_report() -> None:
    bad = {**GOOD, "claims": [*GOOD["claims"], BAD_CLAIM]}
    built, cost, sdk = run([bad], stops=["end_turn", "max_tokens"])
    assert sdk.calls == ["report", "verifier", "report"]
    assert built["claimsVerified"] == 4 and built["claimsRemoved"] == 1
    assert cost == pytest.approx(2 * REPORT_CALL + JUDGE_CALL)


def test_cli_prints_the_spend_of_a_failed_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fail(*_a: Any, **_k: Any) -> Any:
        raise LLMError("model stopped with max_tokens", cost_usd=0.25)

    monkeypatch.setenv("LLM_MODE", "replay")
    monkeypatch.setattr(report, "report_path", lambda *a, **k: tmp_path / "r.json")
    monkeypatch.setattr(report, "load_chunks", dict)
    monkeypatch.setattr(report, "generate", fail)
    assert report.main(["--lang", "en"]) == 1
    assert "$0.2500" in capsys.readouterr().err


def test_report_follows_the_template_with_server_built_citations() -> None:
    built, cost, sdk = run([GOOD])
    assert sdk.calls == ["report", "verifier"] and cost > 0
    assert [s["id"] for s in built["sections"]] == report.SECTIONS
    budget = next(s for s in built["sections"] if s["id"] == "budget")
    assert budget["paragraphs"] == [{"text": GOOD["claims"][1]["text"], "citations": [1]}]
    disagreements = next(s for s in built["sections"] if s["id"] == "disagreements")
    assert disagreements["paragraphs"][0]["citations"] == [1, 2]  # same (chunk, quote) keeps its number
    assert [c["chunkId"] for c in built["citations"]] == ["OVR-p1-s3", "BUD-p1-s2"]
    assert built["citations"][0]["pdfPage"] == 1 and built["model"] == "claude-opus-5-5"
    timeline = next(s for s in built["sections"] if s["id"] == "timeline")
    assert timeline["paragraphs"] == [{"text": report.EMPTY["en"], "citations": []}]


def test_unverifiable_sentence_is_regenerated_once_then_removed() -> None:
    bad = {**GOOD, "claims": [*GOOD["claims"], BAD_CLAIM]}
    built, _, sdk = run([bad])
    assert sdk.calls.count("report") == 2
    assert "$9,000,000" not in json.dumps(built) and built["claimsRemoved"] == 1


def test_one_sided_conflict_is_never_reported() -> None:
    one_sided = {"claims": GOOD["claims"][:3], "conflicts": [{"topic": "Budget", "claim_indexes": [2]}]}
    built, _, _ = run([one_sided])
    disagreements = next(s for s in built["sections"] if s["id"] == "disagreements")
    assert disagreements["paragraphs"][0]["text"] == report.EMPTY["en"]


def test_a_framing_sentence_never_shows_a_citation() -> None:
    framing = rc("summary", 0, "This report covers the Digital Expansion Initiative.", "framing", BUD)
    built, _, _ = run([{**GOOD, "claims": [framing, *GOOD["claims"][1:]]}])
    summary = next(s for s in built["sections"] if s["id"] == "summary")
    assert summary["paragraphs"] == [{"text": framing["text"], "citations": []}]  # judged on wording only


def test_wrong_language_twice_fails_instead_of_saving() -> None:
    with pytest.raises(LLMError):
        run([GOOD], lang="ar")


def test_cache_key_changes_with_corpus_template_model_and_language() -> None:
    base = report.cache_key("abc", "claude-opus-5-5", "en")
    assert base != report.cache_key("abd", "claude-opus-5-5", "en")
    assert base != report.cache_key("abc", "claude-opus-5-5", "en", template="exec-v2")
    assert base != report.cache_key("abc", "claude-sonnet-5-5", "en")
    assert base != report.cache_key("abc", "claude-opus-5-5", "ar")


def test_load_serves_only_the_saved_report_for_this_corpus(tmp_path: Path) -> None:
    index = tmp_path / "index"
    index.mkdir()
    (index / "manifest.json").write_text(json.dumps({"chunks_sha256": "abc"}), encoding="utf-8")
    reports = tmp_path / "reports"
    assert report.load("en", index_dir=index, reports=reports) is None
    path = report.report_path("en", index_dir=index, reports=reports)
    reports.mkdir()
    path.write_text(json.dumps({"title": "saved"}), encoding="utf-8")
    assert report.load("en", index_dir=index, reports=reports) == {"title": "saved"}
    (index / "manifest.json").write_text(json.dumps({"chunks_sha256": "changed"}), encoding="utf-8")
    assert report.load("en", index_dir=index, reports=reports) is None


def test_cli_is_a_dry_run_without_confirmation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("LLM_MODE", "record")
    monkeypatch.setattr(report, "report_path", lambda lang, model=report.REPORT_MODEL: tmp_path / "none.json")
    monkeypatch.setattr(report.LLMClient, "call", lambda *a, **k: pytest.fail("no model call without --yes"))
    assert report.main(["--lang", "en"]) == 0
    assert "Dry run" in capsys.readouterr().out


def test_conflicts_come_from_paragraphs_not_from_model_indexes() -> None:
    off_by_one = {**GOOD, "conflicts": [{"topic": "Total project budget", "claim_indexes": [1, 2]}]}
    built, _, _ = run([off_by_one])
    disagreements = next(s for s in built["sections"] if s["id"] == "disagreements")
    assert "$2,600,000" in disagreements["paragraphs"][0]["text"] and built["claimsRemoved"] == 0
