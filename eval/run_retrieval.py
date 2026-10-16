"""M2 retrieval A/B on gold-v1 (ACCEPTANCE_TESTS §M: recall gates, conflict evidence, dense-leg A/B).

Configurations:
  --config bm25 | hybrid-gemini-embedding-001 | hybrid-gemini-embedding-2
  --queries raw      the gold question as the only query (no LLM; offline baseline)
  --queries planner  the planner's standalone question + searches (needs PLANNER_MODEL; LLM_MODE decides
                     whether cassettes are replayed, recorded or bypassed)

Query embeddings for the hybrid configs are cached in eval/cassettes/embed/<model>.json, so a recorded
A/B replays offline at no cost. Any live call (LLM_MODE=record|live) prints an estimate first and needs
--yes; estimates above $1 also need --over-1-dollar (docs/ENGINEERING_RULES.md operating constraints).

Writes eval/reports/retrieval/<config>__<queries>.{run.jsonl,md}. With --gate, it exits 1 when a gate
fails: recall@5 ≥ 0.95 overall, ≥ 0.90 on the Arabic slice, both sides of C1/C2 retrieved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

from app.llm.client import LLMClient
from app.pipeline.planner import PROMPT, Turn, plan
from app.prices import PRICES
from app.retrieval.dense import DenseLeg, VectorStore, VertexEmbedder, load_vectors, unit
from app.retrieval.retriever import Retriever
from vendor.arabic_rag.retrieval_metrics import average, per_query

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "eval" / "gold" / "gold-v1.jsonl"
REPORTS = ROOT / "eval" / "reports" / "retrieval"
EMBED_CASSETTES = ROOT / "eval" / "cassettes" / "embed"
CONFIGS = ("bm25", "hybrid-gemini-embedding-001", "hybrid-gemini-embedding-2")
ARABIC = {"msa", "levantine", "arabizi", "mixed", "gulf", "egyptian"}
# Both sides of each documented conflict must be retrieved (ACCEPTANCE §M "Conflict evidence recall").
CONFLICT_SIDES = {
    "C-01": [{"OVR-p1-s3"}, {"BUD-p1-s2"}],
    "C-03": [{"OVR-p1-s3"}, {"BUD-p1-s2"}],
    "B-08": [{"OVR-p1-s3"}, {"BUD-p1-s2"}],
    "C-02": [{"GOV-p1-s3"}, {"OVR-p1-s3", "BUD-p2-s3"}],
    "B-09": [{"GOV-p1-s3"}, {"OVR-p1-s3", "BUD-p2-s3"}],
}
DENSE_MIN_SIMILARITY = 0.0  # A/B measures the raw dense ranking; the production threshold is set from it
# Planner call size for the cost estimate: system prompt + question in, JSON plan out [Estimate].
PLANNER_TOKENS_IN, PLANNER_TOKENS_OUT = 1_400, 500


class CachedQueryEmbedder:
    """Query embeddings from a JSON cassette; misses go live only in record/live mode."""

    def __init__(self, model: str, mode: str) -> None:
        self.model, self.mode = model, mode
        self.path = EMBED_CASSETTES / f"{model}.json"
        self.cache: dict[str, list[float]] = (
            json.loads(self.path.read_text("utf-8")) if self.path.is_file() else {}
        )
        self._live: VertexEmbedder | None = None

    def embed_document(
        self, title: str, text: str
    ) -> np.ndarray:  # pragma: no cover - corpus uses make embed
        raise NotImplementedError

    def embed_query(self, text: str) -> np.ndarray:
        key = hashlib.sha256(f"{self.model}\n{text}".encode()).hexdigest()[:32]
        if key not in self.cache:
            if self.mode == "replay":
                raise RuntimeError(f"no cached embedding for {text!r}; record it with an approved live run")
            if self._live is None:
                self._live = VertexEmbedder(
                    self.model,
                    os.environ.get("GCP_PROJECT", ""),
                    os.environ.get("VERTEX_LOCATION", "global"),
                    timeout_s=30.0,
                )
            self.cache[key] = self._live.embed_query(text).tolist()
            if self.mode == "record":
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.cache, sort_keys=True) + "\n", encoding="utf-8")
        return unit(self.cache[key])


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_retriever(config: str, mode: str) -> Retriever:
    chunks = load(ROOT / "data" / "index" / "chunks.jsonl")
    if config == "bm25":
        return Retriever(chunks)
    model = config.removeprefix("hybrid-")
    manifest = json.loads((ROOT / "data" / "index" / "manifest.json").read_text("utf-8"))
    ids = [c["chunk_id"] for c in chunks]
    store = VectorStore(ids, load_vectors(model, ids, manifest["chunks_sha256"]))
    leg = DenseLeg(
        CachedQueryEmbedder(model, mode), store, min_similarity=DENSE_MIN_SIMILARITY, timeout_s=60.0
    )
    return Retriever(chunks, dense=leg)


def checks(gold: list[dict[str, Any]], runs: dict[str, list[str]]) -> dict[str, Any]:
    """Recall by slice (vendored metrics), conflict evidence, and A-13 document coverage."""
    rows = {g["qid"]: per_query(g, {"retrieved_ids": runs[g["qid"]]}, [1, 3, 5, 8]) for g in gold}
    arabic = [rows[g["qid"]] for g in gold if g["variety"] in ARABIC]
    conflict = {
        qid: all(any(cid in runs[qid] for cid in side) for side in sides)
        for qid, sides in CONFLICT_SIDES.items()
    }
    a13 = {cid.split("-")[0] for cid in runs.get("A-13", [])} >= {"OVR", "BUD", "GOV"}
    return {
        "overall": average(list(rows.values())),
        "arabic": average(arabic),
        "conflict_evidence": conflict,
        "a13_all_documents": a13,
        "misses": {
            g["qid"]: sorted(set(g["relevant_ids"]) - set(runs[g["qid"]][:5]))
            for g in gold
            if g["answerable"] and set(g["relevant_ids"]) - set(runs[g["qid"]][:5])
        },
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", choices=CONFIGS, default="bm25")
    parser.add_argument("--queries", choices=("raw", "planner"), default="raw")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--yes", action="store_true", help="confirm live calls (LLM_MODE=record|live)")
    parser.add_argument("--over-1-dollar", action="store_true", help="confirm an estimate above $1")
    args = parser.parse_args(argv)

    mode = os.environ.get("LLM_MODE", "replay")
    gold = load(GOLD)
    planner_model = os.environ.get("PLANNER_MODEL", "")
    if args.queries == "planner":
        if planner_model not in PRICES:
            print(f"run_retrieval: set PLANNER_MODEL to one of {sorted(PRICES)} (ADR D19)", file=sys.stderr)
            return 2
        if mode != "replay":
            price = PRICES[planner_model]
            estimate = len(gold) * (PLANNER_TOKENS_IN * price.input + PLANNER_TOKENS_OUT * price.output) / 1e6
            estimate *= 1.1 if os.environ.get("INFERENCE_GEO", "global") == "us" else 1.0
            calls = f"{len(gold)} planner calls on {planner_model}"
            print(f"run_retrieval: {calls}, estimated ${estimate:.2f} [Estimate]")
            if not args.yes or (estimate > 1 and not args.over_1_dollar):
                print("run_retrieval: refusing live calls without --yes (and --over-1-dollar above $1)")
                return 2

    retriever = build_retriever(args.config, mode)
    client = LLMClient(mode=mode) if args.queries == "planner" else None
    runs: dict[str, list[str]] = {}
    lines, spent = [], 0.0
    for g in gold:
        queries = [g["question"]]
        if client is not None:
            history = [Turn("user", q) for q in g["history"]]
            result = plan(client, planner_model, g["question"], history)
            spent += 0.0 if result.llm.from_cassette else result.llm.cost_usd
            queries = result.queries or [g["question"]]
        retrieval = retriever.retrieve(queries)
        runs[g["qid"]] = retrieval.chunk_ids
        lines.append(
            {
                "qid": g["qid"],
                "retrieved_ids": retrieval.chunk_ids,
                "queries": queries,
                "dense_fallback": retrieval.dense_fallback,
            }
        )

    report = checks(gold, runs)
    tag = f"{args.config}__{args.queries}"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{tag}.run.jsonl").write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines), encoding="utf-8"
    )
    prompt_version = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]
    md = [
        f"# Retrieval run `{tag}`",
        "",
        f"gold: gold-v1 ({len(gold)} rows) · planner: {planner_model or '-'} "
        f"· planner prompt sha {prompt_version} · live spend this run: ${spent:.4f}",
        "",
        "| Slice | recall@1 | recall@3 | recall@5 | recall@8 | MRR@10 |",
        "|---|---|---|---|---|---|",
    ]
    for name in ("overall", "arabic"):
        m = report[name]
        md.append(
            f"| {name} | "
            + " | ".join(
                f"{m.get(k, 0):.2f}" for k in ("recall@1", "recall@3", "recall@5", "recall@8", "mrr@10")
            )
            + " |"
        )
    md += [
        "",
        f"Conflict evidence (both sides retrieved): {report['conflict_evidence']}",
        f"A-13 retrieves all three documents: {report['a13_all_documents']}",
        f"Recall@5 misses: {report['misses'] or 'none'}",
        "",
    ]
    (REPORTS / f"{tag}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))

    if args.gate:
        failed = []
        if report["overall"].get("recall@5", 0) < 0.95:
            failed.append("overall recall@5 < 0.95")
        if report["arabic"].get("recall@5", 0) < 0.90:
            failed.append("Arabic recall@5 < 0.90")
        if not all(report["conflict_evidence"].values()):
            failed.append("conflict evidence incomplete")
        if failed:
            print("run_retrieval: GATE FAILED - " + "; ".join(failed), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
