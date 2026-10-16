#!/usr/bin/env python3
"""Normalise Arabic (and mixed Arabic/English) text for embedding and search indexing.

Keep the original text for display and citations; normalise a copy for the embedding and the
full-text index, and apply the SAME profile to queries.

Profiles (each can be adjusted with the flags below):
  light  : Arabic presentation forms -> base letters, remove tatweel, normalise spaces.
  embed  : light + remove diacritics (tashkeel, Quranic marks, dagger alef), unify alef variants
           (أ إ آ ٱ -> ا), Persian yeh/keheh (ی ک -> ي ك), remove bidi controls and zero-width
           characters, Eastern Arabic and Persian digits -> Western.
  index  : embed + alef maqsura (ى -> ي), taa marbuta (ة -> ه), hamza on waw/yaa (ؤ ئ -> و ي),
           Arabic punctuation -> Latin (، ؛ ؟ -> , ; ?). Aggressive: use for keyword/BM25 indexes.

Usage examples:
  python3 arabic_normalize.py --profile embed --input doc.txt --output doc.norm.txt
  echo "أَهْلاً بِكُمْ ٢٠٢٦" | python3 arabic_normalize.py --profile index
  python3 arabic_normalize.py --profile embed --jsonl --field text --input chunks.jsonl
  python3 arabic_normalize.py --self-test

Statistics of every change are printed to stderr with --stats (JSON).
Standard library only; no network. Exit codes: 0 ok, 1 self-test failure, 2 usage or I/O error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

DIACRITIC_RANGES = [
    (0x0610, 0x061A),  # Quranic honorific small marks
    (0x064B, 0x065F),  # tanween, harakat, shadda, sukun, extended marks
    (0x0670, 0x0670),  # superscript (dagger) alef
    (0x06D6, 0x06DC),  # Quranic annotation signs
    (0x06DF, 0x06E4),
    (0x06E7, 0x06E8),
    (0x06EA, 0x06ED),
]
TATWEEL = "ـ"
ALEF_VARIANTS = {"آ": "ا", "أ": "ا", "إ": "ا", "ٱ": "ا",
                 "ٲ": "ا", "ٳ": "ا"}
PERSIAN_FORMS = {"ی": "ي", "ک": "ك"}  # Farsi yeh, keheh
ALEF_MAQSURA = {"ى": "ي"}
TAA_MARBUTA = {"ة": "ه"}
HAMZA_CARRIERS = {"ؤ": "و", "ئ": "ي"}
PUNCTUATION = {"،": ",", "؛": ";", "؟": "?"}
BIDI_CONTROLS = set("‎‏؜‪‫‬‭‮⁦⁧⁨⁩")
ZERO_WIDTH = set("​‌‍﻿")
EASTERN_DIGITS = {chr(0x0660 + i): str(i) for i in range(10)}
PERSIAN_DIGITS = {chr(0x06F0 + i): str(i) for i in range(10)}
WESTERN_TO_EASTERN = {str(i): chr(0x0660 + i) for i in range(10)}
ARABIC_NUMERIC_SEPARATORS = {"٫": ".", "٬": ",", "٪": "%"}


@dataclass
class Options:
    presentation_forms: bool = True
    tatweel: bool = True
    whitespace: bool = True
    diacritics: bool = False
    alef: bool = False
    persian_forms: bool = False
    bidi: bool = False
    zero_width: bool = False
    digits: str = "keep"  # keep | western | eastern
    alef_maqsura: bool = False
    taa_marbuta: bool = False
    hamza_carriers: bool = False
    punctuation: bool = False


PROFILES: Dict[str, Dict[str, object]] = {
    "light": {},
    "embed": {"diacritics": True, "alef": True, "persian_forms": True, "bidi": True,
              "zero_width": True, "digits": "western"},
    "index": {"diacritics": True, "alef": True, "persian_forms": True, "bidi": True,
              "zero_width": True, "digits": "western", "alef_maqsura": True,
              "taa_marbuta": True, "hamza_carriers": True, "punctuation": True},
}


@dataclass
class Stats:
    counts: Dict[str, int] = field(default_factory=dict)

    def add(self, key: str, n: int = 1) -> None:
        if n:
            self.counts[key] = self.counts.get(key, 0) + n


def _is_diacritic(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in DIACRITIC_RANGES)


def _is_presentation_form(cp: int) -> bool:
    return 0xFB50 <= cp <= 0xFDFF or 0xFE70 <= cp <= 0xFEFF and cp != 0xFEFF


def normalize(text: str, opts: Options, stats: Optional[Stats] = None) -> str:
    st = stats if stats is not None else Stats()
    out: List[str] = []
    for ch in text:
        cp = ord(ch)
        if opts.presentation_forms and _is_presentation_form(cp):
            mapped = unicodedata.normalize("NFKC", ch)
            st.add("presentation_forms")
            out.append(mapped)
            continue
        out.append(ch)
    text = "".join(out)

    out = []
    for ch in text:
        cp = ord(ch)
        if opts.tatweel and ch == TATWEEL:
            st.add("tatweel")
            continue
        if opts.diacritics and _is_diacritic(cp):
            st.add("diacritics")
            continue
        if opts.bidi and ch in BIDI_CONTROLS:
            st.add("bidi_controls")
            continue
        if opts.zero_width and ch in ZERO_WIDTH:
            st.add("zero_width")
            continue
        if opts.alef and ch in ALEF_VARIANTS:
            st.add("alef_variants")
            out.append(ALEF_VARIANTS[ch])
            continue
        if opts.persian_forms and ch in PERSIAN_FORMS:
            st.add("persian_forms")
            out.append(PERSIAN_FORMS[ch])
            continue
        if opts.alef_maqsura and ch in ALEF_MAQSURA:
            st.add("alef_maqsura")
            out.append(ALEF_MAQSURA[ch])
            continue
        if opts.taa_marbuta and ch in TAA_MARBUTA:
            st.add("taa_marbuta")
            out.append(TAA_MARBUTA[ch])
            continue
        if opts.hamza_carriers and ch in HAMZA_CARRIERS:
            st.add("hamza_carriers")
            out.append(HAMZA_CARRIERS[ch])
            continue
        if opts.digits == "western":
            if ch in EASTERN_DIGITS or ch in PERSIAN_DIGITS:
                st.add("digits_to_western")
                out.append(EASTERN_DIGITS.get(ch) or PERSIAN_DIGITS[ch])
                continue
            if ch in ARABIC_NUMERIC_SEPARATORS:
                st.add("numeric_separators")
                out.append(ARABIC_NUMERIC_SEPARATORS[ch])
                continue
        elif opts.digits == "eastern" and ch in WESTERN_TO_EASTERN:
            st.add("digits_to_eastern")
            out.append(WESTERN_TO_EASTERN[ch])
            continue
        if opts.punctuation and ch in PUNCTUATION:
            st.add("punctuation")
            out.append(PUNCTUATION[ch])
            continue
        out.append(ch)
    text = "".join(out)

    if opts.whitespace:
        before = text
        text = text.replace(" ", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = text.strip()
        if text != before:
            st.add("whitespace_fixes")
    return text


def build_options(profile: str, args: Optional[argparse.Namespace] = None) -> Options:
    opts = Options(**PROFILES[profile])  # type: ignore[arg-type]
    if args is None:
        return opts
    if args.digits is not None:
        opts.digits = args.digits
    for name in ("diacritics", "alef", "alef_maqsura", "taa_marbuta", "hamza_carriers", "punctuation"):
        if getattr(args, f"no_{name}", False):
            setattr(opts, name, False)
        if getattr(args, f"force_{name}", False):
            setattr(opts, name, True)
    return opts


SELF_TESTS = [
    ("light", "المـــادة الأولى", "المادة الأولى"),
    ("embed", "أَهْلاً وَسَهْلاً", "اهلا وسهلا"),
    ("embed", "إدارة آمنة", "ادارة امنة"),
    ("embed", "رقم ٢٠٢٦ و۱۲", "رقم 2026 و12"),
    ("embed", "رسوم ٢٥٫٥٠ ريالًا", "رسوم 25.50 ريالا"),
    ("embed", "‏مرحبا‎ بك", "مرحبا بك"),
    ("embed", "مستشفى", "مستشفى"),
    ("index", "مستشفى الجامعة", "مستشفي الجامعه"),
    ("index", "مسؤول هيئة", "مسوول هيىه".replace("ى", "ي")),
    ("index", "هل وصلت الشحنة؟ نعم، وصلت؛ شكرًا", "هل وصلت الشحنه? نعم, وصلت; شكرا"),
    ("embed", "ﻻ إله", "لا اله"),
    ("embed", "کتاب یومی", "كتاب يومي"),
    ("embed", "Order 3.5 kg   shipped", "Order 3.5 kg shipped"),
]


def self_test() -> int:
    failures = 0
    for profile, given, expected in SELF_TESTS:
        got = normalize(given, build_options(profile))
        if got != expected:
            failures += 1
            print(f"FAIL [{profile}] {given!r}: expected {expected!r}, got {got!r}", file=sys.stderr)
    eastern = Options(digits="eastern")
    if normalize("2026", eastern) != "٢٠٢٦":
        failures += 1
        print("FAIL [digits=eastern] 2026", file=sys.stderr)
    total = len(SELF_TESTS) + 1
    print(f"self-test: {total - failures}/{total} passed")
    return 1 if failures else 0


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="embed")
    parser.add_argument("--input", type=Path, help="input file (default stdin)")
    parser.add_argument("--output", type=Path, help="output file (default stdout)")
    parser.add_argument("--digits", choices=["keep", "western", "eastern"], help="override digit handling")
    for name in ("diacritics", "alef", "alef_maqsura", "taa_marbuta", "hamza_carriers", "punctuation"):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(f"--no-{name.replace('_', '-')}", dest=f"no_{name}", action="store_true",
                           help=f"disable {name} normalisation")
        group.add_argument(f"--force-{name.replace('_', '-')}", dest=f"force_{name}", action="store_true",
                           help=f"enable {name} normalisation")
    parser.add_argument("--jsonl", action="store_true", help="input is JSONL; normalise one field per line")
    parser.add_argument("--field", default="text", help="JSONL field to normalise (default 'text')")
    parser.add_argument("--target-field", help="write result to this field (default: <field>_norm)")
    parser.add_argument("--stats", action="store_true", help="print change counts to stderr as JSON")
    parser.add_argument("--self-test", action="store_true", help="run built-in test cases and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    opts = build_options(args.profile, args)
    try:
        raw = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: cannot read input: {exc}", file=sys.stderr)
        return 2
    stats = Stats()
    if args.jsonl:
        target = args.target_field or f"{args.field}_norm"
        out_lines: List[str] = []
        for n, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"ERROR: line {n}: invalid JSON: {exc}", file=sys.stderr)
                return 2
            if args.field not in record or not isinstance(record[args.field], str):
                print(f"ERROR: line {n}: missing string field '{args.field}'", file=sys.stderr)
                return 2
            record[target] = normalize(record[args.field], opts, stats)
            record["normalization_profile"] = args.profile
            out_lines.append(json.dumps(record, ensure_ascii=False))
        result = "\n".join(out_lines) + "\n"
    else:
        result = normalize(raw, opts, stats) + "\n"
    try:
        if args.output:
            args.output.write_text(result, encoding="utf-8")
        else:
            sys.stdout.write(result)
    except OSError as exc:
        print(f"ERROR: cannot write output: {exc}", file=sys.stderr)
        return 2
    if args.stats:
        print(json.dumps({"profile": args.profile, "changes": stats.counts}, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
