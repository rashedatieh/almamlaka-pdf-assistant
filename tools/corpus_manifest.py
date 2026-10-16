"""Build or verify corpus/corpus_manifest.json (doc ID, file, bytes, pages, SHA-256).

The PDFs in corpus/ are read-only (docs/ENGINEERING_RULES.md non-negotiable 9); this tool only reads them.

Usage:
  uv run python -m tools.corpus_manifest            # verify (default); exit 1 on any mismatch
  uv run python -m tools.corpus_manifest --write    # (re)write the manifest; only after an
                                                    # owner-approved corpus change
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "corpus"
MANIFEST_PATH = CORPUS_DIR / "corpus_manifest.json"
# Doc IDs from PROJECT_PLAN §1.1; chunk IDs are built from them ({DOC}-p{page}-s{section}).
DOC_IDS = {
    "Almamlaka_Project_Overview.pdf": "OVR",
    "Almamlaka_Budget_Timeline.pdf": "BUD",
    "Almamlaka_Team_Governance.pdf": "GOV",
}


def describe(pdf: Path) -> dict[str, object]:
    data = pdf.read_bytes()
    return {
        "doc_id": DOC_IDS[pdf.name],
        "file": pdf.name,
        "bytes": len(data),
        "pages": len(PdfReader(pdf).pages),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def build(corpus_dir: Path = CORPUS_DIR) -> dict[str, object]:
    return {
        "schema_version": 1,
        "documents": [describe(corpus_dir / name) for name in DOC_IDS],
    }


def verify(corpus_dir: Path = CORPUS_DIR, manifest_path: Path = MANIFEST_PATH) -> list[str]:
    """Return a list of human-readable problems; empty means the corpus matches the manifest."""
    if not manifest_path.is_file():
        return [f"manifest missing: {manifest_path}"]
    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    pdfs_on_disk = sorted(p.name for p in corpus_dir.glob("*.pdf"))
    if pdfs_on_disk != sorted(DOC_IDS):
        problems.append(f"corpus/ PDFs {pdfs_on_disk} != expected {sorted(DOC_IDS)}")
        return problems
    actual = build(corpus_dir)
    if recorded != actual:
        for want, got in zip(recorded.get("documents", []), actual["documents"], strict=False):
            for key in ("doc_id", "file", "bytes", "pages", "sha256"):
                if want.get(key) != got[key]:
                    problems.append(f"{got['file']}: {key} manifest={want.get(key)!r} actual={got[key]!r}")
        if not problems:
            problems.append("manifest structure differs from the computed one")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--write", action="store_true", help="write the manifest instead of verifying it")
    args = parser.parse_args(argv)
    if args.write:
        MANIFEST_PATH.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {MANIFEST_PATH.relative_to(ROOT)}")
        return 0
    problems = verify()
    for problem in problems:
        print(f"corpus-manifest: MISMATCH - {problem}", file=sys.stderr)
    if problems:
        return 1
    print(f"corpus-manifest: ok - {len(DOC_IDS)} PDFs match {MANIFEST_PATH.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
