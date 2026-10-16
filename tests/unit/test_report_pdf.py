"""Executive report PDF (tools/report_pdf.py, app/report_pdf_api.py): HTML, bidi, router, rendering."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.pipeline import report as reports
from app.pipeline.render import citation
from app.report_pdf_api import make_router, saved_pdf
from tools import report_pdf

CHUNKS = reports.load_chunks()
NNBSP = chr(0x202F)
INJECTION = '<script>alert("x")</script><img src=x onerror=alert(1)>'


def fake_report(lang: str, text: str = "Plain statement.") -> dict[str, Any]:
    """A report shaped like app.pipeline.report.assemble, with citations built from real chunks."""
    cites = [
        citation(1, CHUNKS["OVR-p1-s3"], "Total Approved Budget: $2,400,000"),
        citation(2, CHUNKS["BUD-p1-s1"], "Q1 2027 | $450,000 | $120,000 | $60,000 | $630,000"),
        citation(3, CHUNKS["BUD-p1-s1"], "Q2 2027 | $500,000 | $150,000 | $70,000 | $720,000"),
        citation(4, CHUNKS["BUD-p1-s1"], "Q3 2027 | $400,000 | $100,000 | $60,000 | $560,000"),
        citation(5, CHUNKS["BUD-p1-s2"], "the total project budget was adjusted to $2,600,000"),
        citation(6, CHUNKS["OVR-p1-s3"], "Project Duration: 14 months"),
    ]
    paragraphs = {
        "summary": [{"text": text, "citations": [1]}],
        "glance": [{"text": "The project duration is 14 months.", "citations": [6]}],
        "budget": [
            {"text": "Q1, Q2 and Q3 allocations restated.", "citations": [2, 3, 4]},
            {"text": "Q1 alone.", "citations": [2]},
        ],
        "timeline": [{"text": reports.EMPTY[lang], "citations": []}],
        "team_governance": [{"text": reports.EMPTY[lang], "citations": []}],
        "disagreements": [{"text": "Overview $2,400,000; Breakdown $2,600,000.", "citations": [1, 5]}],
        "risks": [{"text": "A risk.", "citations": [6]}],
    }
    return {
        "lang": lang,
        "title": reports.TITLES[lang]["report"],
        "sections": [
            {"id": s, "title": reports.TITLES[lang][s], "paragraphs": paragraphs[s]} for s in reports.SECTIONS
        ],
        "citations": cites,
        "model": reports.REPORT_MODEL,
        "templateVersion": reports.TEMPLATE_VERSION,
        "claimsVerified": 8,
        "claimsRemoved": 0,
    }


def saved_reports() -> list[tuple[str, dict[str, Any]]]:
    found = [(lang, reports.load(lang)) for lang in report_pdf.LANGS]
    return [(lang, saved) for lang, saved in found if saved is not None]


# ---- HTML builder ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_every_text_value_is_escaped(lang: str) -> None:
    report = fake_report(lang, text=INJECTION)
    report["citations"][0] = {**report["citations"][0], "quote": INJECTION, "section": INJECTION}
    report["title"] = INJECTION
    document = report_pdf.build_html(report, CHUNKS, lang)
    assert "<script" not in document
    assert "<img src=x" not in document
    assert "&lt;script&gt;" in document


def test_arabic_latin_runs_are_isolated() -> None:
    out = report_pdf.isolate_latin("تطبيق الهاتف المحمول (iOS وAndroid) بمجموع $2,400,000.")
    assert '<bdi dir="ltr">iOS</bdi>' in out
    assert f'و{NNBSP}<bdi dir="ltr">Android</bdi>)' in out
    assert '<bdi dir="ltr">$2,400,000</bdi>.' in out  # the sentence's full stop stays Arabic
    named = report_pdf.isolate_latin("قناة المملكة (Almamlaka TV)")
    assert named.endswith('<bdi dir="ltr">Almamlaka TV</bdi>)')
    assert report_pdf.isolate_latin("من 1 آذار/مارس").endswith('<span class="nw">آذار/مارس</span>')
    assert "<b>" not in report_pdf.isolate_latin("<b>نص</b>")


def test_english_text_is_not_wrapped() -> None:
    assert report_pdf.txt("iOS & Android", "en") == "iOS &amp; Android"


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_sections_citations_and_document_shell(lang: str) -> None:
    report = fake_report(lang)
    document = report_pdf.build_html(report, CHUNKS, lang)
    assert f'<html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}">' in document
    for section in report["sections"]:
        assert f"sec-{section['id']}" in document
        assert report_pdf.txt(section["title"], lang) in document
    for c in report["citations"]:
        assert f'<span class="cite">[{c["n"]}]</span>' in document
        assert f'<span class="src-n">[{c["n"]}]</span>' in document  # Sources appendix
    assert report_pdf.STRINGS[lang]["prototype"].split(" — ")[0] in document
    assert "http://" not in document.replace("http://www.w3.org/", "")  # no external resources
    assert "https://" not in document


def test_budget_table_comes_from_chunk_metadata_and_replaces_restatements() -> None:
    document = report_pdf.build_html(fake_report("en"), CHUNKS, "en")
    for cell in ("Q4 2027", "$350,000", "$1,700,000", "$2,400,000"):  # BUD-p1-s1 tables, cited or not
        assert f">{cell}</td>" in document
    assert 'class="src"><span class="cites"><span class="cite">[2]</span>' in document  # row Q1 -> [2]
    assert "Q1, Q2 and Q3 allocations restated." not in document  # three rows: the table carries it
    assert "Q1 alone." in document  # one row: kept


def test_disputed_values_are_flagged_not_resolved() -> None:
    document = report_pdf.build_html(fake_report("en"), CHUNKS, "en")
    total_row = re.search(r'<tr class="row total">.*?</tr>', document)
    assert total_row and "Disputed" in total_row.group(0)  # $2,400,000 is cited under disagreements
    q1_row = re.search(r'<tr class="row">(?:(?!</tr>).)*Q1 2027.*?</tr>', document)
    assert q1_row and "Disputed" not in q1_row.group(0)
    assert 'class="conflict"' in document and "Total Approved Budget: $2,400,000" in document


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_no_current_date(lang: str) -> None:
    document = report_pdf.build_html(fake_report(lang), CHUNKS, lang)
    today = dt.date.today()
    for shown in (today.isoformat(), today.strftime("%B %d, %Y"), today.strftime("%d/%m/%Y")):
        assert shown not in document
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", document)
    assert "Date(" not in document and "Generated on" not in document


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_saved_reports_render_completely(lang: str) -> None:
    saved = reports.load(lang)
    if saved is None:
        pytest.skip(f"no saved {lang} report")
    document = report_pdf.build_html(saved, CHUNKS, lang)
    for c in saved["citations"]:
        assert f'<span class="src-n">[{c["n"]}]</span>' in document
    conflicts = next(s for s in saved["sections"] if s["id"] == "disagreements")["paragraphs"]
    assert document.count('class="conflict"') == len([p for p in conflicts if p["citations"]])


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_shipped_pdf_matches_saved_report(lang: str) -> None:
    if reports.load(lang) is None:
        pytest.skip(f"no saved {lang} report")
    path = saved_pdf(lang)
    assert path == report_pdf.pdf_path(lang)
    assert path.is_file(), "run make report-pdf after make report"
    assert path.read_bytes()[:5] == b"%PDF-"


# ---- router ---------------------------------------------------------------------------------------------


def client(tmp_path: Path, invited: bool = True) -> TestClient:
    def gate(_: Request) -> bool:
        return invited

    app = FastAPI()
    app.include_router(make_router(gate, locate=lambda lang: tmp_path / f"executive-{lang}.pdf"))
    return TestClient(app)


def test_router_requires_invite(tmp_path: Path) -> None:
    (tmp_path / "executive-en.pdf").write_bytes(b"%PDF-1.7 test")
    assert client(tmp_path, invited=False).get("/api/report.pdf?lang=en").status_code == 401


def test_router_404_when_not_built(tmp_path: Path) -> None:
    assert client(tmp_path).get("/api/report.pdf?lang=ar").status_code == 404


def test_router_serves_pdf_download(tmp_path: Path) -> None:
    (tmp_path / "executive-ar.pdf").write_bytes(b"%PDF-1.7 test")
    response = client(tmp_path).get("/api/report.pdf?lang=ar")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert 'filename="Almamlaka-DEI-Executive-Report-AR.pdf"' in disposition
    assert response.content == b"%PDF-1.7 test"


def test_router_rejects_other_languages(tmp_path: Path) -> None:
    assert client(tmp_path).get("/api/report.pdf?lang=fr").status_code == 422


# ---- rendering (needs Playwright with Microsoft Edge) ----------------------------------------------------


def _edge_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch(channel="msedge").close()
    except Exception:
        return False
    return True


def test_render_pdf_produces_a4_pages(tmp_path: Path) -> None:
    if not _edge_available():
        pytest.skip("Playwright with the msedge channel is not available")
    from pypdf import PdfReader

    out = tmp_path / "report.pdf"
    report_pdf.render_pdf(report_pdf.build_html(fake_report("ar"), CHUNKS, "ar"), out)
    reader = PdfReader(out)
    assert len(reader.pages) >= 3  # cover, body, sources
    box = reader.pages[0].mediabox
    assert round(float(box.width)) == 595 and round(float(box.height)) == 842  # A4 in points
