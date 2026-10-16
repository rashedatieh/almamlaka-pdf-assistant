"""End-to-end answer evaluation on gold-v1: the full engine (planner, retrieval, answer, verifier, render).

  LLM_MODE=live|record uv run python -m eval.run_e2e --yes      (live: about $1.50 on Sonnet 5.5)
  LLM_MODE=replay      uv run python -m eval.run_e2e            (replays recorded calls at $0)

Scores per question, then per slice (English / Arabic varieties):
  abstention   answerable -> answered|partial|clarify; unanswerable -> not_in_documents|out_of_scope
  citation hit at least one cited chunk is a gold relevant chunk (answered turns with gold ids)
  language     reply language matches the question (Arabic varieties and Arabizi -> ar)
  conflict     documented conflicts (C-01..C-03, B-08, B-09) carry the "conflict" flag
  latency, cost
Writes eval/reports/e2e/<run>.md and .jsonl.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from app.budget import DailyBudget
from app.llm.client import LLMClient
from app.pipeline.orchestrator import Engine, Settings
from app.pipeline.planner import Turn
from app.pipeline.report import load_chunks
from app.retrieval.conflicts import load_conflict_groups
from app.retrieval.retriever import Retriever

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "eval" / "gold" / "gold-v1.jsonl"
OUT = ROOT / "eval" / "reports" / "e2e"
CONFLICTS = {"C-01", "C-02", "C-03", "B-08", "B-09"}
ARABIC = {"msa", "levantine", "arabizi", "gulf", "egyptian"}


def expected_lang(row: dict[str, Any]) -> str | None:
    """An explicit request ("answer in Arabic", «أجب باللغة الإنجليزية») wins over the question's script."""
    question = row["question"].lower()
    if "in arabic" in question or "بالعربية" in question or "باللغة العربية" in question:
        return "ar"
    if "in english" in question or "بالإنجليزية" in question or "باللغة الإنجليزية" in question:
        return "en"
    if row["variety"] in ARABIC:
        return "ar"
    if row["variety"] == "english":
        return "en"
    return None  # mixed: either is acceptable


def score(row: dict[str, Any], turn: dict[str, Any]) -> dict[str, Any]:
    status = turn["status"]
    if row["answerable"]:
        abstention = status in {"answered", "partial", "clarify"}
    else:
        # ACCEPTANCE_TESTS allows a partial answer for some (E-04: "or partial with planned dates")
        allowed = {"not_in_documents", "out_of_scope"} | (
            {"partial"} if "or partial" in row["note"] else set()
        )
        abstention = status in allowed
    cited = {c["chunkId"] for c in turn["citations"]}
    hit = None
    if row["answerable"] and row["relevant_ids"] and status in {"answered", "partial"}:
        hit = bool(cited & set(row["relevant_ids"]))
    want = expected_lang(row)
    return {
        "abstention": abstention,
        "citation_hit": hit,
        "language": None if want is None else turn["lang"] == want,
        "conflict": ("conflict" in turn["flags"]) if row["qid"] in CONFLICTS else None,
    }


def rate(values: list[bool | None]) -> str:
    vals = [v for v in values if v is not None]
    return f"{sum(vals)}/{len(vals)} ({sum(vals) / len(vals):.0%})" if vals else "-"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="confirm live calls")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", default="", help="comma-separated qids, e.g. A-01,A-07")
    args = parser.parse_args(argv)
    mode = os.environ.get("LLM_MODE", "replay")
    if mode != "replay" and not args.yes:
        print("Dry run: about 48 live turns on Sonnet 5.5, roughly $1.50. Re-run with --yes.")
        return 0
    rows = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = rows[: args.limit] if args.limit else rows
    if args.only:
        wanted = set(args.only.split(","))
        rows = [r for r in rows if r["qid"] in wanted]
    chunks = load_chunks()
    budget = DailyBudget(float(os.environ.get("E2E_BUDGET_USD", "4.00")))
    engine = Engine(
        LLMClient(mode=mode, timeout_s=120),
        Retriever(list(chunks.values())),
        chunks,
        budget,
        Settings(),
        conflict_groups=load_conflict_groups(known=set(chunks)),
    )
    results = []
    for row in rows:
        # gold history is a list of earlier user messages (strings) or {role, text} items
        history = [
            Turn("user", h) if isinstance(h, str) else Turn(h["role"], h["text"])
            for h in row.get("history", [])
        ]
        before = budget.spent_today
        started = time.monotonic()
        final = None
        for event in engine.run(row["question"], history):
            if event["type"] == "final":
                final = event["turn"]
            elif event["type"] == "error":
                final = {
                    "status": "error",
                    "lang": "",
                    "flags": [],
                    "citations": [],
                    "claims": [],
                    "message": event["message"],
                }
        if final is None:
            raise RuntimeError(f"{row['qid']}: no final turn")
        result = {
            "qid": row["qid"],
            "variety": row["variety"],
            "status": final["status"],
            "lang": final["lang"],
            "flags": final["flags"],
            "cited": [c["chunkId"] for c in final["citations"]],
            "text": " ".join(
                t for t in [final.get("message", ""), *(c["text"] for c in final["claims"])] if t
            ),
            "seconds": round(time.monotonic() - started, 2),
            "cost_usd": round(budget.spent_today - before, 5),
            **score(row, final),
        }
        results.append(result)
        print(
            f"{row['qid']:5} {result['status']:16} {result['lang']:2} {result['seconds']:6}s "
            f"abst={result['abstention']} cite={result['citation_hit']} lang={result['language']} "
            f"conf={result['conflict']}",
            flush=True,
        )

    english = [r for r in results if r["variety"] == "english"]
    arabic = [r for r in results if r["variety"] != "english"]
    seconds = sorted(r["seconds"] for r in results)
    lines = [
        f"# End-to-end run `{mode}` on gold-v1 ({len(results)} questions)",
        "",
        "| Slice | abstention | citation hit | reply language | conflict flagged |",
        "|---|---|---|---|---|",
    ]
    for name, rs in (("overall", results), ("english", english), ("arabic varieties", arabic)):
        lines.append(
            f"| {name} | {rate([r['abstention'] for r in rs])} | {rate([r['citation_hit'] for r in rs])} "
            f"| {rate([r['language'] for r in rs])} | {rate([r['conflict'] for r in rs])} |"
        )
    lines += [
        "",
        f"Latency: median {seconds[len(seconds) // 2]}s, p90 {seconds[int(len(seconds) * 0.9) - 1]}s, "
        f"max {seconds[-1]}s. Spend: ${sum(r['cost_usd'] for r in results):.4f} "
        f"(${sum(r['cost_usd'] for r in results) / len(results):.4f} per turn).",
        "",
        "Failures:",
        *[
            f"- {r['qid']} ({r['variety']}): status={r['status']} lang={r['lang']} flags={r['flags']} "
            f"cited={r['cited']} — {r['text'][:200]}"
            for r in results
            if False in (r["abstention"], r["citation_hit"], r["language"], r["conflict"])
        ],
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    name = mode if not (args.only or args.limit) else f"{mode}-subset"
    (OUT / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / f"{name}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results), encoding="utf-8"
    )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
