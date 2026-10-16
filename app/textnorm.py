"""Text normalisation for comparisons. Display text is never normalised (ENGINEERING_RULES.md conventions).

for_match: the comparison form of a text. NFKC, then typographic variants a model may produce are folded:
  curly quotes become straight, U+2010–U+2015 and U+2212 dashes become "-", soft hyphens and zero-width
  spaces are dropped, table-cell pipes "|" become spaces, and whitespace runs collapse.
quote_in: the single rule for "is this quote really in that chunk" (J-02, the M3 verifier, radar and graph).
  The quote must sit within one line of the chunk (one paragraph, key-value line or table row), must not
  be cut mid-word or mid-number ("$2,4" does not match "$2,400,000"), and must have at least 4 characters.
for_index: the vendored Arabic `index` profile (diacritics, tatweel, alef forms, Arabic-Indic
  digits). Used for BM25 on documents and queries, and for instruction-pattern matching.
for_embed: the lighter `embed` profile, for text sent to the embedding model.
"""

from __future__ import annotations

import re
import unicodedata

from vendor.arabic_rag.arabic_normalize import build_options, normalize

_INDEX = build_options("index")
_EMBED = build_options("embed")
_FOLD = str.maketrans(
    {
        **dict.fromkeys(["‘", "’", "‛", "ʼ"], "'"),
        **dict.fromkeys(["“", "”", "„"], '"'),
        **dict.fromkeys(["‐", "‑", "‒", "–", "—", "―", "−"], "-"),
        **dict.fromkeys(["­", "​"], None),
        "|": " ",
    }
)
MIN_QUOTE_CHARS = 4


def for_match(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).translate(_FOLD).split())


def _fold_with_map(line: str) -> tuple[str, list[int]]:
    """for_match(line) plus, for every output character, the index of the input character it came from."""
    chars: list[str] = []
    origin: list[int] = []
    for i, ch in enumerate(line):
        for out in unicodedata.normalize("NFKC", ch).translate(_FOLD):
            if out.isspace():
                if chars and chars[-1] != " ":
                    chars.append(" ")
                    origin.append(i)
            else:
                chars.append(out)
                origin.append(i)
    while chars and chars[-1] == " ":
        chars.pop()
        origin.pop()
    return "".join(chars), origin


def locate(quote: str, text: str, min_chars: int = MIN_QUOTE_CHARS) -> tuple[int, int] | None:
    """Where `quote` sits in `text` as (start, end) character offsets, or None.

    The quote must appear whole within one line of `text`, after for_match folding. The offsets point at
    the original characters, so the UI shows the exact PDF text and the spotlight highlights it.
    """
    needle = for_match(quote).strip(" '\"")
    if len(needle) < min_chars:
        return None
    pattern = re.compile(r"(?<![\w.,])" + re.escape(needle) + r"(?![\w]|[.,]\d)")
    offset = 0
    for line in text.split("\n"):
        folded, origin = _fold_with_map(line)
        match = pattern.search(folded)
        if match:
            return offset + origin[match.start()], offset + origin[match.end() - 1] + 1
        offset += len(line) + 1
    return None


def quote_in(quote: str, text: str, min_chars: int = MIN_QUOTE_CHARS) -> bool:
    """True if `quote` appears whole, within one line of `text`, after for_match folding."""
    return locate(quote, text, min_chars) is not None


def for_index(text: str) -> str:
    return normalize(text, _INDEX)


def for_embed(text: str) -> str:
    """The `embed` profile, applied to every text sent to the embedding model (PROJECT_PLAN §3.1)."""
    return normalize(text, _EMBED)
