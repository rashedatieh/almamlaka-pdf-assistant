"""Render PDF pages to PNG for the evidence spotlight (PROJECT_PLAN §5.3; pdfplumber + pypdfium2)."""

from __future__ import annotations

from pathlib import Path

import pdfplumber

DPI = 144


def pixel_size(width_pt: float, height_pt: float, dpi: int = DPI) -> tuple[int, int]:
    """Image size in pixels for a page of the given size in points (72 points per inch)."""
    return round(width_pt * dpi / 72), round(height_pt * dpi / 72)


def render_page(pdf_path: Path, page_number: int, out_path: Path, dpi: int = DPI) -> tuple[int, int]:
    """Write one page as a 256-colour PNG and return its (width, height) in pixels."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pdfplumber.open(pdf_path) as pdf:
        image = pdf.pages[page_number - 1].to_image(resolution=dpi)
        image.save(out_path, format="PNG")
        return image.original.size
