"""The M2 retrieval harness: gate logic, conflict-evidence checks and the offline BM25 baseline."""

from __future__ import annotations

from pathlib import Path

from eval import run_retrieval as rr

ROOT = Path(__file__).resolve().parents[2]
GOLD = rr.load(rr.GOLD)


def test_gold_v1_has_the_agreed_shape() -> None:
    assert len(GOLD) == 48 and "B-12" not in {g["qid"] for g in GOLD}
    assert all(
        set(g) == {"qid", "question", "variety", "relevant_ids", "answerable", "history", "note"}
        for g in GOLD
    )
    known = {
        line.split('"chunk_id": "')[1].split('"')[0]
        for line in (ROOT / "data/index/chunks.jsonl").read_text("utf-8").splitlines()
    }
    assert all(set(g["relevant_ids"]) <= known for g in GOLD)  # every gold ID is a real §0 chunk


def test_conflict_evidence_needs_both_sides() -> None:
    perfect = {g["qid"]: g["relevant_ids"] + ["OVR-p1-s1", "BUD-p1-s1", "GOV-p1-s1"] for g in GOLD}
    report = rr.checks(GOLD, perfect)
    assert all(report["conflict_evidence"].values()) and report["a13_all_documents"]
    assert report["overall"]["recall@5"] == 1.0  # every relevant ID ranks within the top 5 here
    one_sided = dict(perfect, **{"C-01": ["OVR-p1-s3"]})
    assert rr.checks(GOLD, one_sided)["conflict_evidence"]["C-01"] is False


def test_offline_bm25_baseline_matches_expectations() -> None:
    retriever = rr.build_retriever("bm25", "replay")
    runs = {g["qid"]: retriever.retrieve([g["question"]]).chunk_ids for g in GOLD}
    report = rr.checks(GOLD, runs)
    english = [
        g
        for g in GOLD
        if g["variety"] == "english" and g["answerable"] and g["relevant_ids"] and not g["history"]
    ]
    found = sum(set(g["relevant_ids"]) <= set(runs[g["qid"]][:5]) for g in english)
    assert found == len(english)  # every self-contained English question is found by keywords alone
    assert report["arabic"]["recall@5"] < 0.5  # Arabic needs the planner or dense leg: the M2 gap
