# End-to-end run `record` on gold-v1 (48 questions)

| Slice | abstention | citation hit | reply language | conflict flagged |
|---|---|---|---|---|
| overall | 48/48 (100%) | 39/40 (98%) | 47/47 (100%) | 5/5 (100%) |
| english | 33/33 (100%) | 25/26 (96%) | 33/33 (100%) | 2/2 (100%) |
| arabic varieties | 15/15 (100%) | 14/14 (100%) | 14/14 (100%) | 3/3 (100%) |

Latency: median 8.2s, p90 15.84s, max 33.89s. Spend: $0.6580 ($0.0137 per turn).

Failures:
- A-04 (english): status=partial lang=en flags=[] cited=['BUD-p1-s2'] — The Budget & Timeline Breakdown states that these quarterly figures reflect the originally approved budget.
