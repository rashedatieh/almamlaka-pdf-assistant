"""Evidence spotlight API (PROJECT_PLAN §5.3): the real PDF page image with a cited quote highlighted.

  GET /api/sources/page/{doc_id}/{page}.png   the rendered page (data/derived/pages, app.ingest.render_pages)
  GET /api/sources/spotlight?chunk=&start=&end=
      -> {chunkId, docId, pdfPage, section, imageUrl, width, height, boxes: [{x, y, w, h}]}

Boxes come only from the index (data/index/bboxes.json): one PDF-point box (x0, top, x1, bottom, origin at
the top-left) per character of the chunk text, None for separators the extractor inserted. The span
[start, end) is the one app.pipeline.render.citation sent with the citation; characters are merged into one
rectangle per printed line and scaled to image pixels with the page's manifest size (dpi / 72).

Both routes need the reviewer invite when one is configured (401 otherwise). The integrator mounts the
router with `app.include_router(make_router(svc.invited))`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.textnorm import locate

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "index"
PAGES = ROOT / "data" / "derived" / "pages"
DOC_IDS = frozenset({"OVR", "BUD", "GOV"})
PAD_PT = 1.5  # breathing room around each highlighted line, in PDF points
IMMUTABLE = "private, max-age=31536000, immutable"  # private: the page sits behind the invite cookie

Box = tuple[float, float, float, float]


def merge_lines(boxes: list[Box | None]) -> list[Box]:
    """Merge per-character boxes into one box per printed line, in reading order.

    A character starts a new line when it does not overlap the current line vertically by at least half
    its height, or when it sits left of where the line began (a wrapped paragraph). Separators (None)
    never extend a line; cells of one table row stay one rectangle.
    """
    lines: list[list[float]] = []
    for box in boxes:
        if box is None:
            continue
        x0, top, x1, bottom = box
        if lines:
            line = lines[-1]
            overlap = min(bottom, line[3]) - max(top, line[1])
            if overlap >= 0.5 * (bottom - top) and x0 >= line[0] - 0.5:
                line[0], line[1], line[2], line[3] = (
                    min(line[0], x0),
                    min(line[1], top),
                    max(line[2], x1),
                    max(line[3], bottom),
                )
                continue
        lines.append([x0, top, x1, bottom])
    return [(a, b, c, d) for a, b, c, d in lines]


class SourceIndex:
    """Chunks, character boxes and page sizes, loaded once from data/index."""

    def __init__(self, index_dir: Path = INDEX, pages_dir: Path = PAGES) -> None:
        lines = (index_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        self.chunks: dict[str, dict[str, Any]] = {c["chunk_id"]: c for c in map(json.loads, lines)}
        self.boxes: dict[str, list[Box | None]] = json.loads(
            (index_dir / "bboxes.json").read_text(encoding="utf-8")
        )
        manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
        self.pages: dict[tuple[str, int], dict[str, Any]] = {
            (p["doc_id"], p["pdf_page"]): p for p in manifest["pages"] if p["doc_id"] in DOC_IDS
        }
        self.version = manifest["bboxes_sha256"][:12]  # busts the immutable cache when the index changes
        self.pages_dir = pages_dir

    def page_file(self, doc_id: str, page: int) -> Path | None:
        meta = self.pages.get((doc_id, page))
        if meta is None:
            return None
        # The file name comes from the manifest, never from the request.
        path = self.pages_dir / meta["png"]
        return path if path.is_file() else None

    def spotlight(self, chunk_id: str, start: int, end: int) -> dict[str, Any]:
        chunk = self.chunks[chunk_id]
        meta = self.pages[(chunk["doc_id"], chunk["pdf_page"])]
        scale_x = meta["width_px"] / meta["width_pt"]
        scale_y = meta["height_px"] / meta["height_pt"]
        rects = []
        for x0, top, x1, bottom in merge_lines(self.boxes[chunk_id][start:end]):
            left = max(0.0, (x0 - PAD_PT) * scale_x)
            upper = max(0.0, (top - PAD_PT) * scale_y)
            right = min(float(meta["width_px"]), (x1 + PAD_PT) * scale_x)
            lower = min(float(meta["height_px"]), (bottom + PAD_PT) * scale_y)
            rects.append(
                {
                    "x": round(left, 1),
                    "y": round(upper, 1),
                    "w": round(right - left, 1),
                    "h": round(lower - upper, 1),
                }
            )
        return {
            "chunkId": chunk_id,
            "docId": chunk["doc_id"],
            "pdfPage": chunk["pdf_page"],
            "section": chunk["section"],
            "imageUrl": f"/api/sources/page/{chunk['doc_id']}/{chunk['pdf_page']}.png?v={self.version}",
            "width": meta["width_px"],
            "height": meta["height_px"],
            "boxes": rects,
        }


def make_router(invited: Callable[[Request], bool], index: SourceIndex | None = None) -> APIRouter:
    src = index or SourceIndex()
    router = APIRouter(prefix="/api/sources")

    def guard(request: Request) -> None:
        if not invited(request):
            raise HTTPException(401, "invite required")

    @router.get("/page/{doc_id}/{page}.png")
    def page_image(doc_id: str, page: str, request: Request) -> FileResponse:
        guard(request)
        if doc_id not in DOC_IDS or not page.isascii() or not page.isdigit() or len(page) > 3:
            raise HTTPException(404, "page not found")
        path = src.page_file(doc_id, int(page))
        if path is None:
            raise HTTPException(404, "page not found")
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": IMMUTABLE})

    @router.get("/spotlight")
    def spotlight(
        request: Request,
        chunk: str = Query(max_length=40),
        start: int | None = Query(default=None, ge=0),
        end: int | None = Query(default=None, ge=0),
        quote: str | None = Query(default=None, max_length=2000),
    ) -> dict[str, Any]:
        guard(request)
        record = src.chunks.get(chunk)
        if record is None or chunk not in src.boxes:
            raise HTTPException(404, "unknown chunk")
        text = record["text"]
        if start is None or end is None or end <= start:
            # Citations without offsets (older saved data): find the quote with the verifier's own rule.
            span = locate(quote, text) if quote else None
            if span is None:
                raise HTTPException(400, "start and end, or a quote found in the chunk, are required")
            start, end = span
        if end > len(text):
            raise HTTPException(400, "span outside the chunk text")
        return src.spotlight(chunk, start, end)

    return router
