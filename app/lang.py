"""Reply language (PROJECT_PLAN §4.1 step 1).

`ar` when Arabic letters are at least 30% of the letters, else `en`. An explicit request
("answer in English", «أجب بالعربية») wins; Arabizi is answered in Arabic.
Only letters count: Arabic-Indic digits (U+0660-0669, U+06F0-06F9), Arabic punctuation (، ؛ ؟ ٪),
diacritics and tatweel are in the Arabic blocks but are not letters, so "٢٠٢٧ budget?" is English.
`arabic_letters` and `latin_letters` are shared with the verifier's V7 check (app.pipeline.verify).
"""

from __future__ import annotations

import re

# Arabic, Arabic Supplement, Arabic Extended-A and the two presentation-form blocks.
_ARABIC_BLOCK = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
_LATIN_BLOCK = re.compile(r"[A-Za-z\u00c0-\u024f]")
_TATWEEL = "\u0640"  # a stretching mark (category Lm), not a letter


def is_letter(ch: str) -> bool:
    return ch.isalpha() and ch != _TATWEEL


def arabic_letters(text: str) -> int:
    """How many Arabic letters `text` has; digits, punctuation, diacritics and tatweel don't count."""
    return sum(1 for ch in text if is_letter(ch) and _ARABIC_BLOCK.match(ch))


def latin_letters(text: str) -> int:
    """How many Latin letters (basic and accented) `text` has."""
    return sum(1 for ch in text if is_letter(ch) and _LATIN_BLOCK.match(ch))


def detect(text: str) -> str:
    letters = sum(1 for ch in text if is_letter(ch))
    if not letters:
        return "ar"  # UI_DEFAULT_LANG
    return "ar" if arabic_letters(text) / letters >= 0.3 else "en"


def reply_language(message: str, requested: str = "none", arabizi: bool = False) -> str:
    if requested in {"ar", "en"}:
        return requested
    if arabizi:
        return "ar"
    return detect(message)
