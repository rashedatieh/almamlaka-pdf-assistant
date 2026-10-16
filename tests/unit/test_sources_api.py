"""Evidence spotlight API (app/sources_api.py): page images, quote highlight boxes, invite gate."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.pipeline.render import citation
from app.sources_api import INDEX, PAGES, SourceIndex, make_router, merge_lines

INDEX_SOURCE = SourceIndex()
QUOTE = "Total Approved Budget: $2,400,000"

needs_pages = pytest.mark.skipif(
    not (PAGES / "OVR-p1.png").is_file(), reason="run make index to render pages"
)


def client(invited: bool = True) -> TestClient:
    app = FastAPI()

    def gate(_: Request) -> bool:
        return invited

    app.include_router(make_router(gate, INDEX_SOURCE))
    return TestClient(app)


def budget_citation() -> dict[str, object]:
    chunks = {
        c["chunk_id"]: c for c in map(json.loads, (INDEX / "chunks.jsonl").read_text("utf-8").splitlines())
    }
    return citation(1, chunks["OVR-p1-s3"], QUOTE)


def test_merge_lines_splits_wrapped_text_and_skips_separators() -> None:
    boxes = [(10, 100, 15, 110), None, (16, 100, 20, 110), (10, 112, 14, 122), (15, 112, 30, 122)]
    assert merge_lines(boxes) == [(10, 100, 20, 110), (10, 112, 30, 122)]


def test_budget_quote_highlights_exactly_its_line() -> None:
    cit = budget_citation()
    assert cit["quote"] == QUOTE
    response = client().get(
        "/api/sources/spotlight", params={"chunk": "OVR-p1-s3", "start": cit["start"], "end": cit["end"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["docId"], body["pdfPage"], body["section"]) == ("OVR", 1, "3. Key Details")
    assert body["imageUrl"].startswith("/api/sources/page/OVR/1.png?v=")
    assert (body["width"], body["height"]) == (1224, 1584)
    assert len(body["boxes"]) == 1
    (box,) = body["boxes"]
    assert 0 <= box["x"] and box["x"] + box["w"] <= body["width"]
    assert 0 <= box["y"] and box["y"] + box["h"] <= body["height"]

    # The box covers the characters of that line and nothing from the lines above or below it.
    chars = [b for b in INDEX_SOURCE.boxes["OVR-p1-s3"][cit["start"] : cit["end"]] if b]
    scale = 1224 / 612
    assert (
        box["x"] <= min(b[0] for b in chars) * scale
        and box["x"] + box["w"] >= max(b[2] for b in chars) * scale
    )
    assert (
        box["y"] <= min(b[1] for b in chars) * scale
        and box["y"] + box["h"] >= max(b[3] for b in chars) * scale
    )
    text = INDEX_SOURCE.chunks["OVR-p1-s3"]["text"]
    line_above = INDEX_SOURCE.boxes["OVR-p1-s3"][text.index("Project Lead")]
    line_below = INDEX_SOURCE.boxes["OVR-p1-s3"][text.index("Planned Launch")]
    assert line_above and line_below
    assert box["y"] >= line_above[3] * scale - 2 and box["y"] + box["h"] <= line_below[1] * scale + 2


def test_quote_without_offsets_is_located_server_side() -> None:
    cit = budget_citation()
    got = client().get("/api/sources/spotlight", params={"chunk": "OVR-p1-s3", "quote": QUOTE}).json()
    want = (
        client()
        .get(
            "/api/sources/spotlight", params={"chunk": "OVR-p1-s3", "start": cit["start"], "end": cit["end"]}
        )
        .json()
    )
    assert got == want


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"chunk": "OVR-p9-s9", "start": 0, "end": 4}, 404),
        ({"chunk": "../manifest", "start": 0, "end": 4}, 404),
        ({"chunk": "OVR-p1-s3", "start": 0, "end": 10_000}, 400),
        ({"chunk": "OVR-p1-s3", "start": -1, "end": 4}, 422),
        ({"chunk": "OVR-p1-s3", "quote": "not in this chunk at all"}, 400),
    ],
)
def test_spotlight_rejects_unknown_chunks_and_bad_spans(params: dict[str, object], status: int) -> None:
    assert client().get("/api/sources/spotlight", params=params).status_code == status


@needs_pages
def test_page_image_is_served_immutable() -> None:
    response = client().get("/api/sources/page/OVR/1.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "immutable" in response.headers["cache-control"]
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize(
    "path",
    [
        "/api/sources/page/OVR/9.png",
        "/api/sources/page/XYZ/1.png",
        "/api/sources/page/ovr/1.png",
        "/api/sources/page/OVR/1a.png",
        "/api/sources/page/OVR/-1.png",
        "/api/sources/page/OVR/%2E%2E%2Fmanifest.png",
        "/api/sources/page/..%2Findex/1.png",
        "/api/sources/page/OVR/..%5C..%5Cindex%5Cmanifest.png",
        "/api/sources/page/OVR/../../index/manifest.json",
    ],
)
def test_page_traversal_and_unknown_pages_are_rejected(path: str) -> None:
    response = client().get(path)
    assert response.status_code == 404
    assert not response.content.startswith(b"\x89PNG")


def test_routes_need_the_invite() -> None:
    gated = client(invited=False)
    assert gated.get("/api/sources/page/OVR/1.png").status_code == 401
    assert (
        gated.get("/api/sources/spotlight", params={"chunk": "OVR-p1-s3", "start": 0, "end": 4}).status_code
        == 401
    )
