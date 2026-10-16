"""ACCEPTANCE_TESTS §0 / ING-01: `make index` yields exactly these 16 chunks, with every table cell,
a clean ingest report and the corpus checksums.

The expected inventory below is copied from ACCEPTANCE_TESTS §0 and must not be edited to make a
test pass (docs/ENGINEERING_RULES.md non-negotiable 5).
"""

from __future__ import annotations

import json
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[2]
CHUNKS = ROOT / "data" / "index" / "chunks.jsonl"
MANIFEST = ROOT / "data" / "index" / "manifest.json"

OVR = "Almamlaka_Project_Overview.pdf"
BUD = "Almamlaka_Budget_Timeline.pdf"
GOV = "Almamlaka_Team_Governance.pdf"

# (chunk_id, file, pdf_page, section); printed_label is null for every chunk.
EXPECTED = [
    ("OVR-p1-s1", OVR, 1, "1. Introduction"),
    ("OVR-p1-s2", OVR, 1, "2. Project Goals"),
    ("OVR-p1-s3", OVR, 1, "3. Key Details"),
    ("OVR-p2-s4", OVR, 2, "4. Platform Scope"),
    ("OVR-p2-s5", OVR, 2, "5. Stakeholders"),
    ("OVR-p2-s6", OVR, 2, "6. Success Metrics"),
    ("BUD-p1-s1", BUD, 1, "1. Quarterly Budget Allocation"),
    ("BUD-p1-s2", BUD, 1, "2. Budget Notes"),
    ("BUD-p2-s3", BUD, 2, "3. Project Timeline"),
    ("BUD-p2-s4", BUD, 2, "4. Risk Notes"),
    ("GOV-p1-s1", GOV, 1, "1. Project Team"),
    ("GOV-p1-s2", GOV, 1, "2. Governance Structure"),
    ("GOV-p1-s3", GOV, 1, "3. Revised Launch Date"),
    ("GOV-p2-s4", GOV, 2, "4. Data Privacy Policy"),
    ("GOV-p2-s5", GOV, 2, "5. Content Moderation Policy"),
    ("GOV-p2-s6", GOV, 2, "6. Escalation Contacts"),
]


def test_expected_inventory_has_16_unique_ids() -> None:
    ids = [chunk_id for chunk_id, *_ in EXPECTED]
    assert len(ids) == 16
    assert len(set(ids)) == 16


def load_chunks() -> list[dict]:
    return [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_index_matches_section_0_inventory() -> None:
    got = [(c["chunk_id"], c["file"], c["pdf_page"], c["section"], c["printed_label"]) for c in load_chunks()]
    assert got == [(*row, None) for row in EXPECTED]


def test_chunk_kinds_match_section_0_types() -> None:
    # §0 "Type": key-value OVR-p1-s3; prose + table BUD-p1-s1; tables BUD-p2-s3 and GOV-p1-s1.
    special = {
        "OVR-p1-s3": "key-value",
        "BUD-p1-s1": "prose+table",
        "BUD-p2-s3": "table",
        "GOV-p1-s1": "table",
    }
    for chunk in load_chunks():
        assert chunk["kind"] == special.get(chunk["chunk_id"], "prose"), chunk["chunk_id"]


def test_table_chunks_contain_every_cell_of_the_source_table() -> None:
    chunks = {c["chunk_id"]: c for c in load_chunks()}
    for chunk_id, file, page, (rows, cols) in [
        ("BUD-p1-s1", BUD, 1, (6, 5)),
        ("BUD-p2-s3", BUD, 2, (7, 2)),
        ("GOV-p1-s1", GOV, 1, (6, 3)),
    ]:
        with pdfplumber.open(ROOT / "corpus" / file) as pdf:
            (source,) = pdf.pages[page - 1].extract_tables()
        assert (len(source), len(source[0])) == (rows, cols)
        chunk = chunks[chunk_id]
        (table,) = chunk["tables"]
        assert [table["header"], *table["rows"]] == source
        for row in source:
            assert " | ".join(row) in chunk["text"].splitlines()


def test_ingest_report_is_clean_and_corpus_checksums_match() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["ingest_report"] == []  # 0 hidden-text, 0 instruction-like, 0 furniture flags
    corpus = json.loads((ROOT / "corpus" / "corpus_manifest.json").read_text(encoding="utf-8"))
    assert manifest["corpus"] == corpus["documents"]
    assert manifest["chunk_ids"] == [row[0] for row in EXPECTED]


def test_document_subtitles_and_shared_heading() -> None:
    # §0: display subtitles and the shared heading "Almamlaka TV Digital Expansion Initiative".
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    got = {d["doc_id"]: (d["title"], d["subtitle"]) for d in manifest["documents"]}
    heading = "Almamlaka TV Digital Expansion Initiative"
    assert got == {
        "OVR": (heading, "Project Overview Document"),
        "BUD": (heading, "Budget & Timeline Breakdown"),
        "GOV": (heading, "Team & Governance Document"),
    }
