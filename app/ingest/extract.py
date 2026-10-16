"""Read one PDF into text lines and tables with a bounding box per character (M1).

pdfplumber supplies characters, lines and tables; pypdf supplies /PageLabels and text render modes.
PyMuPDF is not used (AGPL; docs/ENGINEERING_RULES.md non-negotiable 10). The PDF is only read, never modified.

Hidden characters (see flags.py) are left out of the extracted text and reported, so chunk text is
what a reader sees on the page. A page without a text layer stops ingestion: there is no OCR.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader

from app.ingest import flags

Box = tuple[float, float, float, float]  # x0, top, x1, bottom in PDF points, origin at top-left
# Lines entirely inside these top/bottom bands are running headers or footers (page furniture), but
# only if they repeat on another page or read as a page number; otherwise they stay as content.
FURNITURE_MARGIN = 0.06
MAX_X_NEIGHBOURS = 400  # bound for the overprint sweep (see _check_no_overprint)
_DASHES = "-" + chr(0x2013) + chr(0x2014) + " "  # hyphen, en dash, em dash and space around a page number
PAGE_NUMBER_RE = re.compile(
    rf"^[{_DASHES}]*(page\s+)?(\d+|[ivxlcdm]+)(\s*(/|of)\s*\d+)?[{_DASHES}]*$", re.IGNORECASE
)


class IngestError(Exception):
    """The PDF cannot be indexed as it is. Ingestion stops instead of guessing."""


@dataclass(frozen=True)
class Glyph:
    """One character of extracted text. `box` is None for separators the extractor inserted."""

    text: str
    box: Box | None


SPACE = Glyph(" ", None)


@dataclass
class Line:
    glyphs: list[Glyph]
    top: float
    bottom: float
    size: float  # largest font size on the line
    bold: bool  # every glyph uses a bold font

    @property
    def text(self) -> str:
        return "".join(g.text for g in self.glyphs)


@dataclass
class Table:
    top: float
    rows: list[list[list[Glyph]]]  # rows -> cells -> glyphs; row 0 is the header

    def cells(self) -> list[list[str]]:
        return [["".join(g.text for g in cell) for cell in row] for row in self.rows]


@dataclass
class Page:
    number: int  # 1-based PDF page index
    width: float
    height: float
    printed_label: str | None  # from /PageLabels only; None when the PDF defines none
    lines: list[Line]  # body lines outside tables, top to bottom
    tables: list[Table]
    furniture: list[str]  # header/footer lines left out of the text


@dataclass
class Document:
    doc_id: str
    path: Path
    pages: list[Page]
    flags: list[dict[str, Any]]


def _box(char: dict[str, Any]) -> Box:
    return (round(char["x0"], 2), round(char["top"], 2), round(char["x1"], 2), round(char["bottom"], 2))


def align(text: str, chars: list[dict[str, Any]]) -> list[Glyph]:
    """Pair each character of pdfplumber's line text with the box of the char it came from.

    pdfplumber infers spaces from gaps between glyphs; those spaces get no box.
    """
    glyphs: list[Glyph] = []
    i = 0
    for char in chars:
        piece = char["text"]
        while text.startswith(" ", i) and not piece.startswith(" "):
            glyphs.append(SPACE)
            i += 1
        if not text.startswith(piece, i):
            # pdfplumber expands ligatures (U+FB01 "ﬁ" -> "fi") in the line text but not in the char.
            piece = unicodedata.normalize("NFKC", piece)
        if not text.startswith(piece, i):
            raise IngestError(f"cannot align extracted text near {text[i : i + 30]!r}")
        glyphs.extend(Glyph(c, _box(char)) for c in piece)
        i += len(piece)
    if text[i:].strip():
        raise IngestError(f"unaligned trailing text {text[i:]!r}")
    return glyphs


def _line(raw: dict[str, Any]) -> Line:
    visible = [c for c in raw["chars"] if c["text"].strip()]
    return Line(
        glyphs=align(raw["text"], raw["chars"]),
        top=round(raw["top"], 2),
        bottom=round(raw["bottom"], 2),
        size=round(max(c["size"] for c in visible), 2),
        bold=all("Bold" in c["fontname"] for c in visible),
    )


def _cell_glyphs(page: Any, bbox: Box | None) -> list[Glyph]:
    if bbox is None:
        return []
    glyphs: list[Glyph] = []
    for raw in page.within_bbox(bbox).extract_text_lines(return_chars=True, strip=True):
        if glyphs:
            glyphs.append(SPACE)
        glyphs.extend(_line(raw).glyphs)
    return glyphs


def _tables(page: Any) -> tuple[list[Table], list[Box]]:
    tables: list[Table] = []
    boxes: list[Box] = []
    for found in page.find_tables():
        rows = [[_cell_glyphs(page, cell) for cell in row.cells] for row in found.rows]
        table = Table(top=round(found.bbox[1], 2), rows=rows)
        expected = [[" ".join((cell or "").split()) for cell in row] for row in found.extract()]
        if table.cells() != expected:
            raise IngestError(f"page {page.page_number}: table cells disagree with pdfplumber's extract()")
        tables.append(table)
        boxes.append(found.bbox)
    return tables, boxes


def _is_furniture(text: str, repeats: int) -> bool:
    """A margin line is a running header/footer if it repeats on other pages or is a page number."""
    return repeats > 1 or bool(PAGE_NUMBER_RE.match(" ".join(text.split())))


def _check_no_overprint(page: Any) -> None:
    """Two different characters drawn on the same spot stop ingestion.

    A reader sees at most one of them, so the other is hidden text, and its box still shows the
    visible glyph's ink. Overprinting the same character (fake bold) is allowed.
    All characters on the page are swept by x position, so a glyph nudged off its line is still compared.
    Ordinary text never overlaps by a quarter of a glyph; kerning overlaps are far smaller.
    """
    chars = sorted((c for c in page.chars if c["text"].strip()), key=lambda c: c["x0"])
    for i, a in enumerate(chars):
        area_a = (a["x1"] - a["x0"]) * (a["bottom"] - a["top"])
        for compared, b in enumerate(chars[i + 1 :]):
            if b["x0"] >= a["x1"]:
                break  # sorted by x0: nothing further right can overlap `a`
            if compared > MAX_X_NEIGHBOURS:
                # A normal glyph shares its x-span with one glyph per line at most (a few hundred lines);
                # anything wider is an abnormal glyph, and comparing it with everything would be quadratic.
                raise IngestError(f"page {page.page_number}: abnormally wide glyph {a['text']!r}")
            overlap_x = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
            overlap_y = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
            smaller = min(area_a, (b["x1"] - b["x0"]) * (b["bottom"] - b["top"]))
            if (
                a["text"] != b["text"]
                and smaller > 0
                and overlap_y > 0
                and overlap_x * overlap_y > 0.25 * smaller
            ):
                raise IngestError(
                    f"page {page.page_number}: overlapping text ({a['text']!r} drawn over {b['text']!r})"
                )


def _check_coverage(page: Any, used: list[Glyph]) -> None:
    """Every visible character must end up in a line, a table cell or the header/footer list."""
    placed = {g.box for g in used if g.box}
    missing = [c for c in page.chars if c["text"].strip() and _box(c) not in placed]
    if missing:
        text = "".join(c["text"] for c in sorted(missing, key=lambda c: (round(c["top"]), c["x0"])))
        raise IngestError(
            f"page {page.page_number}: text not placed in any line or table cell: {text[:80]!r}"
        )


def printed_labels(reader: PdfReader) -> list[str | None]:
    """Page labels from /PageLabels. Without that entry pypdf invents '1', '2', …, which are not
    printed labels, so every page gets None (PROJECT_PLAN §1.3)."""
    if "/PageLabels" not in reader.trailer["/Root"]:
        return [None] * len(reader.pages)
    return [label or None for label in reader.page_labels]


def extract_document(path: Path, doc_id: str) -> Document:
    reader = PdfReader(path)
    if "/OCProperties" in reader.trailer["/Root"]:
        raise IngestError(
            f"{path.name}: optional content layers (/OCProperties) present; layer visibility is not modelled"
        )
    labels = printed_labels(reader)
    pages: list[Page] = []
    margins: list[list[Line]] = []  # lines in each page's header/footer band, decided after all pages
    report: list[dict[str, Any]] = []
    with pdfplumber.open(path) as pdf:
        for number, plumber_page in enumerate(pdf.pages, start=1):
            if not plumber_page.chars:
                raise IngestError(f"{path.name}: page {number} has no text layer; OCR disabled")
            modes = flags.invisible_render_modes(reader.pages[number - 1])
            if modes:
                raise IngestError(
                    f"{path.name}: page {number} uses invisible text render modes {sorted(modes)}"
                )

            detector = flags.HiddenTextDetector(plumber_page)
            hidden = plumber_page.filter(detector.is_hidden)
            if hidden.chars:
                text = " / ".join(raw["text"] for raw in hidden.extract_text_lines(strip=True))
                report.append({"type": "hidden_text", "doc_id": doc_id, "pdf_page": number, "text": text})
            # Fake bold (the same glyph overprinted) would otherwise read twice ("BBoolldd").
            page = plumber_page.filter(lambda obj, d=detector: not d.is_hidden(obj)).dedupe_chars()

            tables, table_boxes = _tables(page)
            # Prose is read with the table regions cut out, so a line can never merge with cell text.
            # Text inside a table's outline but in no cell is caught by the coverage check below.
            body = page
            for box in table_boxes:
                body = body.outside_bbox(box)
            height = float(page.height)
            lines: list[Line] = []
            band: list[Line] = []
            for raw in body.extract_text_lines(return_chars=True, strip=True):
                line = _line(raw)
                in_band = line.bottom <= height * FURNITURE_MARGIN or line.top >= height * (
                    1 - FURNITURE_MARGIN
                )
                (band if in_band else lines).append(line)
            cell_glyphs = [g for t in tables for row in t.rows for cell in row for g in cell]
            _check_no_overprint(page)
            _check_coverage(page, [*cell_glyphs, *(g for line in [*lines, *band] for g in line.glyphs)])
            margins.append(band)
            pages.append(
                Page(
                    number=number,
                    width=float(page.width),
                    height=height,
                    printed_label=labels[number - 1],
                    lines=lines,
                    tables=tables,
                    furniture=[],
                )
            )

    repeats = Counter(" ".join(line.text.split()) for band in margins for line in band)
    for page, band in zip(pages, margins, strict=True):
        for line in band:
            if _is_furniture(line.text, repeats[" ".join(line.text.split())]):
                page.furniture.append(line.text)
            else:
                page.lines.append(line)  # real content that happens to sit near the edge
        page.lines.sort(key=lambda line: line.top)
    return Document(doc_id=doc_id, path=path, pages=pages, flags=report)
