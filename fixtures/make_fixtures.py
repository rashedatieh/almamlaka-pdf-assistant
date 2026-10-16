"""Generate the synthetic fixture PDFs into fixtures/pdf/ (ACCEPTANCE_TESTS "Synthetic fixtures").

Every fixture is fictional and labelled "TEST FIXTURE — fictional" on every page. Output is
reproducible: ReportLab runs with invariant=1, so the same code always writes the same bytes.

  FX-3  printed page labels differ from PDF page numbers (J-08): cover, ii, iii, then "1"
  FX-4  a scanned page: an image of text with no text layer; ingestion must fail loudly

FX-1, FX-2 and FX-5 (injection and Arabic fixtures) are added at M5 (PROJECT_PLAN §7.4).

Usage: uv run python -m fixtures.make_fixtures
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

FIXTURES_DIR = Path(__file__).resolve().parent / "pdf"
LABEL = "TEST FIXTURE — fictional"
WIDTH, HEIGHT = letter
MARGIN = 72


def _canvas(target: Path | io.BytesIO) -> canvas.Canvas:
    return canvas.Canvas(
        target if isinstance(target, io.BytesIO) else str(target), pagesize=letter, invariant=1
    )


def _furniture(c: canvas.Canvas, footer: str | None) -> None:
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN, HEIGHT - 30, LABEL)
    if footer:
        c.drawCentredString(WIDTH / 2, 30, footer)


def _section(c: canvas.Canvas, heading: str, body: str) -> None:
    c.setFont("Helvetica-Bold", 18)
    c.drawString(MARGIN, HEIGHT - 110, heading)
    c.setFont("Helvetica", 10.5)
    c.drawString(MARGIN, HEIGHT - 140, body)


def make_fx3(target: Path | io.BytesIO) -> None:
    """Four pages: cover (no label), ii, iii, and a page printed "1", with matching /PageLabels."""
    c = _canvas(target)
    _furniture(c, None)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGIN, HEIGHT - 110, "Fixture Handbook")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN, HEIGHT - 140, "Page-label test (FX-3)")
    c.showPage()
    pages = [
        ("ii", "1. Preface", "This fictional handbook exists only to test page labels."),
        ("iii", "2. Contents", "Section 3 starts on the page printed as 1."),
        ("1", "3. Remote Work", "Staff may work remotely two days per week."),
    ]
    for footer, heading, body in pages:
        _furniture(c, footer)
        _section(c, heading, body)
        c.showPage()
    # ReportLab takes the style by name (PDFPageLabel.__convertible__), not by its one-letter code.
    c.addPageLabel(0, prefix="")
    c.addPageLabel(1, style="ROMAN_LOWER", start=2)
    c.addPageLabel(3, style="ARABIC", start=1)
    c.save()


def make_fx4(target: Path | io.BytesIO) -> None:
    """One page that is only an image of text: no text layer at all, not even the fixture label."""
    image = Image.new("L", (1200, 400), 255)
    draw = ImageDraw.Draw(image)
    draw.text((40, 40), "TEST FIXTURE - fictional", fill=0)
    draw.text((40, 120), "Scanned page: this text is an image with no text layer.", fill=0)
    c = _canvas(target)
    c.drawImage(ImageReader(image), MARGIN, HEIGHT - 300, width=WIDTH - 2 * MARGIN, height=160)
    c.showPage()
    c.save()


FIXTURES = {"FX-3.pdf": make_fx3, "FX-4.pdf": make_fx4}


def main() -> int:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, make in FIXTURES.items():
        make(FIXTURES_DIR / name)
        print(f"fixtures: wrote {(FIXTURES_DIR / name).relative_to(FIXTURES_DIR.parent.parent).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
