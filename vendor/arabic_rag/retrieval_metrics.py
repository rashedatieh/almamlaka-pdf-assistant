#!/usr/bin/env python3
"""Compute retrieval and citation metrics for a bilingual (Arabic/English) RAG evaluation run.

Inputs (JSONL):
  gold : {"qid", "question", "variety", "relevant_ids": [...], "answerable": true|false}
         variety examples: msa, gulf, levantine, egyptian, arabizi, english, mixed
  run  : {"qid", "retrieved_ids": [ranked ids], "cited_ids": [...], "refused": true|false}

Metrics per query, then averaged overall and per variety:
  recall@k (k from --k, default 1,3,5,10), hit@k, MRR@10, nDCG@10 (binary relevance),
  citation precision (cited ids that are relevant / cited ids), citation coverage
  (answerable queries with at least one relevant citation), refusal accuracy on unanswerable
  queries (refused == true), false refusals on answerable queries.

Gates (optional): --min-recall-at-5, --min-citation-precision, --min-refusal-accuracy make the
script exit 1 when the overall value is below the threshold (use in CI).

Results are "Measured" only when the gold set version and the baseline run are recorded with them.
Standard library only; no network. Exit codes: 0 ok, 1 gate failed or invalid data, 2 usage/I-O error.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional


def read_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{n}: invalid JSON: {exc}") from exc
    return rows


def ndcg_at(ranked: List[str], relevant: set, k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, doc in enumerate(ranked[:k]) if doc in relevant)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 0.0


def per_query(gold: dict, run: Optional[dict], ks: List[int]) -> Dict[str, Optional[float]]:
    relevant = set(gold.get("relevant_ids", []))
    answerable = bool(gold.get("answerable", True))
    ranked = list(run.get("retrieved_ids", [])) if run else []
    cited = list(run.get("cited_ids", [])) if run else []
    refused = bool(run.get("refused", False)) if run else False
    m: Dict[str, Optional[float]] = {}
    if answerable and relevant:
        for k in ks:
            found = len(relevant & set(ranked[:k]))
            m[f"recall@{k}"] = found / len(relevant)
            m[f"hit@{k}"] = 1.0 if found else 0.0
        rr = 0.0
        for i, doc in enumerate(ranked[:10]):
            if doc in relevant:
                rr = 1.0 / (i + 1)
                break
        m["mrr@10"] = rr
        m["ndcg@10"] = ndcg_at(ranked, relevant, 10)
        m["citation_coverage"] = 1.0 if relevant & set(cited) else 0.0
        m["false_refusal"] = 1.0 if refused else 0.0
    else:
        m["refusal_accuracy"] = 1.0 if refused else 0.0
    if cited:
        m["citation_precision"] = len([c for c in cited if c in relevant]) / len(cited)
    m["missing_run"] = 0.0 if run else 1.0
    return m


def average(rows: List[Dict[str, Optional[float]]]) -> Dict[str, float]:
    sums: Dict[str, float] = defaultdict(float)
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        for key, value in row.items():
            if value is not None:
                sums[key] += value
                counts[key] += 1
    return {key: round(sums[key] / counts[key], 3) for key in sorted(sums)}


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--k", default="1,3,5,10", help="comma-separated cut-offs (default 1,3,5,10)")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--min-recall-at-5", type=float)
    parser.add_argument("--min-citation-precision", type=float)
    parser.add_argument("--min-refusal-accuracy", type=float)
    args = parser.parse_args(argv)
    try:
        ks = sorted({int(x) for x in args.k.split(",") if x.strip()})
        gold_rows = read_jsonl(args.gold)
        run_rows = read_jsonl(args.run)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not gold_rows:
        print("ERROR: gold set is empty", file=sys.stderr)
        return 1
    problems = [f"gold row {i}: missing qid" for i, g in enumerate(gold_rows) if "qid" not in g]
    qids = [g.get("qid") for g in gold_rows]
    if len(set(qids)) != len(qids):
        problems.append("duplicate qid in gold set")
    if problems:
        for p in problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 1
    runs = {r.get("qid"): r for r in run_rows}
    unknown = set(runs) - set(qids)
    per_q = []
    by_variety: Dict[str, List[Dict[str, Optional[float]]]] = defaultdict(list)
    for g in gold_rows:
        metrics = per_query(g, runs.get(g["qid"]), ks)
        per_q.append(metrics)
        by_variety[str(g.get("variety", "unspecified"))].append(metrics)
    overall = average(per_q)
    varieties = {v: average(rows) | {"n": len(rows)} for v, rows in sorted(by_variety.items())}
    result = {"overall": overall | {"n": len(per_q)}, "by_variety": varieties,
              "run_qids_not_in_gold": sorted(str(u) for u in unknown)}
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        cols = [f"recall@{k}" for k in ks] + ["mrr@10", "ndcg@10", "citation_precision", "citation_coverage",
                                             "refusal_accuracy", "false_refusal"]
        print("| Slice | n | " + " | ".join(cols) + " |")
        print("|---|---|" + "---|" * len(cols))
        for name, metrics in [("overall", result["overall"])] + list(varieties.items()):
            cells = [f"{metrics[c]:.2f}" if c in metrics else "-" for c in cols]
            print(f"| {name} | {metrics['n']} | " + " | ".join(cells) + " |")
        if unknown:
            print(f"\nWARNING: {len(unknown)} run qids not in gold set: {sorted(str(u) for u in unknown)}")
        missing = sum(1 for m in per_q if m.get("missing_run"))
        if missing:
            print(f"\nWARNING: {missing} gold queries have no run row (scored as empty retrieval)")
    gates = [("recall@5", args.min_recall_at_5), ("citation_precision", args.min_citation_precision),
             ("refusal_accuracy", args.min_refusal_accuracy)]
    failed = False
    for key, threshold in gates:
        if threshold is None:
            continue
        value = overall.get(key)
        if value is None or value < threshold:
            print(f"GATE FAIL: overall {key} = {value} < {threshold}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
