"""Build the index from corpus/ (M1; ACCEPTANCE_TESTS §0, ING-01..03).

Writes:
  data/index/chunks.jsonl    one record per section chunk (text the model sees, metadata, tables)
  data/index/bboxes.json     chunk_id -> one PDF-point box per text character (None for separators)
  data/index/manifest.json   corpus checksums, page sizes, index hashes and the ingest report
  data/derived/pages/*.png   page images for the evidence spotlight (skipped with --no-pages)

The three data/index files are deterministic: the same PDFs always give byte-identical output.
Page images are not compared byte for byte, because PDF renderers differ slightly across platforms.

Usage: uv run python -m app.ingest.build_index [--no-pages]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from app.ingest import flags
from app.ingest.chunk import Chunk, make_chunks
from app.ingest.extract import IngestError, extract_document
from app.ingest.render_pages import DPI, pixel_size, render_page
from tools import corpus_manifest

ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = ROOT / "data" / "index"
PAGES_DIR = ROOT / "data" / "derived" / "pages"
SCHEMA_VERSION = 1


def _dump(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(
    documents: list[tuple[str, Path]],
    index_dir: Path,
    pages_dir: Path | None,
    corpus_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract, chunk and write the index for (doc_id, pdf) pairs; return the manifest."""
    chunks: list[Chunk] = []
    report: list[dict[str, Any]] = []
    doc_info: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    for doc_id, path in documents:
        doc = extract_document(path, doc_id)
        heading, doc_chunks = make_chunks(doc)
        if not doc_chunks:
            raise IngestError(f"{path.name}: no numbered sections found (0 chunks)")
        chunks.extend(doc_chunks)
        report.extend(doc.flags)
        doc_info.append({"doc_id": doc_id, "file": path.name, **heading})
        for page in doc.pages:
            if page.furniture:
                report.append(
                    {
                        "type": "page_furniture",
                        "doc_id": doc_id,
                        "pdf_page": page.number,
                        "lines": page.furniture,
                    }
                )
            png = f"{doc_id}-p{page.number}.png"
            width_px, height_px = pixel_size(page.width, page.height)
            if pages_dir is not None:
                size = render_page(path, page.number, pages_dir / png)
                if size != (width_px, height_px):
                    raise IngestError(f"{png}: rendered {size}, expected {(width_px, height_px)}")
            pages.append(
                {
                    "doc_id": doc_id,
                    "pdf_page": page.number,
                    "printed_label": page.printed_label,
                    "png": png,
                    "width_pt": page.width,
                    "height_pt": page.height,
                    "dpi": DPI,
                    "width_px": width_px,
                    "height_px": height_px,
                }
            )
    for chunk in chunks:
        # Headings and titles also reach retrieval and the model (§4.1 step 3), so they are scanned too.
        scanned = "\n".join((chunk.doc_title, chunk.doc_subtitle, chunk.section, chunk.text))
        for match in flags.instruction_matches(scanned):
            report.append({"type": "instruction_like_text", "chunk_id": chunk.chunk_id, "match": match})

    chunks_bytes = b"".join(
        (json.dumps(c.record(), ensure_ascii=False) + "\n").encode("utf-8") for c in chunks
    )
    # One compact line per chunk keeps the file small and diffs readable.
    bboxes_lines = [f"{json.dumps(c.chunk_id)}: {json.dumps(c.boxes, separators=(',', ':'))}" for c in chunks]
    bboxes_bytes = ("{\n" + ",\n".join(bboxes_lines) + "\n}\n").encode("utf-8")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "corpus": corpus_entries,
        "documents": doc_info,
        "chunk_count": len(chunks),
        "chunk_ids": [c.chunk_id for c in chunks],
        "chunks_sha256": _sha256(chunks_bytes),
        "bboxes_sha256": _sha256(bboxes_bytes),
        "pages": pages,
        "ingest_report": report,
    }
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "chunks.jsonl").write_bytes(chunks_bytes)
    (index_dir / "bboxes.json").write_bytes(bboxes_bytes)
    (index_dir / "manifest.json").write_bytes(_dump(manifest))
    return manifest


def corpus_documents() -> tuple[list[tuple[str, Path]], list[dict[str, Any]]]:
    """The production corpus, in corpus_manifest.json order, after checking every SHA-256."""
    problems = corpus_manifest.verify()
    if problems:
        raise IngestError("corpus does not match corpus_manifest.json: " + "; ".join(problems))
    entries = json.loads(corpus_manifest.MANIFEST_PATH.read_text(encoding="utf-8"))["documents"]
    return [(e["doc_id"], corpus_manifest.CORPUS_DIR / e["file"]) for e in entries], entries


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--no-pages", action="store_true", help="skip rendering the page images")
    args = parser.parse_args(argv)
    try:
        documents, entries = corpus_documents()
        manifest = build(documents, INDEX_DIR, None if args.no_pages else PAGES_DIR, entries)
    except IngestError as exc:
        print(f"index: FAILED - {exc}", file=sys.stderr)
        return 1
    print(
        f"index: {manifest['chunk_count']} chunks from {len(documents)} PDFs -> {INDEX_DIR.relative_to(ROOT)}"
    )
    for item in manifest["ingest_report"]:
        print(f"index: REVIEW - {json.dumps(item, ensure_ascii=False)}", file=sys.stderr)
    if not manifest["ingest_report"]:
        print("index: ingest report clean (0 hidden-text, 0 instruction-like, 0 furniture flags)")
    if any(item["type"] == "hidden_text" for item in manifest["ingest_report"]):
        # Hidden text is removed from chunks; on the production corpus that must be a human decision.
        print(
            "index: FAILED - hidden text was removed from the production corpus; review it", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
