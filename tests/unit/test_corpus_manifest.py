"""corpus/corpus_manifest.json matches the read-only PDFs and PROJECT_PLAN §1.1."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools import corpus_manifest as cm

# PROJECT_PLAN §1.1 access-check table, kept independent of the manifest file.
PLAN_INVENTORY = {
    "OVR": ("Almamlaka_Project_Overview.pdf", 3511, 2),
    "BUD": ("Almamlaka_Budget_Timeline.pdf", 3787, 2),
    "GOV": ("Almamlaka_Team_Governance.pdf", 3682, 2),
}


def test_manifest_matches_corpus() -> None:
    assert cm.verify() == []


def test_manifest_matches_plan_inventory() -> None:
    manifest = json.loads(cm.MANIFEST_PATH.read_text(encoding="utf-8"))
    got = {d["doc_id"]: (d["file"], d["bytes"], d["pages"]) for d in manifest["documents"]}
    assert got == PLAN_INVENTORY
    assert all(len(d["sha256"]) == 64 for d in manifest["documents"])


def test_verify_detects_a_changed_pdf(tmp_path: Path) -> None:
    # Works on copies only: corpus/ is never modified.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for name in cm.DOC_IDS:
        shutil.copyfile(cm.CORPUS_DIR / name, corpus / name)
    manifest = corpus / "corpus_manifest.json"
    manifest.write_text(json.dumps(cm.build(corpus)), encoding="utf-8")
    assert cm.verify(corpus, manifest) == []

    with (corpus / "Almamlaka_Budget_Timeline.pdf").open("ab") as fh:
        fh.write(b"\n%tampered\n")
    problems = cm.verify(corpus, manifest)
    assert any("sha256" in p for p in problems)
    assert any("bytes" in p for p in problems)


def test_verify_detects_an_extra_pdf(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for name in cm.DOC_IDS:
        shutil.copyfile(cm.CORPUS_DIR / name, corpus / name)
    manifest = corpus / "corpus_manifest.json"
    manifest.write_text(json.dumps(cm.build(corpus)), encoding="utf-8")
    shutil.copyfile(cm.CORPUS_DIR / "Almamlaka_Project_Overview.pdf", corpus / "extra.pdf")
    assert cm.verify(corpus, manifest)
