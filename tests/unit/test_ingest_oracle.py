"""ING-02 (pdftotext oracle) and ING-03 (budget table arithmetic) on the committed index.

ING-02 names poppler's `pdftotext`. It is found through $PDFTOTEXT, then PATH, then the copy that
Git for Windows ships in mingw64/bin (that one is xpdf 4, a close relative, not poppler). Locally the
check is skipped when no tool is found. CI installs poppler-utils and sets REQUIRE_PDFTOTEXT=1, so
there the tool must exist and must be poppler: CI is the authoritative ING-02 gate.
Comparison uses app.textnorm.for_match, the same rule the M3 verifier uses for quotes (J-02).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.textnorm import for_match

ROOT = Path(__file__).resolve().parents[2]
CHUNKS = [
    json.loads(line)
    for line in (ROOT / "data" / "index" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
]


def find_pdftotext() -> str | None:
    if os.environ.get("PDFTOTEXT"):
        return os.environ["PDFTOTEXT"]
    if found := shutil.which("pdftotext"):
        return found
    git = shutil.which("git")
    if git:  # Git for Windows: <Git>/cmd/git.exe and <Git>/mingw64/bin/pdftotext.exe
        bundled = Path(git).resolve().parents[1] / "mingw64" / "bin" / "pdftotext.exe"
        if bundled.is_file():
            return str(bundled)
    return None


def pdftotext_raw(pdf: Path, page: int) -> str:
    tool = find_pdftotext()
    required = os.environ.get("REQUIRE_PDFTOTEXT") == "1"
    if tool is None:
        if required:
            pytest.fail("pdftotext is required here (REQUIRE_PDFTOTEXT=1) but is not on PATH")
        pytest.skip("pdftotext (poppler) not on PATH")
    if required:
        version = subprocess.run([tool, "-v"], capture_output=True, text=True, timeout=30, check=False)  # noqa: S603
        assert "poppler" in (version.stdout + version.stderr).lower(), "CI must use poppler's pdftotext"
    result = subprocess.run(  # noqa: S603 - fixed arguments, resolved executable
        [tool, "-raw", "-enc", "UTF-8", "-f", str(page), "-l", str(page), str(pdf), "-"],
        capture_output=True,
        check=True,
        timeout=60,
    )
    return result.stdout.decode("utf-8")


@pytest.mark.parametrize("chunk", CHUNKS, ids=lambda c: c["chunk_id"])
def test_ing02_chunk_text_is_in_pdftotext_output(chunk: dict) -> None:
    oracle = for_match(pdftotext_raw(ROOT / "corpus" / chunk["file"], chunk["pdf_page"]))
    assert for_match(chunk["text"]) in oracle


def money(cell: str) -> int:
    assert re.fullmatch(r"\$\d{1,3}(,\d{3})*", cell), cell
    return int(cell[1:].replace(",", ""))


def test_ing03_budget_table_rows_and_columns_sum_to_the_stated_totals() -> None:
    (table,) = next(c for c in CHUNKS if c["chunk_id"] == "BUD-p1-s1")["tables"]
    assert table["header"] == ["Quarter", "Development", "Marketing", "Operations", "Total"]
    quarters, total_row = table["rows"][:-1], table["rows"][-1]
    assert total_row[0] == "Total"
    for row in quarters:
        assert sum(money(cell) for cell in row[1:4]) == money(row[4]), row[0]
    for column in range(1, 5):
        assert sum(money(row[column]) for row in quarters) == money(total_row[column])
    assert money(total_row[4]) == 2_400_000
