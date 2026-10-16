"""Ingest-time safety checks (PROJECT_PLAN §4.4 control 4; ACCEPTANCE ING-01, I-01, I-02; ADR-0001 D21).

Hidden text is judged on the rendered page, not guessed from colours. Each page is rendered with pdfium
(the same renderer as the spotlight images). A character is visible only if its box on that image contains
ink that stands out from the background around it. This one check catches everything a reader can't see:
white-on-white, transparency (ExtGState alpha, soft masks), clipping, opaque shapes painted over text,
white-stroke outlines and spot colours. Visible white text on a dark fill, like the corpus table headers,
passes. Tiny or off-page text is hidden too. Hidden characters are removed from chunk text and reported.
Known limit: text drawn over an image counts as visible, because the image gives its box ink.

Two drawing states stop ingestion outright, because pdfplumber can't say which characters they affect:
  * text render modes 3 and 7 (no glyph painted), anywhere in the page or its Form XObjects;
  * optional content (/OCProperties), whose layers may be switched off.

Instruction-like text: phrases that try to steer an AI system, matched on Arabic-normalised text so
diacritics and tatweel don't hide them. They are reported for review only and stay in the chunk as data;
the answer pipeline treats every passage as untrusted (non-negotiable 8). Some business prose
("System: Android 14") will also match. That is accepted noise for a review list.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
from pypdf import PageObject
from pypdf.generic import ContentStream, DictionaryObject

from app.textnorm import for_index

INK_DPI = 144
# Minimum luminance difference (0-255) between a glyph's darkest/brightest pixel and its surroundings.
MIN_INK = 40
MIN_FONT_SIZE = 2.0
INVISIBLE_RENDER_MODES = {3, 7}  # PDF text render modes that paint no glyph
MAX_FORM_DEPTH = 8

_PATTERNS = (
    r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instructions?|rules|prompts?|guidelines|directions|directives)\b",
    r"\b(system|developer)\s+(note|prompt|message|instructions?)\b",
    r"\b(system|assistant)\s*:",
    r"\byou are now\b",
    r"\b(reveal|print|show|output|leak)\b.{0,40}\b(prompt|api key|secret|password|token)\b",
    r"\b(always|must)\b.{0,30}\b(add|include|append|insert)\b.{0,40}\b(link|url)\b",
    r"\bnew instructions?\b",
    r"(تجاهل|تناسى|انسى|تخطى)\S*\s+(\S+\s+){0,3}?(التعليمات|القواعد|الأوامر|التوجيهات)",
    r"ملاحظة\s+للنظام",
    r"موجه\s+النظام",
    r"(المساعد|النظام)\s*:",
    r"(اكشف|أظهر|اعرض)\S*\s+(\S+\s+){0,3}?(مفتاح|موجه|كلمة\s+المرور|التعليمات)",
    r"أنت\s+الآن",
)
# Patterns are normalised like the text, so «الأوامر» in a pattern matches «الاوامر» in a document.
INSTRUCTION_PATTERNS = [re.compile(for_index(p), re.IGNORECASE) for p in _PATTERNS]


def _key(char: dict[str, Any]) -> tuple[float, float, str]:
    return (round(char["x0"], 2), round(char["top"], 2), char["text"])


class HiddenTextDetector:
    """Decides, for one pdfplumber page, which characters leave no visible ink on the rendered page."""

    def __init__(self, page: Any, dpi: int = INK_DPI) -> None:
        self.width = float(page.width)
        self.height = float(page.height)
        self.scale = dpi / 72
        image = page.to_image(resolution=dpi).original.convert("L")
        self.pixels = np.asarray(image, dtype=np.int16)
        self.hidden: set[tuple[float, float, str]] = set()
        previous_hidden = False
        for char in page.chars:  # content order: a space follows the visibility of the glyph before it
            if char["text"].strip():
                previous_hidden = self._invisible(char)
            if previous_hidden:
                self.hidden.add(_key(char))

    def ink(self, char: dict[str, Any]) -> int:
        """Largest luminance difference between the glyph's box and the ring of pixels around it."""
        h, w = self.pixels.shape
        x0 = max(int(char["x0"] * self.scale) - 1, 0)
        x1 = min(int(char["x1"] * self.scale) + 2, w)
        y0 = max(int(char["top"] * self.scale) - 1, 0)
        y1 = min(int(char["bottom"] * self.scale) + 2, h)
        box = self.pixels[y0:y1, x0:x1]
        if box.size == 0:
            return 0
        ring = np.concatenate([box[0], box[-1], box[:, 0], box[:, -1]])
        background = int(np.median(ring))
        return int(np.abs(box - background).max())

    def _invisible(self, char: dict[str, Any]) -> bool:
        if char["size"] < MIN_FONT_SIZE:
            return True
        if char["x1"] < 0 or char["x0"] > self.width or char["bottom"] < 0 or char["top"] > self.height:
            return True
        return self.ink(char) < MIN_INK

    def is_hidden(self, obj: dict[str, Any]) -> bool:
        return obj.get("object_type") == "char" and _key(obj) in self.hidden


def _render_modes(stream: Any, pdf: Any, resources: Any, depth: int) -> set[int]:
    modes: set[int] = set()
    for operands, operator in ContentStream(stream, pdf).operations:
        if operator == b"Tr" and operands and int(operands[0]) in INVISIBLE_RENDER_MODES:
            modes.add(int(operands[0]))
        elif (
            operator == b"Do"
            and operands
            and depth < MAX_FORM_DEPTH
            and isinstance(resources, DictionaryObject)
        ):
            xobjects = resources.get("/XObject")
            form = xobjects.get_object().get(operands[0]) if xobjects else None
            form = form.get_object() if form is not None else None
            if form is not None and form.get("/Subtype") == "/Form":
                modes |= _render_modes(form, pdf, form.get("/Resources", resources), depth + 1)
    return modes


def invisible_render_modes(page: PageObject) -> set[int]:
    """Text render modes 3/7 used in the page's content stream or in Form XObjects it draws."""
    contents = page.get_contents()
    if contents is None:
        return set()
    resources = page.get("/Resources")
    return _render_modes(contents, page.pdf, resources.get_object() if resources else None, 0)


def instruction_matches(text: str) -> list[str]:
    """The instruction-like phrases found in text (empty for normal document prose)."""
    normalised = for_index(text)
    return [m.group(0).strip() for p in INSTRUCTION_PATTERNS if (m := p.search(normalised))]
