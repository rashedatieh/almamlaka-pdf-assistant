"""Turn extracted pages into section chunks (PROJECT_PLAN §3.1 "Chunking"; ACCEPTANCE_TESTS §0).

One chunk per numbered section, bounded by the page; the ID is `{DOC}-p{page}-s{section}`. Lines on
page 1 above the first heading are the document title and subtitle. A section heading is a bold line
of at least 16 pt reading "N. Title".

Chunk text is what the answer model sees and what citation quotes must match (J-02):
  * Lines of one paragraph are joined with a space; paragraphs are separated by a newline.
  * Each table row becomes one line with its cells joined by " | ", header row first.
`boxes[i]` is the PDF-point box of text[i], or None for an inserted space, " | " or newline. The
evidence spotlight (M4) highlights a quote from these boxes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.ingest.extract import SPACE, Box, Document, Glyph, IngestError, Line, Table

HEADING_RE = re.compile(r"^(\d+)\.\s+(\S.*)$")
HEADING_MIN_SIZE = 16.0
# A gap between lines larger than this fraction of the font size starts a new paragraph.
PARAGRAPH_GAP = 0.8
KEY_VALUE_RE = re.compile(r"^[^:\n]{1,40}: \S")
NEWLINE = Glyph("\n", None)
CELL_SEPARATOR = [SPACE, Glyph("|", None), SPACE]


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    file: str
    pdf_page: int
    printed_label: str | None
    section: str  # "1. Introduction", as in ACCEPTANCE_TESTS §0
    section_number: int
    section_title: str
    doc_title: str
    doc_subtitle: str
    kind: str  # prose | key-value | table | prose+table
    text: str
    tables: list[dict[str, Any]]
    boxes: list[Box | None] = field(repr=False)

    def record(self) -> dict[str, Any]:
        """The chunks.jsonl record: everything except the boxes, which go to bboxes.json."""
        return {k: v for k, v in self.__dict__.items() if k != "boxes"}


@dataclass
class _Segment:
    page: int
    printed_label: str | None
    number: int
    heading: str
    title: str
    items: list[Line | Table] = field(default_factory=list)


def _heading(line: Line) -> re.Match[str] | None:
    if not (line.bold and line.size >= HEADING_MIN_SIZE):
        return None
    return HEADING_RE.match(" ".join(line.text.split()))


def _join(pieces: list[list[Glyph]], separator: list[Glyph]) -> list[Glyph]:
    out: list[Glyph] = []
    for piece in pieces:
        if out:
            out.extend(separator)
        out.extend(piece)
    return out


def _body(items: list[Line | Table]) -> tuple[list[Glyph], list[dict[str, Any]], str]:
    """Text glyphs, structured tables and kind of one section segment."""
    pieces: list[list[Glyph]] = []
    prose: list[str] = []
    tables: list[dict[str, Any]] = []
    paragraph: list[Glyph] = []
    previous: Line | None = None
    for item in items:
        if isinstance(item, Line):
            if paragraph and previous and item.top - previous.bottom < PARAGRAPH_GAP * item.size:
                paragraph += [SPACE, *item.glyphs]
            else:
                if paragraph:
                    pieces.append(paragraph)
                    prose.append("".join(g.text for g in paragraph))
                paragraph = list(item.glyphs)
            previous = item
            continue
        if paragraph:
            pieces.append(paragraph)
            prose.append("".join(g.text for g in paragraph))
            paragraph, previous = [], None
        pieces.extend(_join(row, CELL_SEPARATOR) for row in item.rows)
        cells = item.cells()
        tables.append({"header": cells[0], "rows": cells[1:]})
    if paragraph:
        pieces.append(paragraph)
        prose.append("".join(g.text for g in paragraph))

    if tables:
        kind = "prose+table" if prose else "table"
    elif len(prose) >= 2 and all(KEY_VALUE_RE.match(p) for p in prose):
        kind = "key-value"
    else:
        kind = "prose"
    return _join(pieces, [NEWLINE]), tables, kind


def make_chunks(doc: Document) -> tuple[dict[str, str], list[Chunk]]:
    """Return ({"title", "subtitle"}, chunks) for one document, in page and section order."""
    preamble: list[str] = []
    segments: list[_Segment] = []
    current: _Segment | None = None
    for page in doc.pages:
        items: list[Line | Table] = sorted([*page.lines, *page.tables], key=lambda item: item.top)
        for item in items:
            match = _heading(item) if isinstance(item, Line) else None
            if match:
                current = _Segment(
                    page=page.number,
                    printed_label=page.printed_label,
                    number=int(match.group(1)),
                    heading=match.group(0),
                    title=match.group(2),
                )
                segments.append(current)
            elif current is None:
                if page.number != 1 or isinstance(item, Table):
                    raise IngestError(f"{doc.path.name} p{page.number}: content before the first heading")
                preamble.append(" ".join(item.text.split()))
            else:
                if current.page != page.number:  # a section continuing on the next page
                    current = _Segment(
                        page=page.number,
                        printed_label=page.printed_label,
                        number=current.number,
                        heading=current.heading,
                        title=current.title,
                    )
                    segments.append(current)
                current.items.append(item)

    if len(preamble) > 2:
        raise IngestError(f"{doc.path.name}: unexpected text above the first heading: {preamble[2:]}")
    title = preamble[0] if preamble else ""
    subtitle = preamble[1] if len(preamble) > 1 else ""

    chunks: list[Chunk] = []
    for index, seg in enumerate(segments):
        if not seg.items:
            continues = any(s.number == seg.number for s in segments[index + 1 :])
            if continues:
                continue  # a heading at the foot of a page; its text starts on the next page
            raise IngestError(f"{doc.path.name} p{seg.page}: section {seg.heading!r} has no text")
        glyphs, tables, kind = _body(seg.items)
        chunk_id = f"{doc.doc_id}-p{seg.page}-s{seg.number}"
        if any(c.chunk_id == chunk_id for c in chunks):
            raise IngestError(f"duplicate chunk ID {chunk_id}")
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                file=doc.path.name,
                pdf_page=seg.page,
                printed_label=seg.printed_label,
                section=seg.heading,
                section_number=seg.number,
                section_title=seg.title,
                doc_title=title,
                doc_subtitle=subtitle,
                kind=kind,
                text="".join(g.text for g in glyphs),
                tables=tables,
                boxes=[g.box for g in glyphs],
            )
        )
    return {"title": title, "subtitle": subtitle}, chunks
