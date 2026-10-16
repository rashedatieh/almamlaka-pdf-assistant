#!/usr/bin/env python3
"""Sentence-aware chunker for Arabic, English and mixed documents, with overlap.

Splits on sentence terminators . ! ? ؟ … ۔ (followed by optional closing quotes or brackets and
then whitespace or end of text) and on line breaks. Paragraphs (blank lines) are preferred chunk
boundaries. A sentence longer than --max-chars is split at clause marks (؛ ;), then commas (، ,),
then whitespace. Decimal numbers such as 3.5 or ٢٥٫٥٠ are never split.

Chunks are cut from the ORIGINAL text, so diacritics and formatting are preserved for display and
citation; normalise a copy for embedding with arabic_normalize.py. Offsets (char_start, char_end)
refer to the original text.

Sizes are in characters. Token counts depend on the tokenizer: pass --chars-per-token measured on
your corpus with the target tokenizer to get an estimate; nothing is assumed by default.

Output: JSONL, one chunk per line:
  {"chunk_id", "source", "index", "text", "char_start", "char_end", "n_chars", "n_sentences",
   "overlap_chars", "est_tokens"?}

Standard library only; no network. Exit codes: 0 ok, 1 validation failure, 2 usage or I/O error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

TERMINATORS = ".!?؟…۔"  # . ! ? ؟ … ۔
CLOSERS = "\"'»”’)]}"  # " ' » ” ’ ) ] }
SENTENCE_END_RE = re.compile(rf"[{re.escape(TERMINATORS)}]+[{re.escape(CLOSERS)}]*(?=\s|$)")
PARAGRAPH_RE = re.compile(r"\n[ \t]*\n+")
CLAUSE_MARKS = ["؛", ";"]          # ؛ ;
COMMA_MARKS = ["،", ","]           # ، ,


@dataclass
class Span:
    start: int
    end: int
    paragraph: int


def paragraphs(text: str) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    pos = 0
    for match in PARAGRAPH_RE.finditer(text):
        spans.append((pos, match.start()))
        pos = match.end()
    spans.append((pos, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def _trim(text: str, start: int, end: int) -> Tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def sentences(text: str, para_start: int, para_end: int, p_index: int) -> List[Span]:
    spans: List[Span] = []
    for line_match in re.finditer(r"[^\n]+", text[para_start:para_end]):
        l_start = para_start + line_match.start()
        l_end = para_start + line_match.end()
        pos = l_start
        for end_match in SENTENCE_END_RE.finditer(text, l_start, l_end):
            s, e = _trim(text, pos, end_match.end())
            if e > s:
                spans.append(Span(s, e, p_index))
            pos = end_match.end()
        s, e = _trim(text, pos, l_end)
        if e > s:
            spans.append(Span(s, e, p_index))
    return spans


def split_long(text: str, span: Span, max_chars: int) -> List[Span]:
    """Split one over-long sentence at clause marks, commas, then whitespace."""
    if span.end - span.start <= max_chars:
        return [span]
    for marks in (CLAUSE_MARKS, COMMA_MARKS, [" "]):
        cut = -1
        window_end = span.start + max_chars
        for mark in marks:
            idx = text.rfind(mark, span.start + 1, window_end)
            cut = max(cut, idx)
        if cut > span.start:
            first_end = cut + (0 if marks == [" "] else 1)
            first = Span(*_trim(text, span.start, first_end), span.paragraph)
            rest = Span(*_trim(text, first_end, span.end), span.paragraph)
            if first.end > first.start and rest.end > rest.start:
                return [first] + split_long(text, rest, max_chars)
    hard = span.start + max_chars
    return [Span(span.start, hard, span.paragraph)] + split_long(text, Span(hard, span.end, span.paragraph), max_chars)


def pack(text: str, spans: List[Span], max_chars: int, min_chars: int, overlap_sentences: int,
         paragraph_break: bool) -> List[Tuple[List[Span], int]]:
    """Greedy packing. Returns list of (sentences in chunk, number of overlap sentences carried in)."""
    chunks: List[Tuple[List[Span], int]] = []
    current: List[Span] = []
    carried = 0

    def size(items: List[Span]) -> int:
        return items[-1].end - items[0].start if items else 0

    def flush() -> None:
        nonlocal current, carried
        if not current or len(current) == carried:
            return
        chunks.append((current, carried))
        tail = current[-overlap_sentences:] if overlap_sentences > 0 else []
        while tail and size(tail) > max_chars // 2:
            tail = tail[1:]
        current = list(tail)
        carried = len(tail)

    for span in spans:
        new_paragraph = bool(current) and span.paragraph != current[-1].paragraph
        if paragraph_break and new_paragraph and size(current) >= min_chars:
            flush()
        if current and (span.end - current[0].start) > max_chars:
            flush()
            while current and (span.end - current[0].start) > max_chars:
                current = current[1:]
                carried = max(0, carried - 1)
        current.append(span)
    flush()
    return chunks


def chunk_document(text: str, source: str, max_chars: int, min_chars: int, overlap_sentences: int,
                   paragraph_break: bool, chars_per_token: Optional[float]) -> Iterable[dict]:
    all_spans: List[Span] = []
    for p_index, (p_start, p_end) in enumerate(paragraphs(text)):
        for span in sentences(text, p_start, p_end, p_index):
            all_spans.extend(split_long(text, span, max_chars))
    for index, (items, carried) in enumerate(pack(text, all_spans, max_chars, min_chars, overlap_sentences,
                                                   paragraph_break)):
        start, end = items[0].start, items[-1].end
        chunk_text = text[start:end]
        overlap_chars = (items[carried - 1].end - start) if carried else 0
        digest = hashlib.sha256(f"{source}:{start}:{end}".encode("utf-8")).hexdigest()[:12]
        record = {
            "chunk_id": f"{Path(source).stem}-{index:04d}-{digest}",
            "source": source,
            "index": index,
            "text": chunk_text,
            "char_start": start,
            "char_end": end,
            "n_chars": len(chunk_text),
            "n_sentences": len(items),
            "overlap_chars": overlap_chars,
        }
        if chars_per_token:
            record["est_tokens"] = round(len(chunk_text) / chars_per_token)
        yield record


def validate_chunks(text: str, chunks: List[dict], max_chars: int) -> List[str]:
    errors: List[str] = []
    for c in chunks:
        if text[c["char_start"]:c["char_end"]] != c["text"]:
            errors.append(f"{c['chunk_id']}: offsets do not reproduce the text")
        if c["n_chars"] > max_chars:
            errors.append(f"{c['chunk_id']}: {c['n_chars']} chars exceeds max {max_chars}")
        if re.search(r"\d[.٫]$", c["text"]) and c["char_end"] < len(text) and text[c["char_end"]].isdigit():
            errors.append(f"{c['chunk_id']}: chunk ends inside a decimal number")
    covered = sorted((c["char_start"], c["char_end"]) for c in chunks)
    pos = 0
    for start, end in covered:
        if text[pos:start].strip():
            errors.append(f"text between {pos} and {start} is not in any chunk")
        pos = max(pos, end)
    if text[pos:].strip():
        errors.append(f"text after {pos} is not in any chunk")
    return errors


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True, help="UTF-8 text or markdown file")
    parser.add_argument("--output", type=Path, help="JSONL output (default stdout)")
    parser.add_argument("--source", help="source id stored in each chunk (default: input file name)")
    parser.add_argument("--max-chars", type=int, default=1200, help="maximum chunk length in characters (default 1200)")
    parser.add_argument("--min-chars", type=int, default=200,
                        help="close a chunk at a paragraph end once it has this many characters (default 200)")
    parser.add_argument("--overlap-sentences", type=int, default=1, help="sentences carried into the next chunk (default 1)")
    parser.add_argument("--no-paragraph-break", action="store_true", help="ignore paragraph boundaries when packing")
    parser.add_argument("--chars-per-token", type=float,
                        help="measured characters per token for your tokenizer; adds est_tokens")
    parser.add_argument("--check", action="store_true", help="validate offsets, sizes and coverage; exit 1 on failure")
    args = parser.parse_args(argv)
    if args.max_chars < 50:
        print("ERROR: --max-chars must be at least 50", file=sys.stderr)
        return 2
    if args.overlap_sentences < 0 or args.min_chars < 0:
        print("ERROR: --overlap-sentences and --min-chars must be >= 0", file=sys.stderr)
        return 2
    if args.chars_per_token is not None and args.chars_per_token <= 0:
        print("ERROR: --chars-per-token must be positive", file=sys.stderr)
        return 2
    try:
        text = args.input.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: cannot read {args.input}: {exc}", file=sys.stderr)
        return 2
    source = args.source or args.input.name
    chunks = list(chunk_document(text, source, args.max_chars, args.min_chars, args.overlap_sentences,
                                 not args.no_paragraph_break, args.chars_per_token))
    if args.check:
        errors = validate_chunks(text, chunks, args.max_chars)
        for err in errors:
            print(f"CHECK FAIL: {err}", file=sys.stderr)
        if errors:
            return 1
        print(f"check: {len(chunks)} chunks, offsets exact, max {max(c['n_chars'] for c in chunks)} chars, full coverage",
              file=sys.stderr)
    lines = "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks) + "\n"
    try:
        if args.output:
            args.output.write_text(lines, encoding="utf-8")
        else:
            sys.stdout.write(lines)
    except OSError as exc:
        print(f"ERROR: cannot write output: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
