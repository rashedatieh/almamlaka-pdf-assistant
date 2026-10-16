"""Conflict-aware retrieval: the known cross-document disagreements of the corpus, as groups of chunk ids.

The groups come from the verified Executive report (tools/conflict_map.py reads its "Where the documents
disagree" section, whose every side passed the verifier) and are stored as data/index/conflicts.json. When
retrieval returns one side of a known disagreement, the orchestrator adds the other sides, so a broad
question ("Summarize the project") can never show one document's value without the other's (brief
requirement 4). Groups never add text the verifier hasn't checked: they only widen the evidence offered.
"""

from __future__ import annotations

import json
from pathlib import Path

INDEX = Path(__file__).resolve().parents[2] / "data" / "index"


def load_conflict_groups(index_dir: Path = INDEX, known: set[str] | None = None) -> list[list[str]]:
    path = index_dir / "conflicts.json"
    if not path.is_file():
        return []
    groups = [g["chunks"] for g in json.loads(path.read_text(encoding="utf-8"))["groups"]]
    if known is not None:
        groups = [[c for c in g if c in known] for g in groups]
    return [g for g in groups if len(g) >= 2]


def expand(chunk_ids: list[str], groups: list[list[str]]) -> list[str]:
    """chunk_ids plus every missing member of any group the RETRIEVED chunks touch (not transitive: a chunk
    added for one disagreement never pulls in another, and the result doesn't depend on group order)."""
    found = set(chunk_ids)
    out = list(chunk_ids)
    for group in groups:
        if found.intersection(group):
            out += [c for c in group if c not in out]
    return out
