"""Write data/index/conflicts.json from the verified English Executive report ($0, no model call).

  uv run python -m tools.conflict_map

Each paragraph of the report's "disagreements" section is one known disagreement; its citations name the
chunks that hold each side. See app/retrieval/conflicts.py.
"""

from __future__ import annotations

import json
import sys

from app.pipeline import report
from app.retrieval.conflicts import INDEX


def main() -> int:
    saved = report.load("en")
    if saved is None:
        print("no saved English report; run make report first", file=sys.stderr)
        return 1
    by_n = {c["n"]: c["chunkId"] for c in saved["citations"]}
    section = next(s for s in saved["sections"] if s["id"] == "disagreements")
    groups = []
    for para in section["paragraphs"]:
        chunks = list(dict.fromkeys(by_n[n] for n in para["citations"] if n in by_n))
        if len({c.split("-")[0] for c in chunks}) >= 2:
            groups.append({"summary": para["text"][:160], "chunks": chunks})
    out = {"source": "executive report (en), disagreements section", "groups": groups}
    (INDEX / "conflicts.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(groups)} groups: {[g['chunks'] for g in groups]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
