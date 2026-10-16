"""Print-quality PDF of the saved Executive report (ADR D24), one per language.

  uv run python -m tools.report_pdf --lang en|ar|all
  -> data/reports/executive-<lang>-<key>.pdf (same key as the saved report JSON), served by app.report_pdf_api

The browser's print of the report dialog captured the whole app and lost the layout, so the PDF is built
here once from the saved report and shipped with it. The HTML is self-contained (fonts and logo as data URIs,
no network) and printed to A4 by Chromium (Playwright, Edge channel) with CSS @page margin boxes for the
running header, the footer attribution and "page X of Y".

Content rules (docs/ENGINEERING_RULES.md non-negotiables):
- Every text value is HTML-escaped; model text is only ever text.
- Citations and sources come from the saved report, whose citations were built from chunk metadata.
- Tables are copied cell by cell from chunk metadata (`tables`) of a chunk the section cites; a row carries
  the citation whose quote is exactly that row. A paragraph that only restates three or more rows of a
  table shown in the same section is represented by the table (the budget figures read as a table, not as
  a run-on sentence); nothing is added that the report or the chunk does not contain.
- A key fact or table row that shares a dollar amount or a date with a quote cited under "Where the
  documents disagree" is marked "Disputed" and points there. Nothing is resolved.
- No current date appears anywhere (non-negotiable 6).
- Arabic: every Latin or number run is isolated (<bdi dir="ltr">), so "(iOS وAndroid)" and "$2,400,000"
  keep their order inside right-to-left text.
"""

from __future__ import annotations

import argparse
import base64
import html
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.pipeline import report as reports

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "web" / "public" / "fonts"  # brand assets: not in the public repository
LOGO = ROOT / "web" / "public" / "brand" / "almamlaka-logo.webp"
LANGS = ("en", "ar")
TABLE_SECTIONS = frozenset({"budget", "timeline", "team_governance"})
RESTATED_ROWS = 3  # a paragraph citing this many rows of a table shown with it is represented by the table

# (file, weight range, ascent, descent): the metric overrides web/src/index.css uses for the same files.
FONT_FILES = (
    ("ALMAMLAKAFONT-Light.woff2", "300", "90%", "10%"),
    ("ALMAMLAKAFONT-Medium.woff2", "400 600", "90%", "10%"),
    ("ALMAMLAKAFONT-Extrabold.woff2", "700 900", "80%", "20%"),
)

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "based_on": "Based on the three DEI project documents",
        "doc_meta": "{pages} pages · {sections} sections",
        "verified": "statements verified",
        "citations": "citations to the documents",
        "disagreements": "disagreements reported",
        "removed": "statements removed",
        "model": "Drafted by {model} from template {template}. Every statement was checked against the "
        "quoted passage before it was kept.",
        "how_to_read": "Each statement ends with bracketed source numbers such as [3]. The Sources appendix "
        "gives the document, PDF page, section and the verbatim quote for every number. Where the documents "
        "disagree, the report shows each side and does not pick one.",
        "prototype": "Prototype by Rashed Atieh for evaluation — not an official Almamlaka TV product",
        "header": "Executive report · Digital Expansion Initiative",
        "page": 'counter(page) " of " counter(pages)',
        "page_prefix": "Page ",
        "key_facts": "Key facts",
        "key_facts_note": "As stated in the Project Overview Document.",
        "disputed": "Disputed — see “{section}”",
        "disputed_short": "Disputed",
        "source": "Source",
        "table_lang": "",
        "disagreement": "Disagreement {i} of {n}",
        "positions": "What each document says",
        "sources": "Sources",
        "sources_note": "Each number used in the report, with the passage it rests on. Quotes are verbatim "
        "from the documents.",
        "pdf_page": "PDF page {page}",
        "printed": "printed page {label}",
    },
    "ar": {
        "based_on": "استناداً إلى وثائق مبادرة التوسع الرقمي الثلاث",
        "doc_meta": "{pages} صفحة · {sections} أقسام",
        "verified": "عبارة تم التحقق منها",
        "citations": "استشهاداً بالوثائق",
        "disagreements": "مواضع اختلاف مرصودة",
        "removed": "عبارات محذوفة",
        "model": "صاغه النموذج {model} وفق القالب {template}. تم التحقق من كل عبارة مقابل المقطع المقتبس "
        "قبل إبقائها.",
        "how_to_read": "تنتهي كل عبارة بأرقام مصادر بين قوسين مثل [3]. يذكر ملحق المصادر لكل رقم الوثيقة "
        "وصفحة PDF والقسم والاقتباس الحرفي. وحيث تختلف الوثائق، يعرض التقرير كل موقف ولا يرجّح أحدها.",
        "prototype": "نموذج أولي من إعداد راشد عطية لأغراض التقييم — ليس منتجاً رسمياً لقناة المملكة",
        "header": "التقرير التنفيذي · مبادرة التوسع الرقمي",
        "page": 'counter(page) " من " counter(pages)',
        "page_prefix": "صفحة ",
        "key_facts": "حقائق رئيسية",
        "key_facts_note": "كما وردت في وثيقة نظرة عامة على المشروع (النص الأصلي بالإنجليزية).",
        "disputed": "قيمة متنازع عليها — انظر «{section}»",
        "disputed_short": "متنازع عليها",
        "source": "المصدر",
        "table_lang": "الجدول منقول كما ورد في الوثيقة بلغتها الأصلية.",
        "disagreement": "الاختلاف {i} من {n}",
        "positions": "ما تقوله كل وثيقة",
        "sources": "المصادر",
        "sources_note": "كل رقم ورد في التقرير مع المقطع الذي يستند إليه. الاقتباسات حرفية من الوثائق "
        "بلغتها الأصلية (الإنجليزية).",
        "pdf_page": "صفحة PDF {page}",
        "printed": "الصفحة المطبوعة {label}",
    },
}
# Field labels of the Project Overview's "Key Details" list, shown in Arabic beside the verbatim value.
FACT_LABELS_AR = {
    "Project Lead": "قائد المشروع",
    "Total Approved Budget": "إجمالي الميزانية المعتمدة",
    "Planned Launch Date": "موعد الإطلاق المخطط",
    "Project Duration": "مدة المشروع",
}

KEY_FACT = re.compile(r"^([A-Z][A-Za-z ]{2,40}):\s+(\S.{0,60})$")
MONEY = re.compile(r"\$\d[\d,]*")
DATE = re.compile(r"\b(?:[A-Z][a-z]{2,8}) \d{1,2}, \d{4}\b")
NUMERIC_CELL = re.compile(r"^[$\d]")
# One Latin/number piece, and a run of them joined by spaces (or " - ") inside Arabic text.
_PIECE = r"[$A-Za-z0-9&][A-Za-z0-9$%&'\u2019.,/:+\-]*"
LATIN_RUN = re.compile(_PIECE + r"(?:(?: [-\u2013])? +" + _PIECE + r")*")
TRAILING = ".,:;-\u2013"
# A one-letter Arabic prefix (waw, ba, lam, kaf, fa) written straight onto a Latin run gets a narrow
# no-break space, so the conjunction does not read as glued to the end of the Latin word.
PREFIX_BEFORE_RUN = re.compile(r"(?:^|(?<=[\s(\u00ab\"]))[\u0648\u0628\u0644\u0643\u0641]$")
NNBSP = "\u202f"
# An Arabic month pair such as "Adhar/March" written with a slash never breaks at the slash.
ARABIC_PAIR = re.compile(r"[\u0600-\u06ff]+/[\u0600-\u06ff]+")


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _arabic(text: str) -> str:
    return ARABIC_PAIR.sub(lambda m: f'<span class="nw">{m.group(0)}</span>', esc(text))


def isolate_latin(text: str) -> str:
    """Escape Arabic text and isolate each Latin/number run as left-to-right (<bdi dir="ltr">)."""
    out: list[str] = []
    pos = 0
    for match in LATIN_RUN.finditer(text):
        run = match.group(0).rstrip(TRAILING)
        if not run:
            continue
        start = match.start()
        before = text[pos:start]
        if PREFIX_BEFORE_RUN.search(before):
            before += NNBSP
        out.append(_arabic(before))
        out.append(f'<bdi dir="ltr">{esc(run)}</bdi>')
        pos = start + len(run)
    out.append(_arabic(text[pos:]))
    return "".join(out)


def txt(text: str, lang: str) -> str:
    """Model or document text as safe HTML for the report language."""
    return isolate_latin(text) if lang == "ar" else esc(text)


def ltr(text: str, lang: str) -> str:
    """A verbatim (English) value: isolated left-to-right inside an Arabic document."""
    return f'<bdi dir="ltr">{esc(text)}</bdi>' if lang == "ar" else esc(text)


def chips(numbers: Iterable[int]) -> str:
    """Bracketed citation numbers, kept together on one line."""
    inner = "".join(f'<span class="cite">[{int(n)}]</span>' for n in numbers)
    return f'<span class="cites">{inner}</span>' if inner else ""


def value_tokens(text: str) -> set[str]:
    return set(MONEY.findall(text)) | set(DATE.findall(text))


def pdf_path(lang: str) -> Path:
    return reports.report_path(lang).with_suffix(".pdf")


def _data_uri(path: Path, mime: str) -> str:
    """The file as a data URI, or "" when it is absent (the brand assets are not redistributed publicly)."""
    if not path.is_file():
        return ""
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def font_faces() -> str:
    return "\n".join(
        f'@font-face {{ font-family: "ALMAMLAKAFONT"; src: url("{_data_uri(FONTS / name, "font/woff2")}") '
        f'format("woff2"); font-weight: {weight}; font-style: normal; ascent-override: {ascent}; '
        f"descent-override: {descent}; line-gap-override: 0%; }}"
        for name, weight, ascent, descent in FONT_FILES
        if (FONTS / name).is_file()  # without the brand font the PDF uses the fallback stack
    )


def header_logo() -> str:
    """The logo at header size: an SVG wrapper, because a margin box cannot size an image."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="76" height="22.5" viewBox="0 0 159 47">'
        f'<image width="159" height="47" xlink:href="{_data_uri(LOGO, "image/webp")}"/></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


# ---- building blocks -----------------------------------------------------------------------------------


class Context:
    """The saved report plus lookups shared by the HTML builders."""

    def __init__(self, report: dict[str, Any], chunks: dict[str, dict[str, Any]], lang: str) -> None:
        self.report = report
        self.chunks = chunks
        self.lang = lang
        self.s = STRINGS[lang]
        self.cites = {int(c["n"]): c for c in report["citations"]}
        sections = {s["id"]: s for s in report["sections"]}
        conflict = sections.get("disagreements", {"paragraphs": [], "title": ""})
        self.conflict_title = conflict["title"]
        self.conflicts = [p for p in conflict["paragraphs"] if p["citations"]]
        self.disputed: set[str] = set()
        for paragraph in self.conflicts:
            for n in paragraph["citations"]:
                if n in self.cites:
                    self.disputed |= value_tokens(self.cites[n]["quote"])

    def is_disputed(self, text: str) -> bool:
        return bool(value_tokens(text) & self.disputed)

    def flag(self, short: bool = False) -> str:
        label = self.s["disputed_short"] if short else self.s["disputed"].format(section=self.conflict_title)
        return f'<span class="flag">{esc(label)}</span>'

    def documents(self) -> list[dict[str, Any]]:
        docs: dict[str, dict[str, Any]] = {}
        for chunk in self.chunks.values():
            doc = docs.setdefault(
                chunk["doc_id"],
                {"subtitle": chunk["doc_subtitle"], "file": chunk["file"], "pages": 0, "sections": set()},
            )
            doc["pages"] = max(doc["pages"], int(chunk["pdf_page"]))
            doc["sections"].add(chunk["section"])
        return list(docs.values())


def paragraph(ctx: Context, p: dict[str, Any], cls: str = "") -> str:
    empty = "" if p["citations"] else " empty"
    return f'<p class="para{empty}{cls}">{txt(p["text"], ctx.lang)}{chips(p["citations"])}</p>'


def key_facts(ctx: Context) -> str:
    """Label: value lines the report cites verbatim (the Project Overview's Key Details list)."""
    seen: set[str] = set()
    tiles = []
    for n in sorted(ctx.cites):
        match = KEY_FACT.match(ctx.cites[n]["quote"].strip())
        if not match or match.group(1) in seen:
            continue
        label, value = match.group(1), match.group(2)
        seen.add(label)
        shown = FACT_LABELS_AR.get(label, label) if ctx.lang == "ar" else label
        label_html = esc(shown) if shown != label else ltr(label, ctx.lang)
        flag = ctx.flag() if ctx.is_disputed(value) else ""
        tiles.append(
            f'<div class="fact"><div class="fact-label">{label_html}</div>'
            f'<div class="fact-value">{ltr(value, ctx.lang)}{chips([n])}</div>{flag}</div>'
        )
    if not tiles:
        return ""
    cols = len(tiles) if len(tiles) <= 3 else 2
    return (
        f'<div class="facts" style="--cols: {cols}"><div class="facts-head">'
        f"<span>{esc(ctx.s['key_facts'])}</span>"
        f'<span class="facts-note">{esc(ctx.s["key_facts_note"])}</span></div>'
        f'<div class="fact-grid">{"".join(tiles)}</div></div>'
    )


def _row_key(cells: Iterable[str]) -> str:
    return " | ".join(" ".join(str(c).split()) for c in cells)


def section_tables(ctx: Context, section: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Tables of the chunks this section cites, and the paragraphs the tables do not already carry."""
    table_chunks: list[str] = []
    for p in section["paragraphs"]:
        for n in p["citations"]:
            chunk_id = ctx.cites[n]["chunkId"] if n in ctx.cites else ""
            if ctx.chunks.get(chunk_id, {}).get("tables") and chunk_id not in table_chunks:
                table_chunks.append(chunk_id)
    if not table_chunks:
        return "", section["paragraphs"]

    row_cites: dict[str, int] = {}  # row text -> citation number, for the table chunks only
    for n, c in sorted(ctx.cites.items()):
        if c["chunkId"] in table_chunks:
            row_cites.setdefault(_row_key(c["quote"].split("|")), n)

    blocks = []
    row_numbers: set[int] = set()
    for chunk_id in table_chunks:
        chunk = ctx.chunks[chunk_id]
        used: set[int] = set()
        tables = []
        for table in chunk["tables"]:
            head = "".join(f"<th>{esc(h)}</th>" for h in table["header"])
            rows = []
            for row in table["rows"]:
                n = row_cites.get(_row_key(row))
                if n is not None:
                    used.add(n)
                total = " total" if str(row[0]).strip().lower() == "total" else ""
                kinds = ["num" if NUMERIC_CELL.match(str(cell).strip()) else "txt" for cell in row]
                cells = "".join(f'<td class="{k}">{esc(c)}</td>' for k, c in zip(kinds, row, strict=True))
                flag = ctx.flag(short=True) if ctx.is_disputed(" ".join(map(str, row))) else ""
                src = chips([n]) if n is not None else ""
                rows.append(f'<tr class="row{total}">{cells}<td class="src">{src}{flag}</td></tr>')
            tables.append(
                f'<table class="data" dir="ltr"><thead><tr>{head}'
                f'<th class="src">{esc(ctx.s["source"])}</th></tr></thead>'
                f"<tbody>{''.join(rows)}</tbody></table>"
            )
        row_numbers |= used
        others = sorted(n for n, c in ctx.cites.items() if c["chunkId"] == chunk_id and n not in used)
        caption = " · ".join(
            [
                f"{esc(ctx.s['source'])}: {ltr(chunk['doc_subtitle'], ctx.lang)}",
                txt(ctx.s["pdf_page"].format(page=int(chunk["pdf_page"])), ctx.lang),
                ltr(chunk["section"], ctx.lang),
            ]
        )
        note = f'<span class="table-lang">{esc(ctx.s["table_lang"])}</span>' if ctx.s["table_lang"] else ""
        blocks.append(
            f'<figure class="table-wrap">{"".join(tables)}'
            f"<figcaption>{caption}{chips(others)}{note}</figcaption></figure>"
        )

    def restated(p: dict[str, Any]) -> bool:
        ns = [n for n in p["citations"] if n in ctx.cites]
        return (
            bool(ns)
            and all(ctx.cites[n]["chunkId"] in table_chunks for n in ns)
            and len(set(ns) & row_numbers) >= RESTATED_ROWS
        )

    return "".join(blocks), [p for p in section["paragraphs"] if not restated(p)]


def disagreement(ctx: Context, p: dict[str, Any], i: int, total: int) -> str:
    """One reported conflict: the verified narrative, then each document's own quoted words."""
    by_doc: dict[str, list[int]] = {}
    for n in p["citations"]:
        if n in ctx.cites:
            by_doc.setdefault(ctx.cites[n]["docSubtitle"], []).append(n)
    sides = "".join(
        f'<div class="side-doc">{ltr(doc, ctx.lang)}</div><div class="side-quotes" dir="ltr">'
        + "".join(
            f'<div class="side-quote">{chips([n])}<q>{esc(ctx.cites[n]["quote"])}</q></div>' for n in ns
        )
        + "</div>"
        for doc, ns in by_doc.items()
    )
    return (
        f'<div class="conflict"><div class="conflict-head">'
        f"{esc(ctx.s['disagreement'].format(i=i, n=total))}</div>"
        f"{paragraph(ctx, p)}"
        f'<div class="positions-head">{esc(ctx.s["positions"])}</div>'
        f'<div class="sides">{sides}</div></div>'
    )


def body_section(ctx: Context, index: int, section: dict[str, Any]) -> str:
    sid = section["id"]
    parts: list[str] = []
    paragraphs = section["paragraphs"]
    if sid == "glance":
        parts.append(key_facts(ctx))
    if sid in TABLE_SECTIONS:
        tables, paragraphs = section_tables(ctx, section)
        parts.append(tables)
    if sid == "disagreements" and ctx.conflicts:
        n = len(ctx.conflicts)
        parts += [disagreement(ctx, p, i + 1, n) for i, p in enumerate(ctx.conflicts)]
        paragraphs = [p for p in paragraphs if not p["citations"]]
    parts += [paragraph(ctx, p, " risk" if sid == "risks" else "") for p in paragraphs]
    parts = [part for part in parts if part]
    first, rest = (parts[0], parts[1:]) if parts else ("", [])
    # The heading travels with the first block, so a heading never ends a page.
    return (
        f'<section class="sec sec-{esc(sid)}"><div class="keep">'
        f'<div class="sec-head"><span class="sec-num">{index:02d}</span>'
        f"<h2>{txt(section['title'], ctx.lang)}</h2></div>{first}</div>{''.join(rest)}</section>"
    )


def cover(ctx: Context) -> str:
    eyebrow, _, main = ctx.report["title"].partition(":")
    if not main:
        eyebrow, main = "", ctx.report["title"]
    docs = "".join(
        f'<div class="doc"><div class="doc-num">{i:02d}</div>'
        f'<div class="doc-title">{ltr(d["subtitle"], ctx.lang)}</div>'
        f'<div class="doc-file">{ltr(d["file"], ctx.lang)}</div>'
        f'<div class="doc-meta">'
        f"{esc(ctx.s['doc_meta'].format(pages=d['pages'], sections=len(d['sections'])))}</div></div>"
        for i, d in enumerate(ctx.documents(), start=1)
    )
    stats = [
        (ctx.report.get("claimsVerified", 0), ctx.s["verified"]),
        (len(ctx.report["citations"]), ctx.s["citations"]),
        (len(ctx.conflicts), ctx.s["disagreements"]),
        (ctx.report.get("claimsRemoved", 0), ctx.s["removed"]),
    ]
    stat_html = "".join(
        f'<div class="stat"><div class="stat-n">{int(v)}</div><div class="stat-l">{esc(label)}</div></div>'
        for v, label in stats
    )
    model = esc(ctx.s["model"]).format(
        model=ltr(ctx.report["model"], ctx.lang), template=ltr(ctx.report["templateVersion"], ctx.lang)
    )
    return f"""
<div class="cover">
  <div class="cover-band"></div>
  <div class="cover-body">
    <img class="cover-logo" src="{_data_uri(LOGO, "image/webp")}" alt="{esc("قناة المملكة")}">
    <div class="eyebrow">{txt(eyebrow.strip(), ctx.lang)}</div>
    <h1>{txt(main.strip(), ctx.lang)}</h1>
    <div class="rule"></div>
    <p class="based-on">{esc(ctx.s["based_on"])}</p>
    <div class="docs">{docs}</div>
    <div class="stats">{stat_html}</div>
  </div>
  <div class="cover-foot">
    <p class="model">{model}</p>
    <p class="how">{txt(ctx.s["how_to_read"], ctx.lang)}</p>
    <p class="proto">{esc(ctx.s["prototype"])}</p>
  </div>
</div>"""


def sources(ctx: Context) -> str:
    items = []
    for n in sorted(ctx.cites):
        c = ctx.cites[n]
        where = [ctx.s["pdf_page"].format(page=int(c["pdfPage"]))]
        if c.get("printedLabel"):
            where.append(ctx.s["printed"].format(label=c["printedLabel"]))
        meta = " · ".join(txt(w, ctx.lang) for w in where)
        items.append(
            f'<li class="src-item"><span class="src-n">[{n}]</span><div class="src-body">'
            f'<div class="src-meta"><b>{ltr(c["docSubtitle"], ctx.lang)}</b> · {meta} · '
            f"{ltr(c['section'], ctx.lang)}</div>"
            f'<blockquote dir="ltr">“{esc(c["quote"])}”</blockquote></div></li>'
        )
    return (
        f'<section class="sources"><div class="keep"><div class="sec-head"><span class="sec-num">'
        f"{len(ctx.report['sections']) + 1:02d}</span><h2>{esc(ctx.s['sources'])}</h2></div>"
        f'<p class="sources-note">{esc(ctx.s["sources_note"])}</p></div>'
        f'<ol class="src-list">{"".join(items)}</ol></section>'
    )


# ---- document ------------------------------------------------------------------------------------------

CSS = """
:root { --red: #9e0b0f; --navy: #1b2431; --navy2: #273142; --grey: #5d5d5d; --line: #e0e0e0;
  --tint: #f8eded; --amber: #ff9600; --amber-bg: #fff4e5; --amber-fg: #7a4300; --amber-line: #f3d3a6;
  --muted: #f5f5f5; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: "ALMAMLAKAFONT", "Segoe UI", Arial, sans-serif; color: var(--navy); font-weight: 400;
  font-size: 10.5pt; line-height: 1.62; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
html[lang="ar"] body { font-size: 11pt; line-height: 1.85; }
bdi { unicode-bidi: isolate; }
.nw { white-space: nowrap; }

@page { size: A4; margin: 28mm 19mm 22mm 19mm;
  @top-left { content: url("{{LOGO_SVG}}"); vertical-align: bottom; padding-bottom: 2.6mm;
    margin-bottom: 5mm; border-bottom: 0.6pt solid var(--red); }
  @top-center { content: ""; margin-bottom: 5mm; border-bottom: 0.6pt solid var(--red); }
  @top-right { content: "{{HEADER}}"; vertical-align: bottom; padding-bottom: 3mm;
    font-family: "ALMAMLAKAFONT"; font-size: 8pt; font-weight: 400; color: var(--grey);
    margin-bottom: 5mm; border-bottom: 0.6pt solid var(--red); }
  @bottom-{{FOOT_TEXT}} { content: "{{PROTOTYPE}}"; vertical-align: top; padding-top: 3mm;
    font-family: "ALMAMLAKAFONT"; font-size: 7pt; color: var(--grey); width: 75%; }
  @bottom-{{FOOT_PAGE}} { content: "{{PAGE_PREFIX}}" {{PAGE}}; vertical-align: top; padding-top: 3mm;
    font-family: "ALMAMLAKAFONT"; font-size: 8pt; font-weight: 700; color: var(--navy); }
}
@page :first { margin: 0;
  @top-left { content: none; border: 0; } @top-center { content: none; border: 0; }
  @top-right { content: none; border: 0; } @bottom-left { content: none; } @bottom-right { content: none; } }

/* ---- cover ---- */
.cover { position: relative; height: 296mm; overflow: hidden; break-after: page; display: flex;
  flex-direction: column; }
.cover-band { height: 9mm; background: var(--red); }
.cover-body { flex: 1; padding: 24mm 22mm 0; }
.cover-logo { width: 46mm; height: auto; display: block; margin-bottom: 20mm; }
.eyebrow { color: var(--red); font-weight: 700; font-size: 11pt; letter-spacing: 0.18em;
  text-transform: uppercase; }
html[lang="ar"] .eyebrow { letter-spacing: 0; font-size: 14pt; }
h1 { font-size: 30pt; line-height: 1.12; font-weight: 800; margin: 4mm 0 0; color: var(--navy);
  max-width: 150mm; }
html[lang="ar"] h1 { line-height: 1.35; }
.rule { width: 22mm; height: 1.6mm; background: var(--red); margin: 8mm 0 7mm; }
.based-on { font-size: 12.5pt; color: var(--navy2); margin: 0 0 6mm; }
.docs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4mm; }
.doc { border: 0.6pt solid var(--line); border-top: 1.4mm solid var(--navy); padding: 4mm 4mm 3.5mm;
  background: #fff; }
.doc-num { color: var(--red); font-weight: 800; font-size: 13pt; line-height: 1; margin-bottom: 2.5mm; }
.doc-title { font-weight: 700; font-size: 10.5pt; line-height: 1.3; min-height: 2.6em; }
.doc-file { font-size: 7.5pt; color: var(--grey); margin-top: 1.5mm; word-break: break-all; }
.doc-meta { font-size: 8pt; color: var(--grey); margin-top: 1mm; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); margin-top: 10mm;
  border-top: 0.6pt solid var(--line); border-bottom: 0.6pt solid var(--line); }
.stat { padding: 4.5mm 3mm; border-inline-start: 0.6pt solid var(--line); }
.stat:first-child { border-inline-start: 0; padding-inline-start: 0; }
.stat-n { font-size: 22pt; font-weight: 800; color: var(--red); line-height: 1.1; }
.stat-l { font-size: 8.5pt; color: var(--grey); line-height: 1.35; margin-top: 1mm; }
.cover-foot { background: var(--navy); color: #fff; padding: 9mm 22mm 10mm; }
.cover-foot p { margin: 0; }
.model { font-size: 9pt; color: #fff; }
.how { font-size: 9pt; color: #c9cfd8; margin-top: 2.5mm !important; line-height: 1.55; }
.proto { font-size: 8.5pt; font-weight: 700; margin-top: 5mm !important; padding-top: 4mm;
  border-top: 0.6pt solid rgba(255,255,255,.25); }

/* ---- sections ---- */
.sec { margin: 0 0 8mm; }
.keep { break-inside: avoid; }
.sec-head { display: flex; align-items: baseline; gap: 3mm; padding-bottom: 2.4mm; margin-bottom: 4mm;
  border-bottom: 0.6pt solid var(--line); position: relative; break-after: avoid; }
.sec-head::after { content: ""; position: absolute; inset-inline-start: 0; bottom: -1pt; width: 16mm;
  height: 2pt; background: var(--red); }
.sec-num { color: var(--red); font-weight: 800; font-size: 11pt; }
h2 { margin: 0; font-size: 16pt; line-height: 1.25; font-weight: 800; color: var(--navy); }
.para { margin: 0 0 3.2mm; orphans: 3; widows: 3; text-align: start; }
.para.empty { color: var(--grey); font-style: italic; }
.sec-summary .para { font-size: 11.5pt; line-height: 1.7; }
html[lang="ar"] .sec-summary .para { font-size: 12pt; line-height: 1.9; }
.para.risk { border-inline-start: 1.2mm solid var(--red); background: var(--tint); padding: 3mm 4mm;
  break-inside: avoid; }
.cites { white-space: nowrap; }
.cite { display: inline-block; color: var(--red); font-weight: 700; font-size: 0.86em; line-height: 1;
  padding: 0.4mm 0.9mm; margin-inline-start: 0.9mm; background: var(--tint); border-radius: 1mm;
  direction: ltr; unicode-bidi: isolate; white-space: nowrap; font-variant-numeric: tabular-nums;
  vertical-align: 0.05em; }
.flag { display: inline-block; font-size: 7.5pt; font-weight: 700; color: var(--amber-fg);
  background: var(--amber-bg); border: 0.6pt solid var(--amber); border-radius: 1mm; padding: 0.3mm 1.4mm;
  line-height: 1.4; white-space: nowrap; }

/* key facts */
.facts { border: 0.6pt solid var(--line); border-top: 1.2mm solid var(--red); background: var(--muted);
  padding: 4mm 5mm 4.5mm; margin: 0 0 5mm; break-inside: avoid; }
.facts-head { display: flex; justify-content: space-between; align-items: baseline; gap: 4mm;
  margin-bottom: 3mm; }
.facts-head span:first-child { font-weight: 800; font-size: 11pt; }
.facts-note { font-size: 8pt; color: var(--grey); }
.fact-grid { display: grid; grid-template-columns: repeat(var(--cols, 2), minmax(0, 1fr)); gap: 3mm; }
.fact .flag { white-space: normal; }
.fact { background: #fff; border: 0.6pt solid var(--line); padding: 3mm 3.5mm; }
.fact-label { font-size: 8pt; color: var(--grey); text-transform: uppercase; letter-spacing: 0.06em; }
html[lang="ar"] .fact-label { text-transform: none; letter-spacing: 0; font-size: 9pt; }
.fact-value { font-size: 14pt; font-weight: 800; line-height: 1.3; margin: 0.8mm 0 1mm; }
.fact-value .cite { font-size: 8pt; vertical-align: 0.25em; }

/* tables */
.table-wrap { margin: 0 0 5mm; break-inside: avoid; }
table.data { width: 100%; border-collapse: collapse; font-size: 9.5pt; line-height: 1.4;
  font-variant-numeric: tabular-nums; }
table.data th { background: var(--navy); color: #fff; font-weight: 700; text-align: left;
  padding: 2.2mm 3mm; }
table.data td { padding: 2mm 3mm; border-bottom: 0.6pt solid var(--line); }
table.data tbody tr:nth-child(even) td { background: #fafafa; }
table.data td.num { text-align: right; white-space: nowrap; }
table.data th:not(:first-child):not(.src) { text-align: right; }
table.data td.src, table.data th.src { text-align: right; white-space: nowrap; width: 1%; }
table.data td.src .cite { margin: 0; }
table.data td.src .flag { margin-left: 1.2mm; }
table.data tr.total td { font-weight: 800; background: var(--tint) !important;
  border-top: 1.2pt solid var(--navy); border-bottom: 1.2pt solid var(--navy); }
table.data tr { break-inside: avoid; }
.sec-timeline table.data td.num, .sec-team_governance table.data td.num { text-align: left; }
.sec-timeline table.data th:not(.src), .sec-team_governance table.data th:not(.src) { text-align: left; }
figcaption { font-size: 8pt; color: var(--grey); margin-top: 1.8mm; }
figcaption .cite { font-size: 7.5pt; }
.table-lang { display: block; }

/* disagreements */
.conflict { border: 0.6pt solid var(--amber); border-inline-start: 1.6mm solid var(--amber);
  background: var(--amber-bg); padding: 3.2mm 4.5mm 3.8mm; margin: 0 0 4.5mm; break-inside: avoid; }
.conflict-head { font-size: 8.5pt; font-weight: 800; color: var(--amber-fg); text-transform: uppercase;
  letter-spacing: 0.08em; margin-bottom: 2mm; }
html[lang="ar"] .conflict-head { letter-spacing: 0; font-size: 10pt; }
.conflict .para { margin-bottom: 2mm; line-height: 1.5; }
html[lang="ar"] .conflict .para { line-height: 1.75; }
.positions-head { font-size: 8pt; font-weight: 700; color: var(--amber-fg); margin: 0 0 1.2mm; }
.sides { display: grid; grid-template-columns: 47mm 1fr; background: #fff;
  border: 0.6pt solid var(--amber-line); }
.side-doc, .side-quotes { padding: 1.8mm 3mm; border-top: 0.6pt solid var(--amber-line); }
.side-doc:first-child, .side-doc:first-child + .side-quotes { border-top: 0; }
.side-doc { font-weight: 700; font-size: 8.5pt; line-height: 1.35; background: #fffaf2; }
.side-quote { display: flex; gap: 2mm; align-items: baseline; font-size: 8.8pt; line-height: 1.45; }
.side-quote + .side-quote { margin-top: 1.2mm; }
.side-quote .cite { margin: 0; flex: none; }
.side-quote q { quotes: "\\201C" "\\201D"; color: var(--navy2); }

/* sources */
.sources { break-before: page; }
.sources-note { font-size: 9pt; color: var(--grey); margin: 0 0 4mm; }
.src-list { list-style: none; margin: 0; padding: 0; }
.src-item { display: grid; grid-template-columns: 11mm 1fr; gap: 2mm; padding: 2.2mm 0;
  border-bottom: 0.6pt solid var(--line); break-inside: avoid; }
.src-n { color: var(--red); font-weight: 800; font-size: 9.5pt; }
.src-meta { font-size: 8.5pt; color: var(--grey); line-height: 1.45; }
.src-meta b { color: var(--navy); }
blockquote { margin: 1mm 0 0; font-size: 9pt; line-height: 1.5; color: var(--navy2); text-align: left; }
"""


def _css_string(text: str) -> str:
    """A CSS string literal body for the margin boxes."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("<", "\\3C ")


def build_html(report: dict[str, Any], chunks: dict[str, dict[str, Any]], lang: str) -> str:
    """The self-contained report document (no external resources, no current date)."""
    ctx = Context(report, chunks, lang)
    s = ctx.s
    rtl = lang == "ar"
    css = (
        CSS.replace("{{LOGO_SVG}}", header_logo())
        .replace("{{HEADER}}", _css_string(s["header"]))
        .replace("{{PROTOTYPE}}", _css_string(s["prototype"]))
        .replace("{{PAGE_PREFIX}}", _css_string(s["page_prefix"]))
        .replace("{{PAGE}}", s["page"])
        .replace("{{FOOT_TEXT}}", "right" if rtl else "left")
        .replace("{{FOOT_PAGE}}", "left" if rtl else "right")
    )
    if rtl:  # mirror the header: logo on the right, running title on the left
        css = css.replace("@top-left { content: url", "@top-right { content: url", 1).replace(
            '@top-right { content: "', '@top-left { content: "', 1
        )
    body = "".join(body_section(ctx, i, sec) for i, sec in enumerate(report["sections"], start=1))
    return (
        f'<!doctype html><html lang="{esc(lang)}" dir="{"rtl" if rtl else "ltr"}"><head>'
        f'<meta charset="utf-8"><title>{esc(report["title"])}</title>'
        f"<style>{font_faces()}{css}</style></head><body>"
        f'{cover(ctx)}<main class="content">{body}</main>{sources(ctx)}</body></html>'
    )


def render_pdf(document: str, out: Path) -> None:
    """Print the HTML to an A4 PDF with Chromium (Edge channel). No network: everything is inline."""
    from playwright.sync_api import sync_playwright  # dev dependency, needed only to build the PDF

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.abort())  # nothing may load from outside the document
            page.set_content(document, wait_until="load")
            page.evaluate("document.fonts.ready.then(() => true)")
            page.pdf(path=str(out), format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            browser.close()


def build(lang: str) -> Path:
    saved = reports.load(lang)
    if saved is None:
        raise FileNotFoundError(f"no saved {lang} report for this corpus and template: run make report first")
    out = pdf_path(lang)
    render_pdf(build_html(saved, reports.load_chunks(), lang), out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the saved executive report(s) to A4 PDF.")
    parser.add_argument("--lang", choices=[*LANGS, "all"], default="all")
    args = parser.parse_args(argv)
    status = 0
    for lang in LANGS if args.lang == "all" else (args.lang,):
        try:
            out = build(lang)
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            status = 1
            continue
        print(f"{out.relative_to(ROOT)}  ({out.stat().st_size // 1024} KB)")
    return status


if __name__ == "__main__":
    sys.exit(main())
