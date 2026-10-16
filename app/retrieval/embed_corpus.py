"""`make embed`: corpus vectors for one embedding model → data/index/embeddings/<model>.{npy,json}.

This is a LIVE Vertex AI call, paid from the GCP trial credit (16 short chunks, a fraction of a cent;
ADR §3.2 rows 1e/2f). `make embed` runs the GCP guard first, so it only ever touches $GCP_PROJECT. It
prints what it will do and refuses to call Google without --yes (owner approval the first
time). The .json sidecar records the chunk IDs and chunks.jsonl hash, so stale vectors are refused at
load time.

Usage: uv run python -m app.retrieval.embed_corpus --model gemini-embedding-2 [--yes]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

from app.retrieval.dense import EMBEDDINGS_DIR, MODELS, VertexEmbedder
from app.retrieval.retriever import index_text

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "data" / "index"
PRICE_PER_MILLION = {"gemini-embedding-001": 0.15, "gemini-embedding-2": 0.20}  # ADR §3.2 rows 1e, 2f


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", required=True, choices=MODELS)
    parser.add_argument("--yes", action="store_true", help="confirm the live Vertex AI call")
    args = parser.parse_args(argv)

    chunks = [json.loads(line) for line in (INDEX / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    manifest = json.loads((INDEX / "manifest.json").read_text(encoding="utf-8"))
    characters = sum(len(index_text(c)) for c in chunks)
    estimate = characters / 4 / 1_000_000 * PRICE_PER_MILLION[args.model]  # about 4 characters per token
    project = os.environ.get("GCP_PROJECT", "")
    location = os.environ.get("VERTEX_LOCATION", "global")
    target = f"{project or '<GCP_PROJECT unset>'}/{location}"
    print(f"embed: {len(chunks)} chunks (~{characters // 4} tokens) with {args.model} in {target}")
    print(f"embed: estimated cost ${estimate:.5f} from the GCP trial credit (not the Claude budget)")
    if not args.yes:
        print("embed: dry run. Re-run with --yes for the live call (owner approval needed the first time).")
        return 0

    embedder = VertexEmbedder(args.model, project=project, location=location, timeout_s=30.0)
    vectors = np.stack([embedder.embed_document(c["doc_subtitle"], index_text(c)) for c in chunks]).astype(
        np.float32
    )
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    np.save(EMBEDDINGS_DIR / f"{args.model}.npy", vectors)
    meta = {
        "model": args.model,
        "dim": int(vectors.shape[1]),
        "location": location,
        "chunk_ids": [c["chunk_id"] for c in chunks],
        "chunks_sha256": manifest["chunks_sha256"],
    }
    (EMBEDDINGS_DIR / f"{args.model}.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    written = f"{EMBEDDINGS_DIR.relative_to(ROOT).as_posix()}/{args.model}.npy"
    print(f"embed: wrote {written} ({vectors.shape[0]}x{vectors.shape[1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
