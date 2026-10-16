"""User-facing messages in both languages (ENGINEERING_RULES.md: errors are bilingual; no stack traces)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent


@cache
def messages(lang: str) -> dict[str, str]:
    return json.loads((_DIR / f"{'ar' if lang == 'ar' else 'en'}.json").read_text(encoding="utf-8"))


def message(key: str, lang: str) -> str:
    return messages(lang)[key]
