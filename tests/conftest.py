"""Test-wide guardrails: tests never see a real API key and never leave replay mode (Q-04)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _replay_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "replay")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


# The public repository does not redistribute Almamlaka TV's PDFs, their page images or the shipped report
# PDFs (README "Knowledge base"). Tests that read those files skip, with this reason, when they are absent;
# every other test, including the whole answering pipeline on the committed index, still runs.
_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
_HAS_PDFS = any((_ROOT / "corpus").glob("*.pdf"))
_HAS_PAGES = any((_ROOT / "data" / "derived" / "pages").glob("*.png"))
_HAS_REPORT_PDFS = any((_ROOT / "data" / "reports").glob("*.pdf"))
_NEEDS = {
    "test_corpus_manifest.py": _HAS_PDFS,
    "test_ingest_oracle.py": _HAS_PDFS,
    "test_ingest_build.py": _HAS_PDFS and _HAS_PAGES,
    "test_chunk_inventory.py::test_table_chunks_contain_every_cell_of_the_source_table": _HAS_PDFS,
    "test_report_pdf.py::test_shipped_pdf_matches_saved_report": _HAS_REPORT_PDFS,
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip = pytest.mark.skip(reason="needs the client PDFs / rendered pages, not redistributed publicly")
    for item in items:
        if any(key in item.nodeid and not present for key, present in _NEEDS.items()):
            item.add_marker(skip)
