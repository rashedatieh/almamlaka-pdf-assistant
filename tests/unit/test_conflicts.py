"""Conflict-aware retrieval: one side of a known disagreement brings in the others."""

from __future__ import annotations

from app.pipeline.report import load_chunks
from app.retrieval.conflicts import expand, load_conflict_groups


def test_groups_are_the_documented_budget_and_launch_disagreements() -> None:
    groups = load_conflict_groups(known=set(load_chunks()))
    assert ["OVR-p1-s3", "BUD-p1-s1", "BUD-p1-s2"] in groups
    assert ["OVR-p1-s3", "BUD-p2-s3", "GOV-p1-s3"] in groups


def test_expand_adds_missing_sides_after_the_ranked_chunks() -> None:
    groups = [["OVR-p1-s3", "BUD-p1-s2"], ["OVR-p1-s3", "GOV-p1-s3"]]
    assert expand(["BUD-p1-s2", "OVR-p2-s4"], groups) == ["BUD-p1-s2", "OVR-p2-s4", "OVR-p1-s3"]
    assert expand(["GOV-p1-s3"], groups) == ["GOV-p1-s3", "OVR-p1-s3"]  # never cascades into the budget
    assert expand(["GOV-p1-s3"], list(reversed(groups))) == ["GOV-p1-s3", "OVR-p1-s3"]
    assert expand(["OVR-p2-s4"], groups) == ["OVR-p2-s4"]
