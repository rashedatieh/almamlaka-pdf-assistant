# gold-v1: retrieval gold set

`gold-v1.jsonl` has one row per case in ACCEPTANCE_TESTS sections A–E (48 rows). It is the yardstick for the
M2 retrieval gates in ACCEPTANCE_TESTS §M:
- recall@5 ≥ 0.95 overall and ≥ 0.90 on the Arabic slice;
- both sides of C1/C2 retrieved.

Fields follow the toolkit's JSONL format (`vendor/arabic_rag/retrieval_metrics.py`):
`qid`, `question`, `variety`, `relevant_ids`, `answerable`. Two extra fields: `history` (earlier user turns for
a follow-up) and `note` (the judgment call, if any).

## How it was derived (2026-10-15)

The set was derived twice, independently, from ACCEPTANCE_TESTS.md; the results agreed on all 48 rows. The
rules are below. **Rows change only when ACCEPTANCE_TESTS changes**, with owner approval (docs/ENGINEERING_RULES.md
non-negotiable 5).

| Rule | Applied as |
|---|---|
| Rows | Every A–E case except **B-12**, which runs on the fixture corpus |
| `question` | The exact text, without annotations such as "(Levantine)" or "*(follow-up to C-01)*" |
| `variety` | The annotation if there is one. Otherwise Arabic is `msa`, Arabic mixed with English words is `mixed`, and an English question is `english`, even when it asks for an Arabic reply |
| `relevant_ids` | The "Must cite" IDs. For "any: X, Y", **both** X and Y (stricter, and both contain the answer). IDs marked optional or "(+ …)" are left out |
| `answerable` | `true` for answered or partial; `false` for not_in_documents |
| `history` | C-03 follows C-01 |

Recall is `found / len(relevant_ids)`, so a case like A-01 (any: OVR-p1-s3, GOV-p1-s1) scores 1.0 only when
both chunks are retrieved.

**A-13** ("Summarize the three documents") has no single relevant chunk. Its relevant set is empty, so recall
skips it, and the retrieval harness checks instead that ≥1 chunk from each of OVR, BUD and GOV is retrieved.
