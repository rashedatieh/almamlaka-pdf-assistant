"""The vendored Arabic normaliser (vendor/arabic_rag) passes its own self-test."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NORMALIZER = ROOT / "vendor" / "arabic_rag" / "arabic_normalize.py"


def test_self_test_passes() -> None:
    proc = subprocess.run(  # noqa: S603 - fixed argument list
        [sys.executable, "-I", str(NORMALIZER), "--self-test"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    match = re.search(r"self-test: (\d+)/(\d+) passed", proc.stdout)
    assert match, proc.stdout
    passed, total = map(int, match.groups())
    assert total > 0
    assert passed == total


def test_profiles_used_by_the_plan_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    # PROJECT_PLAN §3.1: `index` for BM25 (docs and queries), `embed` for embedding inputs.
    spec = importlib.util.spec_from_file_location("arabic_normalize", NORMALIZER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses resolve annotations through sys.modules, so register it for the test only.
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert {"index", "embed"} <= set(module.PROFILES)
    # Arabic-Indic digits become Western digits under `index` (needed for numbers in queries).
    assert module.normalize("٢٠٢٧", module.build_options("index")) == "2027"
