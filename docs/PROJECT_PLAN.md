# PROJECT_PLAN — Almamlaka TV Bilingual PDF Knowledge Assistant

| | |
|---|---|
| Status | **Draft v0.3: planning only. Implementation not yet approved.** |
| Purpose | **MVP submission to Almamlaka TV.** Deliverables: (1) live link, (2) source code (zip + private repo), (3) short README explaining the approach (chunking, embedding model, vector database…), (4) 2–3 sample Q&A screenshots and a short demo video as a fallback if the live link fails during review |
| Owner | Rashed Atieh |
| Implementer | Rashed Atieh, following `docs/ENGINEERING_RULES.md` |
| Companion docs | `docs/ENGINEERING_RULES.md`, `ACCEPTANCE_TESTS.md`, `FIRST_PROMPT.md` |
| Changes since v0.1 | v0.2: hard budget and isolation constraints; hybrid retrieval; Trust and Voice packs; extras M7–M9. **v0.3:** submission deliverables and the **M6b Submission pack** milestone; corpus confirmed final; **no brand permission**, so the name is used as text only, with a prototype disclaimer and no logo; **reviewer invite link** in place of a typed access code; **LanceDB (embedded) as the vector database**; review-period budget settings |
| Prepared | 2026-10-15 (Asia/Amman) |

**Labels:** **[Verified 2026-10-15]** means the fact was checked against the source cited in this document on that date. **[Unverified]** means the implementer must confirm it at M0. **[Estimate]** means a planning number to be replaced by a measured one. Document facts come from direct inspection of the three PDFs (pdfplumber, pypdf and poppler extraction plus a visual render of every page). All 36 document facts quoted below were re-checked programmatically against the PDF text of the stated page.

---

## 0. Objective, scope and constraints

Build and deploy a chat assistant branded for Almamlaka TV whose **only factual sources** are three PDFs. Testers use it live in Arabic and English. Every factual answer is grounded and cited to document, PDF page and section. The assistant abstains when the documents lack the answer and reports disagreements between documents instead of resolving them.

**In scope (v1 core):** ingestion, bilingual chat, cited answers, abstention, conflict reporting, multi-turn, injection resistance, evaluation harness, single-service deployment and smoke tests, the **Trust pack** and the **Voice pack** (§5.3–5.4), and the **submission pack** (§7.7).
**In scope (extras, built only after every P0 test passes):** Knowledge Graph explorer (M7), TV mode + phone remote (M8), "Try to break me" challenge (M9).
**Out of scope:** OCR, user document upload, user accounts, WhatsApp, avatars, voice cloning, "what-if" speculation, any web or live-news data.

### 0.1 Hard constraints (owner-stated)

| Constraint | Consequence for the design |
|---|---|
| **Claude API: about $25 prepaid credit, no further spend** | Dedicated Anthropic workspace with spend limit; auto-reload OFF; LLM record/replay for development; in-app daily cap; reviewer invite link (no open access); Batch API for repeated evaluation runs |
| **GCP: free-trial billing account, >60 days of the 90-day trial remaining, about $300 credit** | Use only free-tier or trial-credit services; plan the post-trial decision before about day 80 (§9) |
| **Two other projects already run on the same GCP billing account; this bot must be fully independent** | New dedicated project, deploy identity limited to that project, pinned gcloud configuration, per-project budget and spend cap (§3.6). The shared credit pool and shared free tier are unavoidable and are monitored. |

---

## 1. Document assessment

### 1.1 Access check

All three files in the connected folder `Almamlaka TV` opened and extracted without errors. None are missing, encrypted or unreadable.

| Doc ID | File | Bytes | Pages | SHA-256 |
|---|---|---|---|---|
| `OVR` | `Almamlaka_Project_Overview.pdf` | 3,511 | 2 | computed at M1 |
| `BUD` | `Almamlaka_Budget_Timeline.pdf` | 3,787 | 2 | computed at M1 |
| `GOV` | `Almamlaka_Team_Governance.pdf` | 3,682 | 2 | computed at M1 |

### 1.2 Per-document profile

| | OVR | BUD | GOV |
|---|---|---|---|
| **Actual title (page 1 heading)** | "Almamlaka TV Digital Expansion Initiative": *Project Overview Document* | "Almamlaka TV Digital Expansion Initiative": *Budget & Timeline Breakdown* | "Almamlaka TV Digital Expansion Initiative": *Team & Governance Document* |
| PDF metadata title | `(anonymous)` | `(anonymous)` | `(anonymous)` |
| Language | English only | English only | English only |
| Pages | 2 | 2 | 2 |
| Sections | 1 Introduction · 2 Project Goals · 3 Key Details (p1); 4 Platform Scope · 5 Stakeholders · 6 Success Metrics (p2) | 1 Quarterly Budget Allocation (table) · 2 Budget Notes (p1); 3 Project Timeline (table) · 4 Risk Notes (p2) | 1 Project Team (table) · 2 Governance Structure · 3 Revised Launch Date (p1); 4 Data Privacy Policy · 5 Content Moderation Policy · 6 Escalation Contacts (p2) |
| Main topics | DEI purpose, goals (+40% digital viewership in year 1), key details (lead, budget, launch date, duration), platforms, 12-language support, stakeholders, success metrics | Quarterly budget by category (Q1–Q4 2027), budget revision note, milestone timeline, risk notes | Team roster (5 people), steering committee, Finance Committee approval rule, revised launch date, privacy, moderation, escalation |
| Tables | none (key-value list in §3) | 5-col × 6-row budget table; 2-col × 7-row timeline table | 3-col × 6-row team table |
| Producer | ReportLab, born-digital | ReportLab, born-digital | ReportLab, born-digital |

### 1.3 Extraction findings

- **Text layer:** clean on every page (standard Helvetica and Helvetica-Bold, WinAnsi). The extracted text matches the rendered pages exactly. **OCR is not needed.**
- **Tables:** `pdfplumber.extract_tables()` recovers all three tables with correct headers and cells. Table header text is white on a navy fill (`#1A3C5E`); this is visible, not hidden.
- **Hidden content:** none. No invisible render mode, annotations, images, JavaScript or embedded files.
- **Structure:** section headings are 18 pt Helvetica-Bold matching `^\d+\. `. Titles are 20 pt bold and subtitles 14 pt bold. **No section spans a page break.** There are 16 sections of 141–535 characters, about 4.5k characters (~1.1k tokens) in total.
- **Page numbers:** there are **no printed page numbers** and **no `/PageLabels`**. The PDF page index is the only page reference. pypdf's default `'1','2'` labels **must not be treated as printed labels**.
- **Arithmetic:** the budget table is internally consistent. Each quarter's total and each column total adds up, and the grand total is $2,400,000 (verified with code).
- **Time context:** the documents describe Dec 2026 and Jan 2027 events in the past tense. They were generated on 2026-08-13 and today is 2026-10-15. The assistant must **never reason from the current date**.
- **Currency:** amounts use `$` with no currency code. Keep `$`; never convert or assert "US dollars".
- **Personal data:** five staff names and roles (GOV p1 §1); one name repeated in OVR p1 §3. The budget figures are commercially sensitive.
- **Suitability for cited retrieval:** high. The main risks are reasoning across disagreeing documents and precise rendering of names, dates and money across the two languages.

### 1.4 Overlaps

| Topic | Where | Consistent? |
|---|---|---|
| Project Lead = Sara Al-Rashid | OVR p1 §3; GOV p1 §1 | Yes |
| Total budget | OVR p1 §3; BUD p1 §1 and §2 | **No** (C1) |
| Public launch date | OVR p1 §3; BUD p2 §3; GOV p1 §3 | **No** (C2) |
| Smart TV integration as a risk | BUD p1 §2, p2 §4; GOV p1 §3 | Consistent; wording differs ("highest-risk item" vs "a high-risk item") |
| Steering committee | OVR p2 §5, §6; GOV p1 §2, p2 §6 | Consistent (different activities: bi-weekly meetings vs quarterly metric review) |
| Finance Committee | BUD p1 §2; GOV p1 §2 | Consistent |

### 1.5 Conflicts and tensions actually found

| ID | Type | Statement A | Statement B | Expected behaviour |
|---|---|---|---|---|
| **C1** | Cross-document conflict | OVR p1 §3: "Total Approved Budget: $2,400,000". BUD p1 §1 table total $2,400,000, which BUD p1 §2 calls "the originally approved budget". | BUD p1 §2: "Following a revision by the Finance Committee in December 2026, the total project budget was adjusted to $2,600,000 to account for additional smart TV integration costs…" | Report both figures with citations. May state that BUD describes $2.4M as the original figure and $2.6M as an adjustment. Must not call OVR outdated or pick one figure. |
| **C2** | Cross-document conflict | OVR p1 §3: "Planned Launch Date: March 15, 2027"; BUD p2 §3: "Public launch: March 15, 2027" | GOV p1 §3: "Following the steering committee meeting on January 20, 2027, the public launch date was moved to April 1, 2027…" | Report both dates and cite all three documents, including GOV's stated reason. |
| **T1** | Internal inconsistency (BUD p2 §3) | QA & testing Mar 1 – Mar 20, 2027 | Public launch March 15, 2027 (inside the QA window) | Only when asked; derived comparison with citations. |
| **T2** | Scope tension (OVR) | p1 §1: "streaming, mobile, and social platforms" | p2 §4: three platforms (mobile app, web portal, smart TV); social not listed | Report both; do not resolve. |
| **T3** | Terminology gap (GOV) | p2 §6: "contact the **Engineering Lead**" | p1 §1: Omar Fayez, "**Lead Engineer**" | Present any link as an inference; the documents never equate the two titles. |
| **T4** | Not a conflict (trap) | OVR p1 §3: "Project Duration: 14 months" | BUD timeline Jan 10 – Jun 15, 2027; budget Q1–Q4 2027 | The documents don't state start or end dates. Do not compute them or claim a contradiction. |

C1 and C2 are confirmed real conflicts, so **no synthetic conflict fixture is needed for the core requirement.** A synthetic *cross-language* conflict fixture (FX-5) is still used because no Arabic source exists.

### 1.6 Gaps that the tests will exploit

- No Arabic source text exists. The English-question → Arabic-source path is tested with fixture FX-2 only.
- Only 4 of the "12 languages" are named.
- The steering committee is described by department only, never by name.
- No CMS vendor, MAU figures, contact details, revised budget breakdown by category or named data-protection law appears anywhere.

---

## 2. Requirements (agreed baseline)

| ID | Requirement |
|---|---|
| R1 | The only factual evidence is retrieved PDF passages. Model memory, web content, user assertions and prior assistant turns are not evidence. |
| R2 | Every factual claim carries ≥1 citation: document, PDF page, section and verbatim quote. Citations are **rendered by the server from chunk metadata, never typed by the model.** |
| R3 | Outcomes: `answered`, `partial` (states what is missing), `not_in_documents`, `clarify`, `out_of_scope`, `error`. Flags: `conflict`, `premise_contradicted`, `derived`. |
| R4 | Conflicts: both positions stated and cited. No source preferred and no "newer wins" assumption. |
| R5 | Reply in the language of the current message unless the user explicitly asks otherwise. Cross-language retrieval works in both directions. |
| R6 | Names, numbers, currencies and dates preserved exactly. Arabic replies keep names in their original Latin spelling; `$` amounts keep the source digits. |
| R7 | History is used only to resolve references. Fresh retrieval runs every turn. Each browser tab, or each paired TV and phone, is isolated. Reset is available. |
| R8 | PDF text, retrieved passages and user input cannot change the rules, reveal secrets or prompts, or widen the scope. |
| R9 | Secrets stay server-side and out of the repo, responses and logs. Message content is not logged by default; the challenge page is the exception, with a visible notice. |
| R10 | Almamlaka TV named as plain text only (no brand permission); prototype disclaimer on every page; no logo or brand styling. |
| R11 | Reproducible setup, documented env vars, deployed URL, smoke tests, honest limitations. |
| R12 | **Budget safety:** the app cannot spend beyond its configured daily cap. The Anthropic workspace cannot exceed its spend limit. Nothing auto-reloads. |
| R13 | **Isolation:** no resource, identity, secret or command of this project can read or change the owner's other GCP projects. |

---

## 3. Recommended architecture

### 3.1 One primary stack

| Layer | Choice | Why |
|---|---|---|
| Runtime | **Python 3.12**, `uv` | Best PDF tooling; one language end to end |
| Ingestion (build time) | **pdfplumber** (text, words with bounding boxes, font sizes, tables, page images via pypdfium2) + **pypdf** (`/PageLabels`); poppler `pdftotext` only as a test oracle | MIT/BSD/Apache licences (no PyMuPDF, which is AGPL); proven on these files |
| Chunking | **One chunk per numbered section**, page-bounded; tables serialized as pipe rows with headers; deterministic IDs `{DOC}-p{page}-s{section}`; **character-level bounding boxes stored per chunk** (for evidence spotlight) | Natural citation units; gold tests written now |
| Normalisation | `arabic_normalize.py` (vendored): `index` profile for BM25 on docs and queries; `embed` profile for embedding inputs; originals for display and LLM context | GET house standard |
| Retrieval | **Hybrid:** in-process BM25 (own ~60 lines) **plus dense vectors from Vertex AI embeddings** (corpus vectors precomputed at build; one query embedding per search at runtime); planner produces bilingual queries; **RRF fusion (k=50)**, top-8 plus per-document diversity | Best cross-language robustness at about $0 cost (§3.4). The dense leg stays only if the M2 A/B on gold-v1 shows it helps or ties (house rule: measure before adopting an embedder). On a Vertex timeout of 1.5 s, the search falls back to BM25-only and logs it. |
| Vector database | **LanceDB, embedded** (in-process; Apache-2.0; data stored as local files under `data/index/lancedb/`, built at `make embed` and baked into the image) [Verified 2026-10-15, lancedb.com: "Runs in-process", "Apache 2.0 license", local path storage]. Exact (brute-force) vector search: at 16 rows no approximate index is needed, so none is built. The keyword leg stays our own Arabic-aware BM25 (LanceDB's full-text tokenizer is not verified for Arabic), and both legs are fused with RRF in our code. | Gives reviewers a real, named vector database with zero servers, zero cost and no ops. It scales to thousands of chunks unchanged. Wrapped behind a small `VectorStore` interface. |
| Embedding model | `gemini-embedding-001` (task types `RETRIEVAL_DOCUMENT`/`RETRIEVAL_QUERY`) vs `gemini-embedding-2` (text prefixes, no `task_type`), chosen by A/B at M2; 768 dimensions [Verified 2026-10-15: both current; `gemini-embedding-2` supports "over 100 languages"; **Arabic not explicitly confirmed**, so it must be measured] | Paid from GCP trial credit (Google first-party model, not an excluded partner model) [Unverified that trial credit applies; confirm at M0] |
| LLM: planner | **`claude-haiku-5-5`** [Verified: $0.10 / $0.50 per MTok for prompts ≤100k] | Cheap, fast classification and rewriting |
| LLM: answer | **`claude-sonnet-5-5`** [Verified: $2 / $10 per MTok; cache read $0.10] | Strong bilingual reasoning at moderate cost; effort/thinking set low for cost and latency (M0 ADR) |
| LLM: verifier | **`claude-haiku-5-5`**, escalated to Sonnet only if judge calibration fails | Per-claim support judging |
| LLM output control | **Structured outputs** via `output_config.format` (`type: "json_schema"`) [Verified: supported on Sonnet 5.5 and Haiku 5.5; incompatible with the API citations feature and prefill; `additionalProperties:false`; no min/max constraints; check `stop_reason` `refusal`/`max_tokens`] | Schema-valid objects; no prose parsing |
| LLM dev mode | **`LLM_MODE=replay|record|live`.** Tests and local development replay recorded responses (cassettes) by default; only `make eval` and explicit runs go live. | Protects the $25 |
| API | **FastAPI** + uvicorn; `POST /api/chat` sends **SSE** events: stage events, then **claim-by-claim delivery as each claim passes verification**, then a final result | Feels fast without ever showing unverified text |
| UI | Static HTML + vanilla JS (ES modules) + CSS logical properties; no build step; self-hosted libraries only | Full RTL and bidi control, small surface |
| Conversation state | **Client-held, server-signed** (HMAC per turn) in per-tab `sessionStorage`; no server session store. Exception: TV pairing registry in memory (M8). | Isolation by construction |
| Hosting | **Google Cloud Run**, `me-central1` (Doha), **min 0 / max 1 instance**, concurrency 40, request-based billing | `max=1` makes in-memory budget guards and TV pairing exact; ample for a test audience |
| Voice | **Server-side speech-to-text with automatic language ID**, chosen by a measured bake-off (§5.4): **Google Speech-to-Text V2 Chirp 3** (`language_codes=["ar-JO","en-US"]`, phrase adaptation from the PDF vocabulary) vs **a current Gemini model on Vertex AI** (audio transcription returning `{language, transcript}`), both paid from GCP credit [Verified 2026-10-15: Chirp 3 language detection GA (`["auto"]` or several locales); **Arabic locales incl. `ar-JO` are Preview**; adaptation GA, up to 1,000 phrases; regions `us`/`eu` multi-region; V2 $0.016/min, no free tier. Gemini audio model and price Unverified]. The Claude API cannot do this: it has **no audio input** (only text, image and document blocks are documented), and Claude app voice mode is not exposed through the API. Plus **Cloud Text-to-Speech Chirp 3 HD** (`ar-XA`, `en-US`) for spoken answers [Verified: Chirp 3 HD supports Arabic (Generic) `ar-XA`; free tier 1M characters per month per billing account, then $30 per 1M] | Auto-detects Arabic vs English and works the same in every browser (Safari included); costs come from GCP credit, never the $25 |
| Access | **Reviewer invite link:** `https://<service>/?invite=<token>` sets an HttpOnly signed cookie and redirects to the clean URL, so reviewers type nothing. A manual code-entry page is the fallback. The token sits in the `app-secrets` bundle and can be rotated. `X-Robots-Tag: noindex` and `robots.txt` disallow all. | Zero friction for reviewers; blocks crawlers and strangers from spending the credit |

**Grounding by construction (R1/R7):** only the *planner* sees history. The *answer model never receives history*, only the standalone question, the original question and the retrieved passages. Earlier answers cannot become evidence.

### 3.2 Alternatives considered

| Option | Verdict |
|---|---|
| Full corpus every turn (~1.1k tokens) | Kept as an **evaluation-only oracle baseline** (M5 A/B) |
| pgvector/Supabase hybrid (GET reference design) | Over-built for 16 chunks; the right step up at 50+ documents |
| LangChain/LlamaIndex | Not used |
| Streamlit/Gradio | Poor RTL and branding control |
| Render / Fly / Railway | No Middle East region; weaker secrets and IAM. Kept as the **post-trial fallback** (§9) |
| Amazon Bedrock UAE | [Verified] Sonnet 5.5 is **global cross-region only** in `me-central-1`; no residency gain |
| Claude via Vertex AI (to use GCP credit) | [Verified] **The trial credit cannot pay for generative AI partner models**, so this isn't possible |
| Gemini API free tier (AI Studio) for embeddings | Rejected: data-use terms differ from Vertex AI, and the trial credit excludes AI Studio [Verified exclusion] |

### 3.3 Hosting implications (Cloud Run, `me-central1`)

- **Cost** [Verified, cloud.google.com/run/pricing and free-tier page]: the free tier per **billing account** per month is 180,000 vCPU-s, 360,000 GiB-s, 2M requests and 1 GB egress from North America. `me-central1` is Tier 2. Expected usage is $0, but **the free tier is shared with your two other projects**.
- **Persistence:** the index, page images, Consistency Radar data and graph data are built into the image (immutable, hashed and reported at `/readyz`). Conversations stay in the browser. Pairing and challenge scoreboards are in memory and reset on redeploy; this is documented. Logs go to Cloud Logging.
- **Access:** public HTTPS URL, but usable only through the reviewer invite link (or the manual code fallback); `noindex`.
- **Maintenance:** redeploy on any PDF change; pin dependencies; check the Anthropic deprecations page quarterly; rotate the invite token after the review window.
- **Trial lifecycle** [Verified]: the trial closes after 90 days or when the credit is spent. Billing is then disabled, **all resources stop**, and there is a 30-day grace period before deletion. Upgrading to a paid account before closure keeps the service running. **Post-trial decision required (§9).**
- **Residency:** Cloud Run region affects only where the app runs. Claude processes the prompts [Verified: `inference_geo` `"global"`/`"us"` (`"us"` = 1.1×); workspace data at rest US only; no Middle East option]. Default `INFERENCE_GEO=us`. Vertex AI embeddings and Text-to-Speech send chunk text, queries and answer text to Google; endpoint regions to be confirmed at M0. Jordan PDPL (Law No. 24 of 2023; in force 17 Mar 2024 per a secondary source [Unverified against the Gazette]) restricts cross-border transfers. **Client and counsel decision; not legal advice.**

### 3.4 Budget plan

**Anthropic ($25 total; workspace spend limit $20/month; auto-reload OFF)**

| Item | Estimate |
|---|---|
| Per turn | Planner ≈ $0.0003 · Answer ≈ $0.006–0.016 (output plus thinking dominates; system prompt cached) · Verifier ≈ $0.0005 → **≈ $0.007–0.017 per turn** [Estimate; replace with M5 measured] |
| Development | **$3**. Replay mode by default; live only for prompt work. |
| Evaluation | **$7**. About 3 full suites ×3 repeats; repeated runs use the **Batch API (50% off)**, stage by stage |
| Build-time derived artifacts | **$1**. Consistency Radar mining, Knowledge Graph extraction, evidence translations cache |
| Reviewer testing during the evaluation window, including the challenge page | **$11**. Roughly 650–1,550 turns. During review, `DAILY_BUDGET_USD=2.00` (≈5 days at full use, longer in practice); the owner lowers it after review. |
| Reserve | **$3** |

**In-app guards:**
- `DAILY_BUDGET_USD` (default 1.00) is computed from `usage` × the price table in config. When reached, the app returns a bilingual "daily limit reached" message.
- `MAX_TURNS_PER_SESSION` (default 30).
- Reviewer invite link (signed cookie).
- Rate limit.
- Challenge page capped at 15 attempts per session.

**GCP (trial credit; expected ≈ $0)**

| Service | Expected usage | Free tier / price |
|---|---|---|
| Cloud Run | Test traffic | Within the shared free tier |
| Cloud Build | A few builds per day | 2,500 build-min/month free (shared) |
| Artifact Registry | ≤2 images kept (cleanup policy) | 0.5 GB free (shared) |
| Secret Manager | **2 secrets** (`anthropic-api-key`, `app-secrets` JSON bundle) | 6 active versions free (shared); **check that the other projects don't already use them** |
| Vertex AI embeddings | 16 chunks once plus ~50 tokens per query | $0.15/1M (gemini-embedding-001) or $0.20/1M (gemini-embedding-2), so pennies in total [Verified prices; units for legacy models unclear] |
| Text-to-Speech Chirp 3 HD | Spoken answers, capped at `TTS_DAILY_CHAR_CAP` = 25,000 | 1M chars/month free (shared) |
| Speech-to-Text (Chirp 3 or Gemini) | Voice questions, ~10 s each; capped at `STT_DAILY_SECONDS_CAP` = 3,600 | Chirp 3: $0.016/min, no free tier → ~$0.003 per question, from GCP credit; 1,000 voice questions ≈ $3 |
| Logging | Metadata only | Free allotment |

### 3.5 Bonus features: cost summary

| Feature | Runtime LLM cost | Other cost |
|---|---|---|
| Trust pack: evidence spotlight, How-I-answered, quality scoreboard | $0 | $0 |
| Trust pack: Consistency Radar | $0 (built once, ~$0.30) | $0 |
| Trust pack: evidence translation (AR gloss of English quote) | ~$0.0005 per click (Haiku), cached | $0 |
| Voice pack | $0 (no Claude cost) | STT ≈ $0.003/question + TTS in free tier, from GCP credit |
| M7 Knowledge Graph | $0 (built once, < $0.50) | $0 |
| M8 TV mode + phone remote | Normal turns | $0 |
| M9 Break-me challenge | Normal turns, capped | $0 |

### 3.6 Isolation plan (R13)

| Layer | Control |
|---|---|
| GCP project | **New project** (suggested ID `getai-almamlaka-assist-<suffix>`), linked to the trial billing account; only the required APIs enabled: run, cloudbuild, artifactregistry, secretmanager, aiplatform, speech, texttospeech, logging |
| Identities | `almamlaka-runtime@…` (runtime: `secretmanager.secretAccessor` on its 2 secrets, `aiplatform.user`, TTS access). `almamlaka-deployer@…` (deploy roles **on this project only**). The owner's own account impersonates the deployer, so no service-account key files exist. |
| CLI | Dedicated `gcloud config configurations create almamlaka`. The Makefile exports `CLOUDSDK_ACTIVE_CONFIG_NAME=almamlaka` and **aborts if `gcloud config get project` ≠ `$GCP_PROJECT`**. Every gcloud command in scripts passes `--project` explicitly. The tooling never lists, reads or changes other projects. |
| ADC (local Vertex calls) | `gcloud auth application-default login` is global, so code always passes `project=GCP_PROJECT` explicitly and sets the quota project. Alternatively, use replay mode locally and live Vertex only on Cloud Run. |
| Naming and labels | All resources are prefixed `almamlaka-` and labelled `app=almamlaka-assistant,owner=rashed-atieh`. Cost reports filter on the label. |
| Billing | Per-project **budget** of $25 with alerts at 50/80/100%. **Spend Caps** on Cloud Run and Agent Platform (Public Preview, per project and service) if available on the trial account [Verified feature; trial eligibility Unverified]. Artifact Registry cleanup keeps 2 images. |
| Anthropic | A **new workspace** `almamlaka-assistant` (limits can't be set on the Default workspace [Verified]); a key scoped to that workspace; monthly spend limit $20; workspace rate limits; **auto-reload OFF**; the other projects never use this key |
| GitHub | A separate private repo; secrets only in GitHub Actions secrets if CI needs live eval (default: CI runs replay only, so no API key in CI) |

**What can't be separated:** the $300 credit pool and the free-tier allowances are shared by all projects on the billing account. The budget, alerts and labels make the shared use visible.

---

## 4. Answering pipeline

```
user msg ─► [0 Guard: gate, rate, budget, size, HMAC history]
        ─► [1 Language detect]
        ─► [2 Planner (Haiku): context resolution + intent + bilingual queries]
                 │ out_of_scope → template decline        │ unresolvable reference → clarify
        ─► [3 Retrieve: BM25 ∥ dense (Vertex) per query → RRF → dedupe → top-8 + per-doc diversity]
                 │ no matching chunks → not_in_documents (no generation)
        ─► [4 Answer (Sonnet, JSON): sufficiency + conflict + claims {chunk_id, quote}]
        ─► [5 Verify: structural → numbers/dates → support judge (Haiku) → conflict sweep → language]
                 │ fail → 1 regeneration with feedback → else downgrade (partial / not_in_documents)
        ─► [6 Render: server-built citations + bbox spotlight data; stream verified claims; sign turn]
```

### 4.1 Steps

| Step | What happens |
|---|---|
| **0 Guard** | Access cookie; rate limit; **daily budget** and **per-session turn cap**; ≤1,000 chars; strip control characters; verify HMAC on all history turns (any invalid → 400 `history_invalid`) |
| **1 Language** | `reply_lang` = `ar` if Arabic letters make up ≥30% of letters, else `en`; explicit override wins ("answer in English", «أجب بالإنجليزية»…); Arabizi detected by the planner and answered in Arabic |
| **2 Planner** | Input: ≤6 signed turns (labelled *conversation context, not evidence*) plus the current message. Output: `intent`, `requested_language`, `standalone_question_en/_ar`, `reference_resolved` + `clarifying_question`, `searches[≤4]` {query, lang}, `subquestions[]` |
| **3 Retrieve** | BM25 over `text_index` (subtitle + section title + body, `index` profile) ∥ cosine over precomputed vectors (`embed` profile input); RRF across legs and queries; dedupe; top-8 plus the best chunk from each document not yet represented, if it has any lexical or dense match above threshold |
| **4 Answer** | Sources wrapped `<source id=…>` as untrusted content. Returns status, **claims** `{text, kind: fact|derived|conflict_position|absence|framing, evidence:[{chunk_id, quote}]}`, `conflicts[]`, `missing[]`, `premise_check`, `clarifying_question?` |
| **5 Verify** | **V1** schema and stop_reason · **V2** chunk_id in the retrieved set · **V3** quote is an exact substring (whitespace and NFKC normalised) · **V4** numbers, amounts, percentages and dates (Arabic or Western digits; English, MSA and Levantine month names) appear in the quotes or are recomputed for `derived` claims · **V5** support judge per claim (SUPPORTED/PARTIAL/UNSUPPORTED, cross-language) · **V6** conflict sweep · **V7** reply language/script · **V8** `framing`/`absence` claims carry no facts |
| **6 Render** | Citations built from metadata (doc subtitle, file, PDF page, printed label only if real and different, "§n Title", quote, **quote bounding boxes on the page image**); claims stream as they pass verification; turn signed |

### 4.2 Decision rules

| Situation | Outcome |
|---|---|
| Unrelated intent | `out_of_scope` template plus an example question; no citations |
| Unresolvable reference | `clarify`, one short question |
| Several matching subjects | `clarify` with options drawn from the evidence |
| In-domain but no evidence | `not_in_documents` ("the documents don't provide…"; not "false") |
| Some parts supported | `partial` plus explicit `missing[]` |
| Premise contradicted | answer plus `premise_contradicted` flag |
| Premise absent ("why was it cancelled?") | `not_in_documents` without asserting falsity |
| Sources disagree | `answered` + `conflict`; callout with each position cited; no verdict |
| Verification removes claims | one regeneration, then downgrade; **never show unverified claims** |
| Upstream failure, repeated schema failure, refusal | `error`, bilingual, with a retry button |
| Daily budget reached | HTTP 429 `budget_exhausted`, bilingual notice; no LLM call |
| Greeting or help | capability description listing the three documents |

### 4.3 Bilingual output conventions

- Clear MSA.
- Western digits as in the source.
- Dates as «15 آذار/مارس 2027».
- `$` amounts unchanged, inside an LTR isolate.
- Names as «سارة الرشيد (Sara Al-Rashid)», with the Latin form mandatory and verified.
- English document titles kept in citations inside `<bdi>`.

### 4.4 Prompt-injection controls

1. Fixed system rules; all sources and user text delimited as untrusted.
2. JSON-only outputs; every claim needs a verbatim quote.
3. A canary token in the system prompt; output filter and tests check for it.
4. Ingestion flags instruction-like or hidden text for human review.
5. `textContent`-only rendering and a strict CSP.
6. No tools, browsing or code execution for any model.
7. TTS only voices server-reconstructed verified answers, never arbitrary client text.

---

## 5. Interface, branding and features

### 5.1 Screens (core)

1. **Invite landing** (`?invite=` → cookie → redirect) and a bilingual manual-code fallback page.
2. **Chat:**
   - **Header:** a **text-only** title, "Almamlaka TV Document Assistant — MVP prototype" / «مساعد وثائق قناة المملكة — نموذج أولي». There is no logo, no Almamlaka colours or fonts, and no imitation of their site. Also: AR/EN toggle (AR default), **New conversation**, and a persistent badge **"Prototype by Rashed Atieh for evaluation — not an official Almamlaka TV product"** / «نموذج أولي من إعداد راشد عطية لأغراض التقييم — ليس منتجاً رسمياً لقناة المملكة».
   - **Welcome panel:** the 3 documents and example questions in both languages.
   - **Messages:** each bubble has its own `dir`; claims stream in as verified; citation chips; status badges (*Partial / Not in documents / Needs clarification / Sources disagree*); conflict callout; clarify options as buttons.
   - **Source cards:** doc subtitle, `PDF p. N` / «ص N (PDF)», section, quote, **View evidence** (spotlight, §5.3).
   - **States:** real SSE stages, error with retry, rate-limit and budget notices, 1,000-character counter.
   - **Footer disclaimer** (AR/EN).
3. **Responsive and accessible:** works at 360 px, keyboard operable, `aria-live`, WCAG AA.

### 5.2 RTL rules

- `<html dir>` follows the UI language; each bubble sets its own `dir`.
- CSS logical properties throughout.
- `<bdi>` around English titles, amounts, dates and IDs.
- Self-hosted Arabic-capable font (for example IBM Plex Sans Arabic; check its licence file at M4); no font CDN.

### 5.3 Trust pack (v1)

| Feature | Behaviour | Build |
|---|---|---|
| **Evidence spotlight** | "View evidence" opens the real PDF page image with the quoted passage highlighted (bounding-box overlay) and the full section text alongside. Links to the gated PDF `#page=N`. | M1 renders page PNGs (~144 dpi) and character bounding boxes; M4 overlay |
| **Evidence translation** | For Arabic users, an on-demand Arabic gloss of the English quote, labelled **"ترجمة آلية — ليست نص المصدر"** (machine translation, not source text). Haiku, cached by hash; V4 checks numbers and dates. | M5 |
| **"How I answered" panel** | Collapsible trace: documents searched, passages retrieved (IDs, rank), claims verified or removed, conflicts found, timings. No prompts are shown. | M4, from the orchestrator trace |
| **Consistency Radar** / تقرير التناقضات (`/radar`) | Side-by-side cards for every cross-document conflict and tension, each with highlighted evidence from both sides. Generated by `make radar` (Sonnet conflict mining over attribute groups → quote verification → **human approval file** `data/derived/radar.approved.json`). Only approved items are shown. Expected content: C1, C2, T1–T4. | M5 |
| **Quality scoreboard** (`/quality`) | Latest committed evaluation report: pass rate per category, gates, model IDs, gold version, date, measured cost and latency. Static, so no runtime cost. | M5 |

### 5.4 Voice pack (v1)

| Part | Behaviour |
|---|---|
| **Speak a question** | **Hold-to-talk or tap-to-talk** mic (≤30 s). The browser records with `MediaRecorder` (Opus/WebM, or MP4 on Safari; the formats the STT engine accepts are confirmed at M0) → `POST /api/stt` → the server STT engine returns `{language, transcript, word confidences if available}`. **No language needs to be selected: the detected language decides the reply language**, shown as a chip («عربي» / "English") the user can flip. **The transcript goes into the input box with low-confidence words underlined, for the user to confirm or edit before sending.** It is never auto-sent. |
| **Accuracy measures** | (1) **Constrain language ID to Arabic + English** rather than open auto-detect. (2) **Domain phrase list** auto-built from the PDFs (all names, roles, committees, platform terms, amounts, dates, "DEI", "smart TV"…) for Chirp adaptation, or as a glossary in the Gemini prompt. (3) **Glossary snapping:** near-miss names and terms (e.g. "Sara Al Rasheed") are *suggested* as the PDF spelling (shown, never silently replaced). (4) Spoken numbers are normalised to digits («مليونين وستمية ألف» → 2,600,000) as a suggestion. (5) A noise and level meter, plus a "speak closer" hint. (6) Mixed Arabic–English speech («إيمتى الـ public launch؟») is part of the bake-off. |
| **Engine selection (bake-off, M4)** | `eval/voice/`: **≥40 recorded clips** (≥10 MSA, ≥10 Jordanian/Levantine, ≥15 English, ≥5 code-switched; ≥3 speakers; quiet and noisy) whose scripts are questions from ACCEPTANCE_TESTS, covering every name, amount and date. Metrics: language-ID accuracy, WER (EN), CER (AR, GET normalisation), **entity and number exact-match**, latency. Run Chirp 3 (with and without adaptation) vs Gemini; the winner goes in the ADR. Cost ≈ 40 clips × 3 configs × ~10 s ≈ 20 min ≈ $0.35 of GCP credit. |
| **Hear the answer** | 🔊 on each answer → `GET /api/tts/{turn_id}`. The server rebuilds the verified answer text from the signed turn (citation markers removed), calls Cloud TTS Chirp 3 HD (`ar-XA`/`en-US` voice, name confirmed at M0), caches the audio (LRU) and streams MP3. The voice is labelled synthetic. |
| **Limits** | STT: ≤30 s per clip, `STT_DAILY_SECONDS_CAP`=3,600 (≈ $1/day max). TTS: ≤1,500 characters per answer, `TTS_DAILY_CHAR_CAP`=25,000; no arbitrary text-to-speech endpoint. Audio is processed in memory and never stored or logged. |
| **Limitations (stated honestly in README)** | **No speech engine guarantees zero errors**, and neither does Claude's own app voice mode, which Anthropic labels beta for non-English. The design makes errors **visible and correctable before anything is asked** (editable transcript, underlined low-confidence words, glossary suggestions). Audio goes to Google (US/EU multi-region). Chirp's Arabic locales are Preview. |

### 5.5 Extras (built only after every P0 test passes; each redeployed and smoke-tested)

**M7: Knowledge Graph explorer (`/graph`)**
- `make graph`: Sonnet extracts entities (person, role, department, committee, platform, milestone, date, amount, policy, metric) and relations (leads, member_of, approves, budget_of, scheduled_for, revised_to, covers, measured_by…). **Every edge carries `chunk_id` + verbatim quote.** Quotes are verified; conflicting values on the same attribute become **red conflict edges** linking both sources; inferred links (T3) are **not** drawn as facts. A human approves `graph.approved.json`.
- UI: a self-hosted graph library (Cytoscape.js expected; confirm the MIT licence at M7) with bilingual labels (Latin names kept). Clicking a node or edge shows the quotes and spotlight; "Ask about this" pre-fills the chat.
- Cost: build-time only, < $0.50.

**M8: TV mode + phone remote (`/tv`, `/remote`)**
- `/tv`: 10-foot UI (1080p, large Arabic type, D-pad and arrow-key focus navigation, no keyboard needed). Shows a **QR code and a 6-character pairing code**: single use, expires in 10 minutes, HMAC-bound, one phone per TV.
- `/remote` (behind the invite gate): mic, text box and suggested questions. Questions run through the normal pipeline under the TV's session. Verified claims and evidence spotlight stream to the TV over SSE; the phone gets a compact copy. Optional TTS on the TV.
- The pairing registry is in memory (valid because max-instances=1). On restart, devices re-pair (documented). Each pair is fully isolated from other pairs and from normal chat sessions.
- Demo hardware: Chrome on a laptop over HDMI, or an Android TV browser; tested at 1920×1080.

**M9: "Try to break me" challenge (`/challenge`)**
- Bilingual scenario cards: reveal instructions; assert a fake budget; go off-topic; cite a non-existent page; make your claim count as fact; inject through Arabizi.
- Each attempt runs the normal pipeline. A **deterministic scorer** labels it *Blocked ✓* or *Possible bypass ⚠ (queued for review)*:
  - canary present
  - claim numbers not in quotes
  - status vs expected
  - citation validity
  - off-topic content without `out_of_scope`
- The scoreboard (in memory, "since last deploy") shows attempts and blocked percentage. Content logging is **on for this page only**, with a visible notice; bypass candidates are written to a review log. Capped at 15 attempts per session, and the daily budget applies.

### 5.6 Brand assets: missing

| Asset | Status | Temporary handling |
|---|---|---|
| Logo (SVG, AR/EN) | **Not used** (no permission) | Plain-text title only; nothing recreated or scraped |
| Colour palette | **Missing** | Neutral palette; accent `#1A3C5E` comes from the PDFs' table headers, **not** a verified brand colour |
| Typography | **Missing** | IBM Plex Sans Arabic / IBM Plex Sans (temporary) |
| Assistant name | **Missing** | "Document Assistant / مساعد الوثائق" |
| Permission to use the brand | **Not granted (owner, 2026-10-15)** | The name appears only as plain text, describing what the prototype is for (the assignment asks for an assistant for Almamlaka TV). No logo, brand colours, typography or look-alike styling; a prototype disclaimer on every page and in the README; `noindex`. Official branding is applied only if Almamlaka later supplies assets and consent. |

---

## 6. Evaluation

See `ACCEPTANCE_TESTS.md`: 100+ cases (document-derived D and synthetic S), machine assertions, an LLM judge and human Arabic review. Gates cover citation validity (100%), claim support (≥95%), abstention, conflicts (100% on C1/C2), injection (100%), retrieval recall, budget guards, isolation and each feature. P0 cases run 3 times and must pass 3/3. Repeated runs use the Batch API.

---

## 7. Implementation

### 7.1 Repository (private: `almamlaka-pdf-assistant`)

```
almamlaka-pdf-assistant/
├─ docs/ENGINEERING_RULES.md  README.md
├─ docs/  PROJECT_PLAN.md  ACCEPTANCE_TESTS.md  SETUP_ACCOUNTS.md  ENV.md  RUNBOOK.md  LIMITATIONS.md  DEMO_SCRIPT.md
├─ submission/    screenshots/*.png  demo/  SUBMISSION_CHECKLIST.md   # generated in M6b; large video files git-ignored
│        adr/0001-stack-and-models.md
├─ corpus/        3 PDFs (read-only) + corpus_manifest.json
├─ app/
│  ├─ main.py config.py security.py budget.py lang.py logging.py prices.py
│  ├─ ingest/     extract.py chunk.py bboxes.py render_pages.py flags.py build_index.py
│  ├─ retrieval/  normalize.py bm25.py dense.py fuse.py retriever.py
│  ├─ llm/        client.py replay.py schemas.py prompts/{planner,answer,verifier,radar,graph,translate}.md
│  ├─ pipeline/   planner.py answer.py verify.py numbers.py render.py orchestrator.py
│  ├─ features/   spotlight.py translate.py radar.py quality.py tts.py graph.py pairing.py challenge.py
│  └─ i18n/       en.json ar.json
├─ static/        index.html app.js styles.css radar/ quality/ graph/ tv/ remote/ challenge/ fonts/ vendor/ brand/README.md
├─ data/
│  ├─ index/      chunks.jsonl manifest.json lancedb/              # make index / make embed
│  └─ derived/    pages/*.png  radar.approved.json  graph.approved.json  quality.json
├─ vendor/arabic_rag/  arabic_normalize.py chunk_text.py retrieval_metrics.py PROVENANCE.md
├─ fixtures/      make_fixtures.py pdf/ expected/
├─ eval/          cases/*.yaml gold/gold-v1.jsonl run_eval.py batch_runner.py judge.py cassettes/ reports/
├─ tests/         unit/ integration/ e2e/ smoke/
├─ infra/         setup_project.sh budget.sh cleanup_policy.json   # printed for the owner to run; never auto-run
├─ Dockerfile .dockerignore .gcloudignore pyproject.toml uv.lock Makefile .env.example .gitignore
└─ .github/workflows/ci.yml   # ruff, unit, integration (replay), index check, gitleaks
```

### 7.2 Dependencies (exact versions pinned from PyPI at M0; never guessed)

- **Runtime:** `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `anthropic` (supporting `output_config` and `inference_geo`), `pdfplumber` (with `pypdfium2`), `pypdf`, `httpx`, `numpy`, `lancedb` (embedded vector database), the Google client for Vertex embeddings (`google-genai` or `google-cloud-aiplatform`, whichever current docs recommend for the chosen model, decided in the ADR), `google-cloud-texttospeech`, `segno` or `qrcode` (QR code; licence checked).
- **Dev/test:** `pytest`, `pytest-asyncio`, `ruff`, `playwright`, `reportlab`, `pyyaml`; `gitleaks` binary in CI.
- **Front-end (self-hosted, licences checked):** Cytoscape.js (M7).
- **Not used:** LangChain, LlamaIndex, vector DBs, PyMuPDF, any CDN.

### 7.3 Configuration

| Variable | Secret | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✔ | none | Secret `anthropic-api-key` |
| `APP_SECRETS` | ✔ | none | JSON bundle in one secret: `invite_token`, `session_secret`, `canary_token` |
| `ANSWER_MODEL` / `PLANNER_MODEL` / `VERIFIER_MODEL` | | `claude-sonnet-5-5` / `claude-haiku-5-5` / `claude-haiku-5-5` | |
| `INFERENCE_GEO` | | `us` | `us` or `global` |
| `LLM_MODE` | | `replay` (dev/test), `live` (staging/prod) | `replay`, `record` or `live`; prod refuses `replay` |
| `GCP_PROJECT` / `GCP_REGION` / `VERTEX_LOCATION` | | `<new project id>` / `me-central1` / set in ADR | Explicit project on every Google client |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` / `DENSE_ENABLED` | | ADR result / `768` / `true` | `false` = BM25-only |
| `TTS_VOICE_AR` / `TTS_VOICE_EN` / `TTS_DAILY_CHAR_CAP` | | ADR result / ADR result / `25000` | |
| `STT_ENGINE` / `STT_MODEL` / `STT_LANGS` / `STT_LOCATION` | | bake-off winner (`chirp3` or `gemini`) / ADR / `ar-JO,en-US` / ADR | Speech-to-text |
| `STT_MAX_SECONDS` / `STT_DAILY_SECONDS_CAP` | | `30` / `3600` | |
| `DAILY_BUDGET_USD` / `MAX_TURNS_PER_SESSION` | | `1.00` / `30` | In-app spend guard |
| `FEATURE_VOICE` / `FEATURE_RADAR` / `FEATURE_GRAPH` / `FEATURE_TV` / `FEATURE_CHALLENGE` | | `true` / `true` / `false` until M7 / `false` until M8 / `false` until M9 | |
| `CHALLENGE_MAX_ATTEMPTS` / `CHALLENGE_LOG_CONTENT` | | `15` / `true` | Challenge page only |
| `APP_ENV` | | `dev` | `dev`, `staging` or `prod` |
| `RETRIEVAL_TOP_K` / `MAX_HISTORY_TURNS` / `MAX_INPUT_CHARS` | | `8` / `6` / `1000` | |
| `LLM_TIMEOUT_S` / `LLM_MAX_RETRIES` / `DENSE_TIMEOUT_S` | | `45` / `2` / `1.5` | |
| `RATE_LIMIT_PER_MIN` | | `10` | Per IP |
| `LOG_LEVEL` / `LOG_CONTENT` | | `INFO` / `false` | Content logging forbidden in prod except the challenge page |
| `UI_DEFAULT_LANG` | | `ar` | |
| `CORPUS_SET` | | `prod` | `fixtures` refused in prod |

### 7.4 Milestones (stop for owner review at the end of each)

| # | Milestone | Exit criteria |
|---|---|---|
| **M0** | Bootstrap, verification and account setup | Local repo, `uv`, CI skeleton, `.env.example`. **ADR-0001** (with URL and date) records: model IDs and prices; `output_config`; `inference_geo`; effort/thinking settings; caching minimums; Vertex embedding models, their location, and whether trial credit covers them; Chirp 3 HD voice names and region; Cloud Run `me-central1`; Spend Caps eligibility on trial. **`docs/SETUP_ACCOUNTS.md`** lists exact commands for the owner to run (new project, APIs, service accounts, budget, spend cap, Artifact Registry cleanup, 2 secrets, Anthropic workspace, spend limit, auto-reload off). `make check` passes. |
| **M1** | Ingestion | `make index` produces exactly the **16 chunks** in ACCEPTANCE_TESTS §0, plus page PNGs and character bounding boxes; ingest report clean; FX-3/FX-4 tested |
| **M2** | Retrieval | BM25 + Vertex dense + RRF + diversity; planner prompt; **A/B BM25-only vs hybrid × 2 embedding models on gold-v1 (Arabic slice reported separately)**; decision in the ADR; recall gates pass |
| **M3** | Answer + verify | Full pipeline with claim streaming, budget guard and replay mode; mocked-LLM integration tests for every status and flag; verifier unit tests green; first live run of A–E |
| **M4** | API + UI + Trust pack (part 1) + Voice pack | SSE endpoint, gate, HMAC, rate and budget guards, security headers; UI with RTL, citations, **evidence spotlight**, **How I answered**, reset, states; **voice in/out** with the **STT bake-off** (≥40 recorded clips; winner and measured WER/CER/language-ID recorded in the ADR; owner records or sources the clips); Playwright e2e green |
| **M5** | Hardening + Trust pack (part 2) | Fixtures FX-1…FX-5; **evidence translation**, **Consistency Radar** (human-approved), **quality scoreboard**; full suite ×3 (Batch API); oracle A/B; judge calibration; Arabic human review; measured cost and latency; `LIMITATIONS.md` |
| **M6** | Deploy core | Staging → smoke green → **prod with approval** → smoke green → `RUNBOOK.md` |
| **M6b** | **Submission pack (submittable checkpoint)** | README to the §7.7 spec with measured evaluation numbers; 3 screenshots from the live URL; silent Playwright demo recording plus `DEMO_SCRIPT.md` for the owner's narrated video; source zip (secret-scanned) + private repo; reviewer invite link tested in a clean browser; `SUBMISSION_CHECKLIST.md` all ticked. **The owner can submit here; M7–M9 are optional upgrades.** |
| **M7** | Knowledge Graph | `make graph` + human approval; `/graph`; ACCEPTANCE_TESTS section KG green; P0 regression green; redeploy + smoke |
| **M8** | TV mode + phone remote | `/tv`, `/remote`, pairing; section TV green on 1080p and phone; P0 regression green; redeploy + smoke |
| **M9** | Break-me challenge | `/challenge`, scorer, scoreboard, review log; section CH green; P0 regression green; redeploy + smoke; final handover |

Rough effort: **about 11–13 working days to M6b (submittable)**, plus about 4–5 days for M7–M9. [Estimate] If the deadline is tight, extras are dropped before any core quality gate is relaxed. After each extra ships, the screenshots and video are refreshed only if time allows.

### 7.5 Deployment steps (Cloud Run; commands live in `docs/SETUP_ACCOUNTS.md` and `RUNBOOK.md`)

1. **The owner runs** project creation, links the trial billing account, enables only the listed APIs, and creates the runtime and deployer service accounts with project-scoped roles.
2. Create the 2 secrets; grant the runtime SA accessor on those secrets only.
3. Create a per-project budget ($25, alerts at 50/80/100%) and Spend Caps on Cloud Run and Agent Platform if eligible.
4. Create the Artifact Registry repo `almamlaka` in the project with a cleanup policy (keep the last 2 images).
5. Create the Anthropic workspace, scoped key, $20 spend limit and rate limits; confirm auto-reload is OFF.
6. Dockerfile: install deps → copy `data/` (index, embeddings, page images, approved radar/graph) → verify the manifest hash → run as non-root.
7. `gcloud run deploy almamlaka-assistant-staging --project $GCP_PROJECT --source . --region me-central1 --service-account almamlaka-runtime@… --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest,APP_SECRETS=app-secrets:latest --set-env-vars APP_ENV=staging,LLM_MODE=live,… --min-instances 0 --max-instances 1 --concurrency 40 --cpu 1 --memory 512Mi --timeout 300 --labels app=almamlaka-assistant --allow-unauthenticated` (flags checked against current docs at M6; the timeout covers TV SSE streams).
8. `make smoke URL=<staging>` → fix → **approval** → the same for the prod service `almamlaka-assistant` → `make smoke URL=<prod>`.
9. Record the URL, revision, image digest, manifest hash, smoke report and current shared free-tier usage in `RUNBOOK.md`.

### 7.6 Live verification

The smoke suite is in ACCEPTANCE_TESTS §N. It covers health, index hash, gate, EN, AR, abstention, conflict, injection/canary, secrets, headers, budget guard, TTS, latency, and from M7–M9 `/graph`, `/tv` pairing and `/challenge`.

### 7.7 Submission pack (M6b)

| Deliverable | Spec |
|---|---|
| **1. Live link** | The prod Cloud Run URL plus the **reviewer invite link** (`?invite=<token>`). Test it in a fresh incognito window on desktop and phone. Smoke suite green on the day of submission. When the daily budget is reached or the service errors, the UI shows a bilingual notice: "The live demo is temporarily unavailable — please see the demo video and screenshots included in the submission." |
| **2. Source code** | `make release-zip` runs `git archive` of the tagged commit, then **gitleaks + a grep for key patterns** fail the build on any hit. Contents: code, PDFs (corpus), derived data, docs; no `.env`, cassettes containing keys, or video files. Also a **private** GitHub repo (`almamlaka-pdf-assistant`); reviewers are added on request. Tag `v1.0.0-mvp`. |
| **3. README** (short; the main body readable in about 5 minutes; detail goes in `docs/`) | 1. What it does (3 lines + live link + screenshot). 2. **Approach at a glance:** Mermaid architecture diagram. 3. **Document analysis:** 3 born-digital English PDFs, 6 pages, no OCR needed, tables, no printed page labels, conflicts found (C1, C2). 4. **Chunking strategy:** one chunk per numbered section, page-bounded, tables serialized with headers, deterministic IDs, 16 chunks, and why. 5. **Embedding model:** the ADR winner, with the measured A/B table (BM25-only vs hybrid; Arabic slice). 6. **Vector database:** LanceDB embedded, exact search, and why no server-based database is needed at this scale. 7. **Retrieval:** bilingual query planning + hybrid BM25/dense + RRF + per-document diversity. 8. **Generation and grounding controls:** claim-level citations, quote verification, numeric checks, support judge, conflict sweep, abstention rules. 9. **Arabic/English:** cross-lingual retrieval, RTL, name/number/date preservation. 10. **Security:** injection defences, secrets, session isolation. 11. **Evaluation results:** a table from the latest report (gold version, pass rates, gates, cost per turn, latency). 12. **Data handling:** what goes to Anthropic/Google; no content logging. 13. **Limitations** (honest list). 14. **Run locally / deploy** (env vars table link). 15. Prototype disclaimer. Optional Arabic summary paragraph at the top. |
| **4a. Screenshots (3)** | Captured by `make screenshots URL=…` (Playwright, 1440×900, light theme): **S1** an English question (A-03, Q2 marketing) with a citation card and the **evidence spotlight** open. **S2** an Arabic question in RTL (C-02, launch date) showing the **"Sources disagree"** callout with both citations. **S3** abstention plus a follow-up: E-03 "not in documents" and a G-01 follow-up in the same transcript. PNGs go to `submission/screenshots/`, reviewed by the owner. |
| **4b. Demo video (2–3 min)** | (i) `make demo-video URL=…` records a **silent** scripted Playwright run (video is saved when the browser context closes) as a fallback. (ii) **Main video:** the owner records a narrated screen capture (e.g., Windows Clipchamp or Xbox Game Bar) following `docs/DEMO_SCRIPT.md`. Bilingual script, timed shots: 0:00 intro and disclaimer → 0:15 Arabic question with citation and spotlight → 0:45 conflict (budget) → 1:05 out-of-documents answer → 1:20 follow-up + reset → 1:40 injection attempt blocked → 2:00 voice question in Arabic + spoken answer → 2:20 Consistency Radar + quality scoreboard → 2:45 close. MP4, ≤ 100 MB, attached to the form (or an unlisted link if the form limits size). |
| **Checklist** | `submission/SUBMISSION_CHECKLIST.md`: live link opened in incognito today ✓; invite link works ✓; smoke green ✓; zip scanned ✓; README numbers match the latest report ✓; screenshots current ✓; video plays ✓; daily budget set for the review window ✓; Anthropic balance noted ✓; GCP trial end date noted ✓ |

---

## 8. Known limitations

- RAG with verification **reduces but does not eliminate** unsupported statements; the judge has a measured, non-zero error rate.
- There is no Arabic source text, so Arabic-source behaviour is tested only on fixtures.
- Dialect and Arabizi handling depend on the planner. Speech recognition is measured, not perfect; transcripts are always user-confirmed, and audio is processed by Google.
- Prompts and passages are processed by Anthropic (US) and Google (embeddings, TTS) outside Jordan.
- No server history; the pairing registry and challenge scoreboard reset on redeploy.
- **The demo stops when the GCP trial closes** unless billing is upgraded or the container is moved (§9).
- The budget allows roughly 650–1,550 live test turns [Estimate].
- Temporary branding.

---

## 9. Decisions needed before implementation can finish

| # | Decision | Blocks | Default if you agree |
|---|---|---|---|
| 1 | **Data-handling OK (pending owner confirmation):** the PDFs were supplied by Almamlaka specifically to build this chatbot, so sending their text to Anthropic (Claude) and Google (embeddings, voice) during processing is treated as within the assignment. This is disclosed in the README "Data handling" section. | M2 live, M3 live | Proceed on confirmation |
| 2 | ~~Brand permission~~ **Closed: not granted.** Text-only name, prototype disclaimer, no logo or brand styling (§5.6); reviewer invite link (§3.1) | — | — |
| 3 | ~~Corpus finality~~ **Closed: these 3 PDFs are the final MVP corpus.** | — | — |
| 6 | **Submission deadline:** decides whether M7–M9 fit before submitting | Milestone plan | Submit at M6b; add extras only if time remains |
| 7 | **Source code delivery:** zip (default) and/or GitHub. The repo stays **private** (it contains their documents and staff names); add reviewers' GitHub handles if they want repo access | M6b | Zip + private repo |
| 4 | **Post-trial hosting:** at about day 80, either upgrade the billing account to paid (Cloud Run likely stays in the free tier, but a card is on file and overages are possible), or move the container to a free host (to be evaluated then), or let the demo end | Before about day 80 | Decide at the M6 review with measured usage |
| 5 | **Trial end date:** the exact date from GCP Billing → Overview | M6 scheduling | — |

---

## Sources (verified 2026-10-15)

- Claude models: https://platform.claude.com/docs/en/models/overview
- Claude pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Data residency: https://platform.claude.com/docs/en/manage-claude/data-residency
- Workspaces (spend and rate limits): https://platform.claude.com/docs/en/manage-claude/workspaces
- Rate limits and tiers: https://platform.claude.com/docs/en/api/rate-limits
- Credit expiry and auto-reload: https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage
- GCP free trial and free tier: https://docs.cloud.google.com/free/docs/free-cloud-features
- Cloud Run pricing: https://cloud.google.com/run/pricing
- GCP Spend Caps (Public Preview, 2026-07-28): https://cloud.google.com/blog/topics/cost-management/new-early-anomalies-and-spend-caps-on-google-cloud-budgets
- Vertex AI pricing (embeddings): https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing
- Gemini embeddings: https://ai.google.dev/gemini-api/docs/embeddings
- Text-to-Speech pricing: https://cloud.google.com/text-to-speech/pricing
- Chirp 3 HD voices: https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd
- Speech-to-Text Chirp 3 (language detection, adaptation, regions): https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3
- Speech-to-Text pricing: https://cloud.google.com/speech-to-text/pricing
- Claude Messages API content types (no audio input): https://platform.claude.com/docs/en/api/messages
- Claude voice mode (apps only; non-English beta): https://support.claude.com/en/articles/11101966-use-voice-mode
- GitHub Actions billing: https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions
- Bedrock Sonnet 5.5 regions: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html
- Bedrock Middle East global CRIS: https://aws.amazon.com/blogs/machine-learning/introducing-amazon-bedrock-global-cross-region-inference-for-anthropics-claude-models-in-the-middle-east-regions
- Almamlaka TV public-service page: https://www.almamlakatv.com/pages/3
- Jordan PDPL summary (secondary): https://www.clym.io/regulations/law-no-24-of-2023-jordan
