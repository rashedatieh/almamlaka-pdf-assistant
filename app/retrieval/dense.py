"""Dense leg: Vertex AI embeddings in an embedded LanceDB table (PROJECT_PLAN §3.1; ADR-0001 §1, §3.2).

Corpus vectors are computed once by `make embed` (a live call) and committed as
data/index/embeddings/<model>.npy; they are deterministic, which LanceDB files are not. At start-up they
are loaded into an embedded LanceDB table and searched exactly: cosine distance with the vector index
bypassed. Each search embeds the query once.

The two candidate models take their instructions differently (ADR §3.2):
  gemini-embedding-001  task_type RETRIEVAL_DOCUMENT/RETRIEVAL_QUERY (+ title); vectors re-normalised at 768
  gemini-embedding-2    text prefixes "title: … | text: …" and "task: search result | query: …"
Every input uses the `embed` normalisation profile. If the query embedding fails or exceeds
DENSE_TIMEOUT_S, the caller falls back to BM25 only (ACCEPTANCE §M "Dense fallback").
"""

from __future__ import annotations

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from app.textnorm import for_embed

MODELS = ("gemini-embedding-001", "gemini-embedding-2")
EMBEDDINGS_DIR = Path(__file__).resolve().parents[2] / "data" / "index" / "embeddings"


class DenseUnavailable(Exception):
    """The dense leg cannot answer this search (timeout, API error, missing vectors)."""


class Embedder(Protocol):
    model: str

    def embed_document(self, title: str, text: str) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def unit(vector: Any) -> np.ndarray:
    v = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(v))
    if not norm:
        raise DenseUnavailable("zero-length embedding")
    return v / norm


def _operator_credentials() -> Any:
    """Explicit credentials for operator runs on a workstation, else None (Cloud Run's own identity).

    GCP_ACCESS_TOKEN (e.g. from `gcloud auth print-access-token`) avoids the machine's Application Default
    Credentials, which may belong to another account or point their quota at another project.
    """
    token = os.environ.get("GCP_ACCESS_TOKEN", "").strip()
    if not token:
        return None
    from google.oauth2.credentials import Credentials

    return Credentials(token)


class VertexEmbedder:
    """Embeddings through google-genai on Vertex (`enterprise=True`), always with an explicit project."""

    def __init__(
        self, model: str, project: str, location: str, dim: int = 768, timeout_s: float = 1.5
    ) -> None:
        if model not in MODELS:
            raise ValueError(f"unknown embedding model {model!r}; expected one of {MODELS}")
        if not project:
            raise ValueError("GCP_PROJECT is required: Google clients never rely on a default project")
        from google import genai  # imported lazily: tests and BM25-only runs never need it

        self.model = model
        self.dim = dim
        self.timeout_ms = int(timeout_s * 1000)
        self.client = genai.Client(
            enterprise=True, project=project, location=location, credentials=_operator_credentials()
        )

    def _embed(self, content: str, **config: Any) -> np.ndarray:
        config = {"output_dimensionality": self.dim, "http_options": {"timeout": self.timeout_ms}, **config}
        response = self.client.models.embed_content(model=self.model, contents=[content], config=config)
        (embedding,) = response.embeddings or []
        return unit(embedding.values)

    def embed_document(self, title: str, text: str) -> np.ndarray:
        title, text = for_embed(title), for_embed(text)
        if self.model == "gemini-embedding-001":
            return self._embed(text, task_type="RETRIEVAL_DOCUMENT", title=title)
        return self._embed(f"title: {title or 'none'} | text: {text}")

    def embed_query(self, text: str) -> np.ndarray:
        text = for_embed(text)
        if self.model == "gemini-embedding-001":
            return self._embed(text, task_type="RETRIEVAL_QUERY")
        return self._embed(f"task: search result | query: {text}")


class VectorStore:
    """An embedded LanceDB table of unit vectors; exact cosine search (no approximate index)."""

    TABLE = "chunks"

    def __init__(self, chunk_ids: list[str], vectors: np.ndarray) -> None:
        import lancedb
        import pyarrow as pa

        if len(chunk_ids) != len(vectors):
            raise DenseUnavailable("vector count does not match chunk count")
        dim = int(vectors.shape[1])
        schema = pa.schema(
            [pa.field("chunk_id", pa.string()), pa.field("vector", pa.list_(pa.float32(), dim))]
        )
        self._dir = tempfile.TemporaryDirectory(prefix="almamlaka-lancedb-")
        rows = [{"chunk_id": cid, "vector": v.tolist()} for cid, v in zip(chunk_ids, vectors, strict=True)]
        self.table = lancedb.connect(self._dir.name).create_table(
            self.TABLE, data=rows, schema=schema, mode="overwrite"
        )

    def search(self, vector: np.ndarray, limit: int) -> list[tuple[str, float]]:
        """(chunk_id, cosine similarity), best first."""
        query = self.table.search(vector.tolist()).distance_type("cosine").bypass_vector_index().limit(limit)
        hits = [(row["chunk_id"], 1.0 - float(row["_distance"])) for row in query.to_list()]
        return sorted(hits, key=lambda hit: (-hit[1], hit[0]))


def load_vectors(
    model: str, chunk_ids: list[str], chunks_sha256: str, directory: Path = EMBEDDINGS_DIR
) -> np.ndarray:
    """Committed corpus vectors for a model; refuses vectors built from a different index."""
    meta_path, npy_path = directory / f"{model}.json", directory / f"{model}.npy"
    if not (meta_path.is_file() and npy_path.is_file()):
        raise DenseUnavailable(f"no corpus vectors for {model}; run make embed")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta["chunk_ids"] != chunk_ids or meta["chunks_sha256"] != chunks_sha256:
        raise DenseUnavailable(f"vectors for {model} were built from a different index; run make embed")
    return np.load(npy_path)


@dataclass
class DenseLeg:
    """Embeds each query and searches the store; any failure or timeout raises DenseUnavailable."""

    embedder: Embedder
    store: VectorStore
    min_similarity: float
    limit: int = 8
    timeout_s: float = 1.5

    def search(self, queries: list[str]) -> list[list[tuple[str, float]]]:
        pool = ThreadPoolExecutor(max_workers=max(len(queries), 1))
        try:
            futures = [pool.submit(self.embedder.embed_query, q) for q in queries]
            vectors = [f.result(timeout=self.timeout_s) for f in futures]
        except FutureTimeout as exc:
            raise DenseUnavailable(f"query embedding exceeded {self.timeout_s}s") from exc
        except DenseUnavailable:
            raise
        except Exception as exc:  # API, network or quota errors: fall back, never fail the turn
            raise DenseUnavailable(f"query embedding failed: {type(exc).__name__}") from exc
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return [
            [hit for hit in self.store.search(v, self.limit) if hit[1] >= self.min_similarity]
            for v in vectors
        ]
