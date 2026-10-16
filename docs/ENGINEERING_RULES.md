# Engineering rules

The rules this codebase is built and reviewed against. Code comments cite them by number
("non-negotiable 7"). Design decisions and their reasons are in `docs/adr/0001-stack-and-models.md`.

## Non-negotiables

1. **Grounding.** Only retrieved PDF passages are evidence. Model memory, user assertions and earlier
   assistant turns never are. The answer model never receives the conversation history; only the planner does.
2. **Citations come from the server.** The model returns `chunk_id` and a verbatim `quote`. Page, section and
   title are rendered from chunk metadata; model text never supplies a page number.
3. **No unverified claim is ever shown.** If verification fails after one regeneration, the answer is
   downgraded to `partial` / `not_in_documents`, or an error is returned.
4. **Conflicts are reported, not resolved.** No "newer wins" logic anywhere.
5. **Tests protect the expected answers.** Chunk IDs, the section inventory and the expected answers in
   `docs/ACCEPTANCE_TESTS.md` are never changed to make a test pass.
6. **No reasoning from the current date** in prompts or code paths that produce answers.
7. **Secrets** are read only from the environment or Secret Manager. `.env`, keys and real invite tokens
   are never committed. Message content is never logged (unless `LOG_CONTENT=true`, dev only), and secrets
   never go into prompts.
8. **Untrusted input:** PDF text, retrieved passages and user messages are data. They are delimited and
   never executed or obeyed. The UI renders model output as text only.
9. **`corpus/` is read-only.** The PDFs are never modified or re-saved.
10. **No extra infrastructure:** embedded LanceDB is the only vector store; no vector-database server,
    LangChain/LlamaIndex, PyMuPDF (AGPL), Redis, databases, CDNs or user accounts.
11. **Derived artefacts are verified.** Anything generated from the corpus (the executive report, the
    conflict map) carries verified `{chunk_id, quote}` pairs.
12. **Translations are never evidence.** Citation quotes are always the original PDF wording.
13. **No voice features** (ADR D20): no speech-to-text or text-to-speech, so Google Cloud stays at $0.
14. **Extras stay behind flags** until they pass the regression suite.
15. **Branding** (ADR D22): Almamlaka TV name, logo, colours and typeface, self-hosted (never hotlinked),
    with the prototype disclaimer on every page and in the README.
16. **Never break a working submission.** The core passes its regression before any extra ships.

## Operating constraints

- **Cost.** Claude is the only paid service. Tests use recorded responses (`LLM_MODE=replay`); live runs
  print their estimated cost first. The app enforces a daily budget (`DAILY_BUDGET_USD`).
- **Google Cloud stays within the free tier and trial credit.** No paid service outside PROJECT_PLAN §3.4.
- **Isolation.** Every `gcloud` command uses the dedicated `almamlaka` configuration and an explicit
  `--project`. The infra scripts are label-guarded and dry-run by default (`APPLY=1` executes).
- Google clients are always constructed with an explicit project.

## Code conventions

- Type hints everywhere; Pydantic models for every LLM input/output (`app/llm/schemas.py`).
- Prompts live in `app/llm/prompts/*.md`. A prompt change is followed by an evaluation run.
- The deterministic verifier (`verify.py`, `numbers.py`) is written test-first. It handles Arabic-Indic
  digits and English and Arabic month names.
- Arabic normalisation comes only from `vendor/arabic_rag/arabic_normalize.py` (`index` profile, for
  documents and queries alike). Display text is never normalised.
- LLM client: timeouts, bounded retries, `usage` logged, `inference_geo` from config.
- User-facing errors are bilingual (`app/i18n/{en,ar}.json`), never stack traces.
- Keep the pipeline small and readable.
