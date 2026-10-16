# Evidence for owner-run checks

Files here record checks that only the owner can perform. They are referenced by ACCEPTANCE_TESTS Q-08/Q-09 and
by `docs/SETUP_ACCOUNTS.md`.

| Expected file | Check |
|---|---|
| `anthropic-workspace-limits.png` | Workspace `almamlaka-assistant`: spend limit $20/month and rate limits (Q-08) |
| `anthropic-auto-reload-off.png` | Billing: auto-reload OFF (Q-08) |
| `gcp-budget.png` | $25 budget on this project only, credits excluded, alerts 50/80/100% (Q-09) |
| `gcp-spend-caps.png` or a note in this file | Spend Caps on Cloud Run and Agent Platform, or "not available on trial account" (Q-09) |
| `gcp-verify.txt` | Output of `APPLY=1 bash infra/07_verify.sh` (Q-09) |

Before committing a file, check it contains **no API key, invite token or other secret**. `gcp-verify.txt`
also contains the owner's Google account e-mail, so replace it with `user:<owner>` before committing.
Committed files ship in the source zip.
