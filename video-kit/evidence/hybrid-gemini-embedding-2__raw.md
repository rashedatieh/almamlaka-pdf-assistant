# Retrieval run `hybrid-gemini-embedding-2__raw`

gold: gold-v1 (48 rows) · planner: - · planner prompt sha d56f40557d57 · live spend this run: $0.0000

| Slice | recall@1 | recall@3 | recall@5 | recall@8 | MRR@10 |
|---|---|---|---|---|---|
| overall | 0.78 | 0.94 | 0.99 | 1.00 | 0.95 |
| arabic | 0.73 | 0.98 | 1.00 | 1.00 | 0.96 |

Conflict evidence (both sides retrieved): {'C-01': True, 'C-03': True, 'B-08': True, 'C-02': True, 'B-09': True}
A-13 retrieves all three documents: True
Recall@5 misses: {'C-03': ['OVR-p1-s3']}
