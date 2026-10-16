"""Reply-language detection (PROJECT_PLAN §4.1 step 1; review finding 2026-10-16: only letters count).
Arabic-Indic digits and Arabic punctuation sit in the Arabic Unicode block but are not letters."""

from __future__ import annotations

import pytest

from app.lang import arabic_letters, detect, latin_letters, reply_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What is the total budget?", "en"),
        ("ما هي الميزانية الإجمالية؟", "ar"),
        ("ما هي ميزانية Q2 2027?", "ar"),
        ("Who is سارة الرشيد?", "ar"),  # 10 of 15 letters are Arabic
        # Digits and punctuation from the Arabic block used to count as Arabic letters.
        ("Budget in ٢٠٢٧?", "en"),
        ("Q2 ٢٠٢٧ ٢٬٤٠٠٬٠٠٠ ٪٤٠ budget?", "en"),  # noqa: RUF001
        ("Budget for ۱۴۰۶؟ ، ؛", "en"),
        ("Budgetـــــــ?", "en"),  # tatweel is not a letter
        ("ﻣﺮﺣﺒﺎ", "ar"),  # presentation forms are letters
        ("", "ar"),  # no letters: the UI default
        ("٢٠٢٧ ؟", "ar"),  # digits and punctuation only: no letters, the UI default
        ("2027?", "ar"),
    ],
)
def test_detect_counts_only_letters(text: str, expected: str) -> None:
    assert detect(text) == expected


def test_letter_counts_exclude_digits_punctuation_diacritics_and_tatweel() -> None:
    assert arabic_letters("١٢٣ ۴۵۶ ، ؛ ؟ ٪ ٫ ٬") == 0  # noqa: RUF001
    assert arabic_letters("مُحَمَّد") == 4  # the diacritics are marks, not letters
    assert arabic_letters("مـــرحبا") == 5  # tatweel is not a letter
    assert latin_letters("Café 2027, déjà-vu!") == 10
    assert latin_letters("ميزانية") == 0 and arabic_letters("Budget") == 0


@pytest.mark.parametrize(
    ("message", "requested", "arabizi", "expected"),
    [
        ("What is the budget?", "ar", False, "ar"),
        ("ما هي الميزانية؟", "en", False, "en"),
        ("shu el budget?", "none", True, "ar"),
        ("Budget in ٢٠٢٧?", "none", False, "en"),
    ],
)
def test_reply_language_explicit_request_and_arabizi_win(
    message: str, requested: str, arabizi: bool, expected: str
) -> None:
    assert reply_language(message, requested, arabizi) == expected
