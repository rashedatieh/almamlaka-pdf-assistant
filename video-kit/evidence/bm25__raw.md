# Retrieval run `bm25__raw`

gold: gold-v1 (48 rows) · planner: - · planner prompt sha d56f40557d57 · live spend this run: $0.0000

| Slice | recall@1 | recall@3 | recall@5 | recall@8 | MRR@10 |
|---|---|---|---|---|---|
| overall | 0.52 | 0.67 | 0.69 | 0.69 | 0.65 |
| arabic | 0.02 | 0.12 | 0.14 | 0.14 | 0.11 |

Conflict evidence (both sides retrieved): {'C-01': True, 'C-03': False, 'B-08': False, 'C-02': False, 'B-09': True}
A-13 retrieves all three documents: False
Recall@5 misses: {'B-01': ['GOV-p1-s1', 'OVR-p1-s3'], 'B-02': ['OVR-p1-s2'], 'B-04': ['OVR-p2-s4'], 'B-05': ['GOV-p1-s1'], 'B-06': ['GOV-p2-s5'], 'B-07': ['OVR-p2-s4'], 'B-08': ['BUD-p1-s2', 'OVR-p1-s3'], 'B-11': ['BUD-p2-s3'], 'B-13': ['GOV-p2-s6'], 'C-02': ['BUD-p2-s3', 'GOV-p1-s3', 'OVR-p1-s3'], 'C-03': ['OVR-p1-s3'], 'D-03': ['BUD-p1-s1', 'BUD-p1-s2'], 'E-07': ['GOV-p2-s4']}
