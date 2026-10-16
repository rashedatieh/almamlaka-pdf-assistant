"""Keyword leg: in-process Okapi BM25 over chunk index text (PROJECT_PLAN §3.1, §4.1 step 3).

Documents and queries pass through the same steps:
  1. The vendored Arabic `index` normalisation (docs/ENGINEERING_RULES.md), then lower-casing and tokenising.
  2. Thousands separators are removed from numbers, so "$2,400,000", "2,400,000" and "2400000" match.
  3. A light, symmetric stemmer strips English plural "s" and Arabic article/conjunction prefixes.
  4. A short stopword list drops question words that would match every chunk.
Display text is never touched.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from app.textnorm import for_index

TOKEN_RE = re.compile(r"[^\W_]+(?:[,.][^\W_]+)*")
K1 = 1.2
B = 0.75

STOPWORDS = frozenset(
    "a an and are as at be by did do does for from has have how in is it its of on or that the "
    "their there this to was were what when where which who whom why will with".split()
)
# Arabic stopwords, written after `index` normalisation (alef and taa marbuta forms unified).
ARABIC_STOPWORDS = frozenset(
    for_index(w) for w in "ما ماذا من في على هل متى كم هو هي عن إلى او أو مع هذا هذه التي الذي".split()
)
ARABIC_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")


def _stem(token: str) -> str:
    if token.isascii():
        if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
            return token[:-1]
        return token
    for prefix in ARABIC_PREFIXES:
        if token.startswith(prefix) and len(token) - len(prefix) >= 3:
            return token[len(prefix) :]
    return token


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in TOKEN_RE.findall(for_index(text).lower()):
        token = raw.replace(",", "") if any(ch.isdigit() for ch in raw) else raw
        if token in STOPWORDS or token in ARABIC_STOPWORDS:
            continue
        tokens.append(_stem(token))
    return tokens


class BM25:
    """BM25 over a fixed set of documents, keyed by ID."""

    def __init__(self, documents: dict[str, str]) -> None:
        self.ids = list(documents)
        self.terms = {doc_id: Counter(tokenize(text)) for doc_id, text in documents.items()}
        self.lengths = {doc_id: sum(counts.values()) for doc_id, counts in self.terms.items()}
        self.average_length = sum(self.lengths.values()) / max(len(self.ids), 1)
        frequency: Counter[str] = Counter()
        for counts in self.terms.values():
            frequency.update(counts.keys())
        n = len(self.ids)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in frequency.items()}

    def score(self, query_terms: list[str], doc_id: str) -> float:
        counts, length = self.terms[doc_id], self.lengths[doc_id]
        total = 0.0
        for term in query_terms:
            tf = counts.get(term, 0)
            if tf:
                norm = tf + K1 * (1 - B + B * length / self.average_length)
                total += self.idf[term] * tf * (K1 + 1) / norm
        return total

    def search(self, query: str, limit: int | None = None) -> list[tuple[str, float]]:
        """Documents with at least one matching term, best first (ties broken by ID)."""
        terms = tokenize(query)
        scored = [(doc_id, self.score(terms, doc_id)) for doc_id in self.ids]
        hits = sorted((hit for hit in scored if hit[1] > 0), key=lambda hit: (-hit[1], hit[0]))
        return hits[:limit] if limit else hits
