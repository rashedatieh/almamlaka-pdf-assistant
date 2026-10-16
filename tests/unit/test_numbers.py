"""V4 number/date normalisation (written test-first). Arabic-Indic digits, English, MSA and
Levantine month names, amounts with $ / million, percentages, and derived arithmetic."""

from __future__ import annotations

import pytest

from app.pipeline.numbers import Fact, facts, format_chars, supported_by


def keys(text: str) -> set[str]:
    return {f.key for f in facts(text)}


# ---- extraction -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Total Approved Budget: $2,400,000", {"n:2400000"}),
        ("adjusted to $2.6 million", {"n:2600000"}),
        ("$2.6M in total", {"n:2600000"}),
        ("بلغت الميزانية ‎$٢٬٦٠٠٬٠٠٠‎", {"n:2600000"}),
        ("مليونان وستمئة ألف", set()),  # number words are not parsed; the support judge covers them
        ("2.4 مليون دولار", {"n:2400000"}),
        ("increase digital viewership by 40%", {"p:40"}),
        ("بنسبة ٤٠٪", {"p:40"}),
        ("Project Duration: 14 months", {"n:14"}),
        ("in 12 languages", {"n:12"}),
    ],
)
def test_numbers_and_amounts(text: str, expected: set[str]) -> None:
    assert keys(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Planned Launch Date: March 15, 2027", {"d:2027-03-15"}),
        ("Mar 1 - Mar 20, 2027", {"d:2027-03-01", "d:2027-03-20"}),
        ("Feb 5, 2027", {"d:2027-02-05"}),
        ("15 March 2027", {"d:2027-03-15"}),
        ("in December 2026", {"d:2026-12"}),
        ("15 آذار/مارس 2027", {"d:2027-03-15"}),
        ("١٥ آذار ٢٠٢٧", {"d:2027-03-15"}),
        ("1 نيسان/أبريل 2027", {"d:2027-04-01"}),
        ("كانون الأول/ديسمبر 2026", {"d:2026-12"}),
        ("في 5 شباط/فبراير 2027", {"d:2027-02-05"}),
        ("20 كانون الثاني/يناير 2027", {"d:2027-01-20"}),
        ("15 حزيران/يونيو 2027", {"d:2027-06-15"}),
        ("10 يناير 2027", {"d:2027-01-10"}),
    ],
)
def test_dates_in_english_msa_and_levantine(text: str, expected: set[str]) -> None:
    assert keys(text) == expected


def test_quarter_labels_are_not_amounts_but_their_digits_still_count() -> None:
    assert keys("Marketing in Q2 2027") == {"n:2027", "r:2"}
    assert keys("الربع Q1 من 2027") == {"n:2027", "r:1"}
    assert (
        supported_by("Marketing in Q2 2027 was $150,000.", ["Q2 2027 | $500,000 | $150,000"], derived=False)
        == []
    )
    assert (
        supported_by("Marketing in Q3 2027 was $150,000.", ["Q2 2027 | $500,000 | $150,000"], derived=False)
        != []
    )


# ---- security review 2026-10-16 ------------------------------------------------------------------------


def test_case_folding_look_alikes_never_crash() -> None:
    # "ſ" (long s) and the Kelvin sign fold to ASCII letters; they used to reach the month lookup and raise.
    for text in ["Auguſt 5, 2027", "MaK 5, 2027", "MARCH 15, 2027", "Aprİl 1, 2027"]:
        facts(text)  # must not raise
    assert keys("Auguſt 5, 2027") == {"d:2027-08-05"}  # NFKC turns ſ into s
    assert keys("MARCH 15, 2027") == {"d:2027-03-15"}


@pytest.mark.parametrize(
    "claim",
    [
        "The budget is $２,６００,０００.",  # full-width digits
        "The budget is $2 600 000.",  # thin-space separators
        "The budget is $2 600 000.",
        "The budget is 2.6e6 dollars.",
    ],
)
def test_unusual_number_formats_cannot_skip_v4(claim: str) -> None:
    # Against a quote that says $2,400,000, none of these may pass unverified.
    assert supported_by(claim, ["Total Approved Budget: $2,400,000"], derived=False) != []


def test_years_inside_dates_are_not_counted_twice() -> None:
    assert keys("March 15, 2027") == {"d:2027-03-15"}


# ---- support (V4) --------------------------------------------------------------------------------------


QUOTES = [
    "Total Approved Budget: $2,400,000",
    "the total project budget was adjusted to $2,600,000",
    "Following a revision by the Finance Committee in December 2026",
]


def test_claim_numbers_must_appear_in_quotes() -> None:
    assert supported_by("The budget is $2,400,000.", QUOTES, derived=False) == []
    assert (
        supported_by("الميزانية ‎$2,600,000‎ بعد التعديل في كانون الأول/ديسمبر 2026", QUOTES, derived=False)
        == []
    )
    missing = supported_by("The budget is $2,500,000.", QUOTES, derived=False)
    assert [f.key for f in missing] == ["n:2500000"]


def test_derived_numbers_must_be_recomputable_from_quotes() -> None:
    # C-05: the verifier recomputes 2,600,000 - 2,400,000.
    assert supported_by("The budget rose by $200,000.", QUOTES, derived=True) == []
    assert supported_by("The budget rose by $300,000.", QUOTES, derived=True) != []
    # A derived figure is not allowed in a plain fact claim.
    assert supported_by("The budget rose by $200,000.", QUOTES, derived=False) != []


def test_partial_dates_match_full_dates_with_the_same_day_and_month() -> None:
    assert (
        supported_by("Launch was planned for 15 March.", ["Public launch: March 15, 2027"], derived=False)
        == []
    )
    assert (
        supported_by("Launch was planned for 16 March.", ["Public launch: March 15, 2027"], derived=False)
        != []
    )


def test_month_year_claim_matches_a_full_date_in_that_month() -> None:
    assert (
        supported_by("The launch is in March 2027.", ["Public launch: March 15, 2027"], derived=False) == []
    )


def test_fact_dataclass_is_hashable_and_readable() -> None:
    fact = next(iter(facts("$2,400,000")))
    assert isinstance(fact, Fact) and fact.text.endswith("2,400,000")


# ---- review findings 2026-10-16 ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$4.1M", {"n:4100000"}),
        ("$8.2M", {"n:8200000"}),
        ("$0.3M", {"n:300000"}),
        ("4.1 million", {"n:4100000"}),
        ("2.45 مليون", {"n:2450000"}),
        ("$1.005 million", {"n:1005000"}),
        ("$12.5K", {"n:12500"}),
        ("2.5", {"n:2.5"}),
        ("2.50", {"n:2.5"}),
        ("$4,100,001", {"n:4100001"}),
        ("$123456789012345678901234567890123", {"n:123456789012345678901234567890123"}),
    ],
)
def test_decimal_amounts_are_exact_and_never_scientific(text: str, expected: set[str]) -> None:
    assert keys(text) == expected


def test_decimal_amounts_match_their_written_out_form() -> None:
    assert supported_by("The budget is $4.1M.", ["Budget: $4,100,000"], derived=False) == []
    assert supported_by("The budget is $4,100,000.", ["Budget: $4.1 million"], derived=False) == []
    assert supported_by("Phase 2 costs $8.2M.", ["Phase 2: $8,200,000"], derived=False) == []


def test_different_decimal_amounts_never_collide() -> None:
    # As floats, 4.1M, 4.100001M and 4,100,001 could all print as "4.1e+06".
    assert keys("$4.1M") != keys("$4,100,001") and keys("$4.1M") != keys("$4.100001M")
    assert supported_by("The budget is $4,100,001.", ["Budget: $4.1M"], derived=False) != []
    assert supported_by("The budget is $4.12M.", ["Budget: $4.1M"], derived=False) != []
    assert supported_by("The budget is 1234567.8.", ["Budget: 1234567.9"], derived=False) != []


def test_derived_decimal_sums_and_differences_are_exact() -> None:
    quotes = ["Phase 1: $4.1M", "Phase 2: $8.2M"]
    assert supported_by("Together they cost $12.3M.", quotes, derived=True) == []
    assert supported_by("Phase 2 costs $4.1M more.", quotes, derived=True) == []
    assert supported_by("Together they cost $12,300,000.", quotes, derived=True) == []
    assert supported_by("Together they cost $12.4M.", quotes, derived=True) != []
    three = ["A: $0.1M", "B: $0.2M", "C: $0.3M"]
    assert supported_by("In total $0.6M.", three, derived=True) == []  # 0.1 + 0.2 + 0.3, which floats miss


@pytest.mark.parametrize(
    "text",
    [
        "increase digital viewership by 40%",
        "increase digital viewership by 40 percent",
        "increase digital viewership by 40 per cent",
        "increase digital viewership by 40 Percent",
        "زيادة المشاهدة بنسبة 40 بالمئة",
        "زيادة المشاهدة بنسبة ٤٠ بالمائة",
        "زيادة المشاهدة بنسبة ٤٠ في المئة",
        "زيادة المشاهدة بنسبة 40 في المائة",
        "زيادة المشاهدة بنسبة ٤٠٪",
        "زيادة المشاهدة بنسبة ٤٠ ٪",
    ],
)
def test_percent_words_in_english_and_arabic(text: str) -> None:
    assert keys(text) == {"p:40"}
    assert supported_by(text, ["increase digital viewership by 40%"], derived=False) == []


def test_percent_words_are_not_percent_inside_longer_words() -> None:
    assert keys("40 percentage points") == {"n:40"}
    assert keys("12.5 per cent") == {"p:12.5"}
    assert supported_by("viewership rose 40 percent", ["Budget: $40"], derived=False) != []


@pytest.mark.parametrize(
    "char", ["\u202e", "\u202a", "\u2066", "\u2069", "\u200b", "\u200d", "\u200e", "\ufeff"]
)
def test_format_characters_are_reported_and_removed(char: str) -> None:
    text = f"The budget is $2,{char}400,000."
    assert format_chars(text) == [f"U+{ord(char):04X}"]
    assert keys(text) == {"n:2400000"}  # removed before parsing, so the amount isn't split


def test_plain_text_has_no_format_characters() -> None:
    assert format_chars("الميزانية $2,400,000 والمدة ١٤ شهراً، Q2 2027.") == []
