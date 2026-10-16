# Retrieval run `bm25__planner`

gold: gold-v1 (48 rows) · planner: claude-sonnet-5-5 · planner prompt sha d56f40557d57 · live spend this run: $0.1443

| Slice | recall@1 | recall@3 | recall@5 | recall@8 | MRR@10 |
|---|---|---|---|---|---|
| overall | 0.75 | 0.97 | 1.00 | 1.00 | 0.94 |
| arabic | 0.73 | 0.96 | 1.00 | 1.00 | 0.95 |

Conflict evidence (both sides retrieved): {'C-01': True, 'C-03': True, 'B-08': True, 'C-02': True, 'B-09': True}
A-13 retrieves all three documents: True
Recall@5 misses: none
