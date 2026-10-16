"""M1 index build: deterministic, committed copy current, character boxes and page images correct."""

from __future__ import annotations

import json
from pathlib import Path

import pdfplumber
import pytest
from PIL import Image

from app.ingest import build_index

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "data" / "index"
PAGES = ROOT / "data" / "derived" / "pages"
FILES = ("chunks.jsonl", "bboxes.json", "manifest.json")


@pytest.fixture(scope="module")
def fresh_build(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("index")
    documents, entries = build_index.corpus_documents()
    build_index.build(documents, out, None, entries)
    return out


def test_committed_index_is_current(fresh_build: Path) -> None:
    # A stale data/index means `make index` was not re-run after an ingestion change. Equality with a
    # fresh build in another process also proves the build is deterministic.
    for name in FILES:
        assert (INDEX / name).read_bytes() == (fresh_build / name).read_bytes(), f"re-run make index ({name})"


def test_manifest_hashes_match_the_files() -> None:
    import hashlib

    manifest = json.loads((INDEX / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["chunks_sha256"] == hashlib.sha256((INDEX / "chunks.jsonl").read_bytes()).hexdigest()
    assert manifest["bboxes_sha256"] == hashlib.sha256((INDEX / "bboxes.json").read_bytes()).hexdigest()


def _chunks() -> list[dict]:
    return [json.loads(line) for line in (INDEX / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]


def test_every_box_points_at_the_same_character_on_the_page() -> None:
    boxes = json.loads((INDEX / "bboxes.json").read_text(encoding="utf-8"))
    for chunk in _chunks():
        chunk_boxes = boxes[chunk["chunk_id"]]
        assert len(chunk_boxes) == len(chunk["text"]), chunk["chunk_id"]
        with pdfplumber.open(ROOT / "corpus" / chunk["file"]) as pdf:
            page_chars = {
                (round(c["x0"], 2), round(c["top"], 2), round(c["x1"], 2), round(c["bottom"], 2)): c["text"]
                for c in pdf.pages[chunk["pdf_page"] - 1].chars
            }
        for char, box in zip(chunk["text"], chunk_boxes, strict=True):
            if box is None:
                assert char in " |\n", f"{chunk['chunk_id']}: unboxed {char!r}"
            else:
                assert page_chars[tuple(box)] == char, f"{chunk['chunk_id']}: {char!r} at {box}"
        boxed = sum(box is not None for box in chunk_boxes)
        assert boxed >= 0.75 * len(chunk["text"]), chunk["chunk_id"]


def test_table_row_quote_stays_inside_its_row() -> None:
    # Groundwork for O-02: a quote from one budget-table row maps to boxes on that row only.
    chunk = next(c for c in _chunks() if c["chunk_id"] == "BUD-p1-s1")
    boxes = json.loads((INDEX / "bboxes.json").read_text(encoding="utf-8"))["BUD-p1-s1"]
    quote = "Q3 2027 | $400,000"
    start = chunk["text"].index(quote)
    quoted = [b for b in boxes[start : start + len(quote)] if b]
    with pdfplumber.open(ROOT / "corpus" / "Almamlaka_Budget_Timeline.pdf") as pdf:
        (table,) = pdf.pages[0].find_tables()
        row_index = [row[0] for row in table.extract()].index("Q3 2027")
        _, top, _, bottom = table.rows[row_index].bbox
    assert quoted and all(top <= b[1] and b[3] <= bottom for b in quoted)


def test_page_images_exist_with_the_recorded_size() -> None:
    manifest = json.loads((INDEX / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["pages"]) == 6
    for page in manifest["pages"]:
        with Image.open(PAGES / page["png"]) as image:
            assert image.size == (page["width_px"], page["height_px"]), page["png"]
        assert page["printed_label"] is None


def _ink(image: Image.Image, box: list[float], scale: float) -> float:
    """Share of dark pixels inside a PDF-point box on the rendered page."""
    x0, top, x1, bottom = (round(v * scale) for v in box)
    histogram = image.crop((x0, top, x1, bottom)).convert("L").histogram()  # 256 grey-level counts
    return sum(histogram[:128]) / max(sum(histogram), 1)


def test_page_images_show_each_chunks_text_where_its_boxes_say() -> None:
    # A PNG of the wrong page, or boxes on the wrong scale, has blank paper where the heading-side
    # text should be. Light fills (the corpus table rows) are not dark, so they don't fake ink.
    boxes = json.loads((INDEX / "bboxes.json").read_text(encoding="utf-8"))
    scale = 144 / 72
    for chunk in _chunks():
        if chunk["kind"] != "prose":
            continue  # table text may be white on navy; prose is black on white
        first_word = [b for b in boxes[chunk["chunk_id"]][:12] if b]
        with Image.open(PAGES / f"{chunk['doc_id']}-p{chunk['pdf_page']}.png") as image:
            span = [min(b[0] for b in first_word), min(b[1] for b in first_word)]
            span += [max(b[2] for b in first_word), max(b[3] for b in first_word)]
            assert _ink(image, span, scale) > 0.05, chunk["chunk_id"]
            blank = [span[0], span[1] + 400, span[2], span[3] + 400]  # well below the text
            assert _ink(image, blank, scale) < _ink(image, span, scale), chunk["chunk_id"]
