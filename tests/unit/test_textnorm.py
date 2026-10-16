"""quote_in: the J-02 quote rule (red-team M1 findings 5 and 7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.textnorm import for_match, quote_in

ROOT = Path(__file__).resolve().parents[2]
CHUNKS = {
    c["chunk_id"]: c["text"]
    for c in map(json.loads, (ROOT / "data/index/chunks.jsonl").read_text("utf-8").splitlines())
}
BUDGET_NOTES = CHUNKS["BUD-p1-s2"]
BUDGET_TABLE = CHUNKS["BUD-p1-s1"]
KEY_DETAILS = CHUNKS["OVR-p1-s3"]


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("the total project budget was adjusted to $2,600,000", BUDGET_NOTES),
        ("Q2 2027 | $500,000 | $150,000", BUDGET_TABLE),
        ("Q2 2027 $500,000 $150,000", BUDGET_TABLE),  # the same row quoted without pipes
        ("Planned Launch Date: March 15, 2027", KEY_DETAILS),
        ("“Planned Launch Date: March 15, 2027”", KEY_DETAILS),  # wrapped in curly quotes
        ("the channel’s digital presence", CHUNKS["OVR-p1-s1"]),  # curly apostrophe
        ("Mar 1 – Mar 20, 2027", CHUNKS["BUD-p2-s3"]),  # en dash for the hyphen
        ("bi‑weekly", CHUNKS["GOV-p1-s2"]),  # non-breaking hyphen
    ],
)
def test_faithful_quotes_match(quote: str, text: str) -> None:
    assert quote_in(quote, text)


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("$2,6", BUDGET_NOTES),  # truncated number
        ("2,600,00", BUDGET_NOTES),  # truncated number at the end
        ("600,000", BUDGET_NOTES),  # cut from the front of $2,600,000
        ("", BUDGET_NOTES),
        ("   ", BUDGET_NOTES),
        ("Q1", BUDGET_TABLE),  # too short to be evidence
        ("$630,000 Q2 2027", BUDGET_TABLE),  # spliced across two table rows
        ("Sara Al-Rashid Total Approved Budget", KEY_DETAILS),  # spliced across key-value lines
        ("adjusted to $2,400,000", BUDGET_NOTES),  # simply not in the text
    ],
)
def test_unfaithful_quotes_do_not_match(quote: str, text: str) -> None:
    assert not quote_in(quote, text)


def test_for_match_folds_typography_but_keeps_digits_and_words() -> None:
    assert for_match("a | b c​d — “e”") == 'a b cd - "e"'
    assert for_match("٢٠٢٦") == "٢٠٢٦"  # Arabic-Indic digits are not rewritten here (index profile does that)
