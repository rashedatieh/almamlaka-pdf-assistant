<div align="center">

# Almamlaka TV Document Assistant

**A bilingual (Arabic / English) RAG chatbot that answers only from your documents, cites every sentence,
admits what it doesn't know, and flags where documents disagree.**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.143-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Claude](https://img.shields.io/badge/LLM-Claude%20Sonnet%205.5%20%7C%20Opus%205.5-D97757)
![Cloud Run](https://img.shields.io/badge/Deployed-Google%20Cloud%20Run-4285F4?logo=googlecloud&logoColor=white)
![Tests](https://img.shields.io/badge/tests-635%20passing-2ea44f)
![License](https://img.shields.io/badge/license-MIT-blue)

**[Live demo](https://almamlaka-assistant-383606437746.me-central1.run.app)** (invite link on request) ·
**[Interactive pipeline explainer](https://rashedatieh.github.io/almamlaka-pdf-assistant/video-kit/pipeline-graph.html)** ·
[Approach](#approach) · [Results](#results) · [Security](#security)

<img src="docs/images/answer-with-conflict.png" alt="A cited answer that flags a disagreement between two documents" width="900">

*Prototype by Rashed Atieh for evaluation — not an official Almamlaka TV product.*

</div>

---

## Why it exists

Organisations keep their answers in PDFs: plans, budgets, policies. A general chatbot can find those answers
in seconds, but it can also invent them, and it sounds just as confident when it does. For a broadcaster
that has to be right on air and in the boardroom, that is not acceptable.

This assistant is built the other way round. **Nothing reaches the screen unless it is quoted, word for
word, from the source documents and checked.** Every sentence links to the document, page and section it
came from, and one click opens the original PDF page with the quote highlighted. When the documents don't
say something, it says so. When two documents disagree, it shows both sides and never picks one. It works
the same way in Arabic and English.

| For | What they get |
|---|---|
| **Editors and staff** | Instant, sourced answers from internal documents, in Arabic or English |
| **Managers** | A one-click Executive report: every figure cited, every disagreement surfaced |
| **Compliance and IT** | No made-up answers, resistance to prompt injection, a fixed daily cost cap, data kept in the cloud project |

## Features

| | |
|---|---|
| <img src="docs/images/evidence-spotlight.png" alt="Evidence spotlight" width="440"> | **Evidence spotlight.** Click any citation to open the real PDF page with the quoted line highlighted. Citations are built by the server from the index; the model never types a page number. |
| <img src="docs/images/arabic-answer.png" alt="Arabic answer" width="440"> | **Arabic first, truly bilingual.** It replies in the language you ask in: Modern Standard Arabic, Levantine dialect, Arabizi or English. Layout is right to left, with Arabic-aware search and Arabic numerals and month names understood. |
| <img src="docs/images/multi-turn.png" alt="Multi-turn conversation" width="440"> | **Real conversations.** Follow-ups such as "What about its budget?" are resolved from context. The history is signed by the server, so it can't be forged. |
| <img src="docs/images/injection-refused.png" alt="Prompt injection refused" width="440"> | **Stays in scope.** Rule-change attempts ("ignore previous instructions…", «تجاهل التعليمات…») are refused before any model call. |
| <img src="docs/images/executive-report.png" alt="Executive report" width="440"> | **Executive report.** A 7-section report across all documents, verified like the chat and downloadable as a typeset A4 PDF in English or Arabic. |
| <img src="docs/images/mobile.png" alt="Mobile" width="200"> <img src="docs/images/dark-mode.png" alt="Dark mode" width="230"> | **Polished UI.** React 19, Tailwind and shadcn, with Almamlaka TV branding. Mobile-first, dark mode, accessible. |

## Architecture

```mermaid
flowchart LR
    subgraph Offline["Build time"]
        PDF["3 PDFs"] --> ING["Ingestion<br/>per-character boxes<br/>hidden-text checks"]
        ING --> IDX[("Index<br/>16 section chunks<br/>bboxes · page images")]
        IDX -.-> EMB[("Embeddings<br/>gemini-embedding-2<br/>LanceDB · measured, off")]
        IDX --> CM[("Conflict map<br/>from verified report")]
    end
    subgraph Online["Every question"]
        UI["React UI"] -->|"POST /api/chat"| API["FastAPI<br/>invite · rate limit<br/>signed history · injection guard"]
        API --> PL["Planner<br/>Claude Sonnet 5.5"]
        PL --> RET["Retrieval<br/>BM25 + RRF + diversity<br/>+ conflict partners"]
        RET --> ANS["Answer<br/>Claude Sonnet 5.5<br/>claims + quotes"]
        ANS --> VER["Verifier<br/>8 rules + support judge"]
        VER -->|"fail: regenerate once"| ANS
        VER --> REN["Render<br/>citations from index"]
        REN -->|"SSE stream"| UI
    end
    IDX --> RET
    CM --> RET
```

```mermaid
sequenceDiagram
    participant U as User
    participant S as Server
    participant P as Planner (Sonnet)
    participant A as Answer (Sonnet)
    participant V as Verifier + judge (Sonnet)
    U->>S: "What about its budget?" + signed history
    S->>S: guards: invite, rate limit, signature, injection, budget
    S->>P: message + history (only the planner sees history)
    P-->>S: standalone question + English & Arabic searches
    S->>S: BM25 retrieval + conflict partners
    S->>A: passages as untrusted <source> data (no history)
    A-->>S: claims, each with {chunk_id, verbatim quote}
    S->>V: quote-in-chunk, numbers, language, conflicts, support
    V-->>S: kept / dropped (one regeneration with feedback)
    S-->>U: cited answer + conflict flag (streamed)
```

## Approach

**Chunking.** One chunk is one numbered section of one page: 16 chunks with stable IDs like `BUD-p1-s2`.
The documents are short and organised by numbered sections, so a section is self-contained and is the
natural citation unit ("Budget & Timeline Breakdown, p.1, §2 Budget Notes"). Smaller windows would split a
budget table from its "originally approved" note; bigger ones would blur which section a fact comes from.
Tables are kept as `cell | cell` rows under their header. Every character keeps its position on the page,
which powers the highlight. Ingestion stops the build on hidden text (white on white, invisible render
modes, overprinting) and flags instruction-like text for review.

**Retrieval, the embedding model and the vector database.**
- **In production:** BM25 over Arabic-normalised text. The planner writes queries in both English and
  Arabic; the PDFs are English, so an Arabic question is also searched in English.
- **Fusion:** Reciprocal Rank Fusion (k = 50), keeping the top 8 with at least one passage per matching
  document.
- **Conflict partners:** retrieving one side of a known disagreement brings in the other sides.
- **Dense leg:** built and measured, using **`gemini-embedding-2`** (768 dimensions) vectors in an embedded
  **LanceDB** table with exact cosine search.

| Recall@5 on the 48-question gold set | Overall | Arabic questions |
|---|---|---|
| BM25, raw question | 0.69 | 0.14 |
| BM25 + embeddings, raw question | 0.99 | 1.00 |
| **BM25, planner queries (production)** | **1.00** | **1.00** |
| BM25 + embeddings, planner queries | 1.00 | 1.00 |

With bilingual planner queries, embeddings add no measurable recall. They would still cost an extra cloud
call per search, so the dense leg ships **off**, behind `DENSE_ENABLED=true`. The vectors are committed,
and any failure falls back to BM25.

**Verification:** nothing is shown unless it passes all of these.

| Rule | Check |
|---|---|
| V1 | Valid structured output; the model didn't stop early |
| J-01 | Every fact has evidence |
| V2 | The cited passage was retrieved this turn |
| V3 | The quote is verbatim in that passage |
| V4 | Every number, amount and date is in the quote, including Arabic-Indic digits and Arabic month names; derived sums are recomputed |
| V5 | A judge model confirms that the evidence supports the claim |
| V6 | A conflict has two or more documents and is never shown one-sided |
| V7 | The reply is in the user's language |
| V8 | "Framing" and "not stated" sentences carry no facts |

A failing sentence is regenerated once with feedback. If it fails again it is removed, and the answer
becomes *partial* or *not in the documents*.

**Models:**
- Claude Sonnet 5.5 for the planner, the answer and the judge.
- Claude Opus 5.5 only for the Executive report. It is generated once by the operator and saved, so a
  click costs nothing.

## Results

Live Claude on the 48-question gold set: English, Modern Standard Arabic, Levantine, Arabizi and mixed.

| | Correct answer or correct abstention | Cites a correct passage | Reply language | Conflicts flagged |
|---|---|---|---|---|
| **All** | **48/48** | **39/40** | **47/47** | **5/5** |
| Arabic varieties | 15/15 | 14/14 | 14/14 | 3/3 |

The median answer takes about 8 s and costs about $0.014. Reports are in `eval/reports/`.

## Security

1. A deterministic guard refuses rule-change and prompt-extraction attempts before any model call. It
   covers English, Arabic, Arabizi and leetspeak.
2. The planner classifies paraphrased override attempts as out of scope, even when they are mixed with a
   real question.
3. Passages and user text are wrapped as untrusted data, with tag escaping. The models have no tools and no
   internet access.
4. Every shown sentence must quote the documents verbatim, so an injected "fact" can't pass verification.
5. Ingestion removes hidden text and flags instruction-like text inside PDFs (indirect injection).
6. Assistant history is HMAC-signed; a forged or altered turn is rejected with `400 history_invalid`.

Also in place:
- an invite cookie and a per-IP rate limit (`429`);
- input length and turn caps;
- a daily Claude budget;
- a strict CSP;
- secrets in Secret Manager;
- no message content in logs.

## Run it

Requires [uv](https://docs.astral.sh/uv/), Python 3.12 and Node 24.

```bash
uv sync --locked                                  # Python dependencies
cd web && npm ci && npm run build && cd ..        # UI → web/dist
make check                                        # lint + tests; recorded model calls, no API key needed
LLM_MODE=live ANTHROPIC_API_KEY=… APP_ENV=dev uv run uvicorn app.server:app --port 8000
```

**Knowledge base.** The three source PDFs, and Almamlaka TV's logo and typeface, belong to Almamlaka TV and
are **not redistributed** in this repository. The extracted index in `data/index/` is included, so the app
and the answering tests run as is. To rebuild from the originals, put the PDFs in `corpus/` and run
`make index`. Tests that need the PDFs skip when they are absent, and the UI falls back to system fonts.

Other targets:
- `make eval-retrieval` and `uv run python -m eval.run_e2e` for the evaluations;
- `make report` / `make report-pdf` for the Executive report;
- `make smoke URL=…` for a live check;
- `infra/01…08_*.sh` for Google Cloud deployment (label-guarded, dry run by default).

## Repository map

```
app/ingest      PDF → section chunks, character boxes, hidden-text checks
app/retrieval   BM25, RRF, dense leg (LanceDB), conflict partners
app/pipeline    planner, answer, verifier, numbers, injection guard, report, orchestrator
app/llm         Claude client (record/replay), prompts, schemas
app/server.py   FastAPI: SSE chat, report, evidence spotlight, security headers
web/            React 19 + TypeScript + Tailwind + shadcn UI
eval/           gold set, retrieval A/B and end-to-end harnesses, reports
tests/          635 tests (unit + integration)
infra/          label-guarded Google Cloud scripts
docs/           project plan, acceptance tests, architecture decisions, engineering rules
video-kit/      demo script, storyboard, interactive pipeline graph
```

## Limitations

- The knowledge base is the three supplied English PDFs. Arabic-script PDF extraction is untested.
- Answers can vary slightly between runs.
- The support judge is the last check for numbers written in words.
- The service scales to zero to stay free, so the first answer after a quiet period takes about 15 s
  longer.

## Licence

Code: [MIT](LICENSE) © 2026 Rashed Atieh. Almamlaka TV's name, logo, typeface and documents are not covered;
see [NOTICE](NOTICE.md).
