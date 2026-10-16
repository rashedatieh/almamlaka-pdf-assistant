"""M2 retrieval: tokenizer, BM25, RRF, LanceDB exact search, dense fallback and per-document diversity.

No network: the dense leg uses a deterministic fake embedder (hashed bag of words).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pytest

from app.retrieval.bm25 import BM25, tokenize
from app.retrieval.dense import DenseLeg, DenseUnavailable, VectorStore, load_vectors, unit
from app.retrieval.fuse import rrf
from app.retrieval.retriever import Retriever, index_text

ROOT = Path(__file__).resolve().parents[2]
CHUNKS = [
    json.loads(line)
    for line in (ROOT / "data" / "index" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
]
GOLD = [
    json.loads(line)
    for line in (ROOT / "eval" / "gold" / "gold-v1.jsonl").read_text(encoding="utf-8").splitlines()
]


class FakeEmbedder:
    """Deterministic bag-of-words vectors: shared tokens give positive cosine similarity."""

    model = "fake"

    def __init__(self, dim: int = 256, delay_s: float = 0.0, fail: bool = False) -> None:
        self.dim, self.delay_s, self.fail = dim, delay_s, fail

    def _vector(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for token in tokenize(text):
            v[int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.dim] += 1.0
        v[0] += 1e-3  # never all-zero
        return unit(v)

    def embed_document(self, title: str, text: str) -> np.ndarray:
        return self._vector(f"{title} {text}")

    def embed_query(self, text: str) -> np.ndarray:
        time.sleep(self.delay_s)
        if self.fail:
            raise ConnectionError("vertex unreachable")
        return self._vector(text)


def dense_leg(embedder: FakeEmbedder | None = None, **kwargs: float) -> DenseLeg:
    embedder = embedder or FakeEmbedder()
    vectors = np.stack([embedder.embed_document(c["doc_subtitle"], index_text(c)) for c in CHUNKS])
    store = VectorStore([c["chunk_id"] for c in CHUNKS], vectors)
    return DenseLeg(
        embedder=embedder, store=store, min_similarity=kwargs.pop("min_similarity", 0.1), **kwargs
    )


# ---- tokenizer and BM25 -----------------------------------------------------------------------------


def test_numbers_match_with_or_without_separators_and_dollar_sign() -> None:
    assert tokenize("$2,400,000") == tokenize("2400000") == ["2400000"]
    assert tokenize("Q2 2027") == ["q2", "2027"]


def test_tokenizer_drops_question_words_and_stems_plurals_symmetrically() -> None:
    assert tokenize("What are the platforms?") == ["platform"]
    assert tokenize("platform") == ["platform"]
    assert tokenize("status") == ["status"]  # -us is not a plural


def test_arabic_is_normalised_like_the_index() -> None:
    # Diacritics, alef forms and the article are handled the same in documents and queries.
    assert tokenize("المِيزانيّة") == tokenize("ميزانيه")


def test_bm25_ranks_the_section_with_the_answer_first() -> None:
    bm25 = BM25({c["chunk_id"]: index_text(c) for c in CHUNKS})
    assert bm25.search("How often does the steering committee meet?")[0][0] == "GOV-p1-s2"
    assert bm25.search("marketing Q2 2027")[0][0] == "BUD-p1-s1"
    assert bm25.search("mobile app design freeze")[0][0] == "BUD-p2-s3"


def test_bm25_returns_only_chunks_with_a_matching_term() -> None:
    bm25 = BM25({c["chunk_id"]: index_text(c) for c in CHUNKS})
    assert bm25.search("zebra xylophone") == []
    assert all(score > 0 for _, score in bm25.search("budget"))


# ---- fusion ---------------------------------------------------------------------------------------


def test_rrf_rewards_agreement_and_is_deterministic() -> None:
    fused = rrf([["a", "b", "c"], ["b", "a", "d"], ["b"]], k=50)
    assert [cid for cid, _ in fused] == ["b", "a", "c", "d"]
    assert rrf([["x"], ["y"]]) == rrf([["y"], ["x"]])  # ties broken by ID, not input order


# ---- LanceDB store and dense leg ------------------------------------------------------------------


def test_vector_store_exact_cosine_search() -> None:
    vectors = np.stack([unit([1, 0, 0]), unit([0, 1, 0]), unit([1, 1, 0])])
    store = VectorStore(["a", "b", "c"], vectors)
    hits = store.search(unit([1, 0.2, 0]), limit=3)
    assert [cid for cid, _ in hits] == ["a", "c", "b"]
    assert hits[0][1] == pytest.approx(float(unit([1, 0.2, 0]) @ unit([1, 0, 0])), abs=1e-5)


def test_dense_leg_filters_by_similarity_threshold() -> None:
    leg = dense_leg(min_similarity=0.99)
    assert leg.search(["completely unrelated words"]) == [[]]


def test_dense_timeout_and_errors_raise_dense_unavailable() -> None:
    with pytest.raises(DenseUnavailable, match="exceeded"):
        dense_leg(FakeEmbedder(delay_s=0.5), timeout_s=0.05).search(["budget"])
    with pytest.raises(DenseUnavailable, match="ConnectionError"):
        dense_leg(FakeEmbedder(fail=True)).search(["budget"])


def test_retriever_falls_back_to_bm25_when_dense_is_down() -> None:
    # ACCEPTANCE §M "Dense fallback": results still come back, flagged dense_fallback.
    retriever = Retriever(CHUNKS, dense=dense_leg(FakeEmbedder(fail=True)))
    result = retriever.retrieve(["How often does the steering committee meet?"])
    assert result.dense_fallback and "ConnectionError" in result.dense_error
    assert result.chunk_ids[0] == "GOV-p1-s2"
    assert "dense" not in result.rankings


def test_load_vectors_refuses_vectors_from_another_index(tmp_path: Path) -> None:
    ids = ["a", "b"]
    np.save(tmp_path / "m.npy", np.eye(2, dtype=np.float32))
    (tmp_path / "m.json").write_text(json.dumps({"chunk_ids": ids, "chunks_sha256": "old"}), encoding="utf-8")
    with pytest.raises(DenseUnavailable, match="different index"):
        load_vectors("m", ids, "new", tmp_path)
    assert load_vectors("m", ids, "old", tmp_path).shape == (2, 2)
    with pytest.raises(DenseUnavailable, match="make embed"):
        load_vectors("missing", ids, "old", tmp_path)


# ---- retriever: fusion across legs and queries, diversity -----------------------------------------


def test_conflicting_documents_are_both_retrieved_for_c1_and_c2() -> None:
    retriever = Retriever(CHUNKS)
    budget = retriever.retrieve(["total project budget", "budget revised Finance Committee"]).chunk_ids
    assert {"OVR-p1-s3", "BUD-p1-s2"} <= set(budget)
    launch = retriever.retrieve(["public launch date", "launch date moved"]).chunk_ids
    assert {"GOV-p1-s3", "OVR-p1-s3", "BUD-p2-s3"} <= set(launch)


def test_diversity_adds_only_matched_chunks_from_unrepresented_documents() -> None:
    retriever = Retriever(CHUNKS, top_k=1)
    result = retriever.retrieve(["steering"])
    docs = {cid.split("-")[0] for cid in result.chunk_ids}
    assert docs == {"OVR", "GOV"}  # BUD never says "steering", so nothing from BUD is forced in
    assert len(result.chunk_ids) == 2 and len(result.diversity_added) == 1
    assert all(cid in result.chunk_ids for cid in result.diversity_added)


def test_retriever_deduplicates_queries_and_ignores_blank_ones() -> None:
    result = Retriever(CHUNKS).retrieve(["budget", " budget ", "", "   "])
    assert len(result.rankings["bm25"]) == 1


def test_hybrid_with_fake_dense_keeps_english_recall() -> None:
    retriever = Retriever(CHUNKS, dense=dense_leg())
    english = [
        g
        for g in GOLD
        if g["variety"] == "english" and g["answerable"] and g["relevant_ids"] and not g["history"]
    ]
    found = sum(
        set(g["relevant_ids"]) <= set(retriever.retrieve([g["question"]]).chunk_ids[:5]) for g in english
    )
    assert found / len(english) >= 0.95
