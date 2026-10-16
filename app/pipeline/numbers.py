"""Numbers, amounts, percentages and dates in claims and quotes (verifier step V4; PROJECT_PLAN §4.1).

Every number, amount, percentage or date in a claim must appear in that claim's quotes. A `derived` claim may
also use a value the verifier can recompute from them (a sum or difference, as in C-05). Normalisation covers:
  * Western and Arabic-Indic digits (٠-٩, ۰-۹), Arabic separators (٬ ٫ ٪), and every invisible format
    character (Unicode category Cf: bidi marks, overrides and isolates, zero-width characters), which is
    removed. A claim containing one is dropped by the verifier (`format_chars`), so it can never hide or
    reorder what a reader sees; quotes may contain them;
  * amounts with $, thousands separators, and million/M/مليون or thousand/K/ألف, as exact decimals
    ($4.1M is 4100000, never a float such as 4099999.99…), so two different amounts never share a key;
  * percentages written with % or ٪, "percent", "per cent", بالمئة, بالمائة, في المئة or في المائة;
  * dates with English month names (full or abbreviated), MSA names (يناير…ديسمبر) and Levantine names
    (كانون الثاني…كانون الأول), alone or paired ("آذار/مارس"), as day-month-year, month-year, day-month
    and ranges ("Mar 1 - Mar 20, 2027").
Numbers glued to letters (Q2, FX-3) are labels, not quantities. Number words are not parsed; the support
judge (V5) covers them.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from decimal import MAX_EMAX, MAX_PREC, MIN_EMIN, Context, Decimal
from functools import reduce
from itertools import combinations

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_MARKS = str.maketrans(
    {
        "\u066c": ",",
        "\u066b": ".",
        "\u066a": "%",
        "\u00a0": " ",
    }
)

_EN = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MSA = {
    "يناير": 1,
    "فبراير": 2,
    "مارس": 3,
    "أبريل": 4,
    "ابريل": 4,
    "إبريل": 4,
    "مايو": 5,
    "يونيو": 6,
    "يوليو": 7,
    "أغسطس": 8,
    "اغسطس": 8,
    "سبتمبر": 9,
    "أكتوبر": 10,
    "اكتوبر": 10,
    "نوفمبر": 11,
    "ديسمبر": 12,
}
_LEVANTINE = {
    "كانون الثاني": 1,
    "شباط": 2,
    "آذار": 3,
    "اذار": 3,
    "نيسان": 4,
    "أيار": 5,
    "ايار": 5,
    "حزيران": 6,
    "تموز": 7,
    "آب": 8,
    "اب": 8,
    "أيلول": 9,
    "ايلول": 9,
    "تشرين الأول": 10,
    "تشرين الاول": 10,
    "تشرين الثاني": 11,
    "كانون الأول": 12,
    "كانون الاول": 12,
}
_MONTHS = {**_EN, **_MSA, **_LEVANTINE}
_NAMES = "|".join(sorted((re.escape(m) for m in _MONTHS), key=len, reverse=True))
# A month is one name, or a Levantine/MSA pair such as "آذار/مارس".
MONTH = rf"(?P<{{g}}>(?:{_NAMES})(?:\s*/\s*(?:{_NAMES}))?)\.?"
_NOT_WORD = r"(?<![\w])"

RANGE_RE = re.compile(
    MONTH.format(g="m1")
    + r"\s+(?P<d1>\d{1,2})\s*[-–—]\s*"
    + MONTH.format(g="m2")
    + r"\s+(?P<d2>\d{1,2}),?\s+(?P<y>\d{4})",
)
MDY_RE = re.compile(_NOT_WORD + MONTH.format(g="m") + r"\s+(?P<d>\d{1,2}),?\s+(?P<y>\d{4})")
DMY_RE = re.compile(r"(?<!\d)(?P<d>\d{1,2})\s+" + MONTH.format(g="m") + r",?\s+(?P<y>\d{4})")
MY_RE = re.compile(_NOT_WORD + MONTH.format(g="m") + r",?\s+(?P<y>\d{4})")
DM_RE = re.compile(r"(?<!\d)(?P<d>\d{1,2})\s+" + MONTH.format(g="m") + r"(?![\w])")
MD_RE = re.compile(_NOT_WORD + MONTH.format(g="m") + r"\s+(?P<d>\d{1,2})(?!\d)")
_PERCENT_WORDS = r"percent|per\s+cent|بالمئة|بالمائة|في\s+المئة|في\s+المائة"
PERCENT_RE = re.compile(rf"(?<![\w.,])(?P<v>\d+(?:\.\d+)?)\s*(?:%|(?:{_PERCENT_WORDS})(?![\w]))")
AMOUNT_RE = re.compile(
    r"(?<![\w.,])\$?\s*(?P<v>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s*(?P<mult>million|thousand|مليون|ملايين|ألف|الف|آلاف)|(?P<suffix>[mk])(?![\w]))?(?![\w])",
)
_ONE, _THOUSAND, _MILLION = Decimal(1), Decimal(1_000), Decimal(1_000_000)
_MULTIPLIER = {
    "million": _MILLION,
    "مليون": _MILLION,
    "ملايين": _MILLION,
    "m": _MILLION,
    "thousand": _THOUSAND,
    "ألف": _THOUSAND,
    "الف": _THOUSAND,
    "آلاف": _THOUSAND,
    "k": _THOUSAND,
}
# Unbounded precision, so products, sums and differences of decimals read from text are always exact.
_EXACT = Context(prec=MAX_PREC, Emax=MAX_EMAX, Emin=MIN_EMIN)


RESIDUAL_RE = re.compile(r"\d+")


@dataclass(frozen=True)
class Fact:
    key: str  # "n:2400000", "p:40", "d:2027-03-15", "d:2026-12", "d:--03-15"
    text: str  # the matched span, for error messages


def format_chars(text: str) -> list[str]:
    """The invisible format characters (Unicode category Cf) in `text`, as "U+202E" labels, in order.

    Bidi overrides (U+202A-202E), isolates (U+2066-2069), marks (U+200E, U+200F, U+061C) and zero-width
    characters (U+200B-200D, U+2060, U+FEFF) can reorder or hide what a reader sees, so the verifier drops
    a claim that contains any of them (V4 / V8) instead of cleaning it.
    """
    return [f"U+{ord(ch):04X}" for ch in text if unicodedata.category(ch) == "Cf"]


def normalise(text: str) -> str:
    """NFKC (full-width digits, look-alike letters such as "ſ"), Arabic digits and marks, then lower case.

    Every format character (category Cf) is removed, so a zero-width space inside "2,400,000" in a quote
    can't split the amount. Patterns match lower-case names without re.IGNORECASE, so Unicode case
    folding can't produce a match that the month lookup doesn't know (security review, 2026-10-16).
    """
    text = "".join(ch for ch in unicodedata.normalize("NFKC", text) if unicodedata.category(ch) != "Cf")
    return text.translate(_DIGITS).translate(_MARKS).lower()


def _month(name: str) -> int | None:
    first = re.split(r"\s*/\s*", name.strip().rstrip("."))[0]
    return _MONTHS.get(first)


def _date(year: str, month: str, day: str | None = None) -> str | None:
    number = _month(month)
    if number is None:
        return None
    return f"d:{year}-{number:02d}" + (f"-{int(day):02d}" if day else "")


def _plain(amount: Decimal) -> str:
    """A decimal as plain digits, never scientific notation: 4100000.0 -> "4100000", 2.50 -> "2.5".

    format(…, "f") also has no digit limit, unlike str(int(…)), so a very long number can't raise.
    """
    text = format(amount, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _number(value: str, multiplier: Decimal = _ONE) -> str:
    """The key value of a matched number: its digits without commas, times the multiplier, exactly."""
    return _plain(_EXACT.multiply(Decimal(value.replace(",", "")), multiplier))


def facts(text: str) -> set[Fact]:
    """All numbers, amounts, percentages and dates in `text`, normalised."""
    text = normalise(text)
    found: set[Fact] = set()

    def take(pattern: re.Pattern[str], make: Callable[[re.Match[str]], list[str | None]]) -> None:
        nonlocal text

        def replace(m: re.Match[str]) -> str:
            keys = make(m)
            if not keys or any(k is None for k in keys):
                return m.group(0)  # not a recognised date: leave it for the number passes
            for key in keys:
                found.add(Fact(str(key), m.group(0).strip()))
            return " " * len(m.group(0))  # mask, so a year is not counted again as a number

        text = pattern.sub(replace, text)

    def day_month(m: re.Match[str]) -> list[str | None]:
        number = _month(m["m"])
        return [None if number is None else f"d:--{number:02d}-{int(m['d']):02d}"]

    take(RANGE_RE, lambda m: [_date(m["y"], m["m1"], m["d1"]), _date(m["y"], m["m2"], m["d2"])])
    take(MDY_RE, lambda m: [_date(m["y"], m["m"], m["d"])])
    take(DMY_RE, lambda m: [_date(m["y"], m["m"], m["d"])])
    take(MY_RE, lambda m: [_date(m["y"], m["m"])])
    take(DM_RE, day_month)
    take(MD_RE, day_month)
    take(PERCENT_RE, lambda m: [f"p:{_number(m['v'])}"])
    take(AMOUNT_RE, lambda m: [f"n:{_number(m['v'], _MULTIPLIER.get(m['mult'] or m['suffix'] or '', _ONE))}"])
    # Any digit run left (in a label such as "Q2", or in a format no pattern knows) is still a fact:
    # V4 then requires the same digits in the quotes, so no number can skip verification.
    for run in RESIDUAL_RE.findall(text):
        found.add(Fact(f"r:{run}", run))
    return found


def _derived_values(numbers: list[Decimal]) -> set[str]:
    """Every pairwise difference and sum, and the total of three or more, computed exactly."""
    pairs = list(combinations(numbers, 2))
    values = {_EXACT.abs(_EXACT.subtract(a, b)) for a, b in pairs} | {_EXACT.add(a, b) for a, b in pairs}
    if len(numbers) > 2:
        values.add(reduce(_EXACT.add, numbers))
    return {_plain(v) for v in values}


def supported_by(claim: str, quotes: list[str], derived: bool) -> list[Fact]:
    """The claim's facts that its quotes don't support (empty = V4 passes)."""
    quote_keys = {f.key for q in quotes for f in facts(q)}
    full_dates = [k[2:] for k in quote_keys if re.fullmatch(r"d:\d{4}-\d{2}-\d{2}", k)]
    years = {d[:4] for d in full_dates} | {k[2:6] for k in quote_keys if re.fullmatch(r"d:\d{4}-\d{2}", k)}
    numbers = [Decimal(k[2:]) for k in quote_keys if k.startswith("n:")]
    allowed = _derived_values(numbers) if derived else set()
    quote_digits = {run for q in quotes for run in RESIDUAL_RE.findall(normalise(q))}

    missing: list[Fact] = []
    for fact in sorted(facts(claim), key=lambda f: f.key):
        key = fact.key
        if key in quote_keys:
            continue
        if key.startswith("d:--") and any(d.endswith(key[4:]) for d in full_dates):
            continue  # "15 March" against "March 15, 2027"
        if re.fullmatch(r"d:\d{4}-\d{2}", key) and any(d.startswith(key[2:]) for d in full_dates):
            continue  # "March 2027" against "March 15, 2027"
        if key.startswith("n:") and (key[2:] in years or key[2:] in allowed):
            continue
        if key.startswith("r:") and key[2:] in quote_digits:
            continue  # a label such as "Q2" that the quotes also contain
        missing.append(fact)
    return missing
