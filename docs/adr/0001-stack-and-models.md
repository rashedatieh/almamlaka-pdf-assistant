# ADR-0001: Stack, models and platform facts (verified at M0)

| | |
|---|---|
| Status | **Accepted.** The owner decided every open deviation on 2026-10-15 (§7, "Owner answers"). |
| Date | 2026-10-15 |
| Deciders | Rashed Atieh |
| Context | docs/ENGINEERING_RULES.md "Verify before you rely on it" and PROJECT_PLAN §7.4 M0 require each planning fact to be re-checked against official pages, with URL and access date. |
| Method | Official pages fetched on **2026-10-15**: Anthropic docs (raw `.md`), Google Cloud docs and pricing pages, gcloud reference, PyPI JSON API, official GitHub repositories and tags. Every source URL listed in §8 returned HTTP 200 that day. SDK parameter names were also checked in the installed package source. **No paid API call was made (spend $0).** |

**Status legend:**
- ✅ matches PROJECT_PLAN
- ➕ new information
- ⚠ differs from the plan (see §5)
- ◐ partially verified
- ❓ not stated in the official docs

Source keys such as `[ANT-PRC]` resolve in §8. Every source was accessed on 2026-10-15.

---

## 1. Decisions (values this repository uses)

| Setting | Value | Basis |
|---|---|---|
| Answer model | `claude-sonnet-5-5`: `output_config.effort="low"`, adaptive thinking (default, `display` omitted), structured output. **Pending D19** (Opus 5.5 is the owner's alternative) | §3.1 rows 1, 5. Thinking cannot be disabled on Sonnet 5.5 (D2) |
| Planner model | `claude-haiku-5-5`: `effort="low"`, `thinking: {type: "disabled"}` (the planner has no tools). **Pending D19**: the owner asked not to use Haiku for now | §3.1 row 5 |
| Verifier model | `claude-haiku-5-5`: `effort="medium"` (its default), adaptive thinking. Escalate to Sonnet if judge calibration fails (ACCEPTANCE §M). **Pending D19** | §3.1 row 5. Latency and accuracy are re-measured at M3 and M5 |
| Sampling parameters | **None sent.** A non-default `temperature`, `top_p` or `top_k` returns a 400 on both models | §3.1 row 5f (D2) |
| Structured outputs | `output_config.format = {type: "json_schema", schema}`, GA, no beta header. `additionalProperties: false` on every object. No `minimum`/`maximum`/`minLength`/`maxLength`/`maxItems`. `minItems` only 0 or 1. At most 24 optional parameters and 16 union-typed parameters per request | §3.1 row 3 |
| Inference geo | `INFERENCE_GEO=us` (1.1× price), as in the plan. **Owner decision (D1)** | §3.1 row 4 |
| Prompt caching | `cache_control` on static system prompts of at least 512 tokens; 5-minute TTL; 1-hour TTL for batch eval | §3.1 row 6 |
| Repeated eval | Message Batches API (50% off; structured outputs and caching supported) | §3.1 row 10 |
| Vector database | **LanceDB 0.40.0, embedded**: `lancedb.connect("data/index/lancedb")`, `tbl.search(v).distance_type("cosine").bypass_vector_index().limit(k)` (exact kNN) | §3.6 |
| Google GenAI SDK | `google-genai==2.31.0`, `genai.Client(enterprise=True, project=GCP_PROJECT, location=VERTEX_LOCATION)` | §3.2 row 3 (D6) |
| `VERTEX_LOCATION` | `global` (the only location offering every candidate model at base price). `eu` is the residency alternative. **Owner decision (D3)** | §3.2 rows 1d, 2e, 4e |
| Embedding candidates (M2 A/B) | `gemini-embedding-001` (`task_type` RETRIEVAL_DOCUMENT/QUERY; 768 dims via `output_dimensionality`; **re-normalise**) vs `gemini-embedding-2` (text prefixes; 768 dims; already normalised) | §3.2 (D4) |
| Voice (speech-to-text, text-to-speech) | **Removed by the owner (D20).** No STT or TTS API, role, dependency or setting is used. §3.3, §3.4 and the transcription rows of §3.2 are kept only as a record of what was checked | D20 |
| Cloud Run | `me-central1` (Doha, Tier 2 pricing) | §3.5 |
| QR library (M8) | `segno==1.6.6` (BSD-3-Clause) | §3.7 |
| Fonts (M4) | IBM Plex Sans / IBM Plex Sans Arabic 1.1.0, SIL OFL 1.1. Serve IBM's own `.woff2` files **unmodified** (renaming rule) | §3.7 |
| Graph library (M7) | Cytoscape.js 3.34.3 (MIT) | §3.7 |
| CI | `actions/checkout` v7.0.1 `3d3c42e5aac5ba805825da76410c181273ba90b1`; `astral-sh/setup-uv` v10.3.0 `1c37ad07a6a961277cf70c0d37d6f313000f5884`; gitleaks **binary** 8.30.1 (sha256 `551f6fc8…70eb`) instead of the action | §3.8 (D16) |

---

## 2. Dependencies pinned from PyPI (2026-10-15, `https://pypi.org/pypi/<name>/json`)

| Package | Version | Upload date | Licence |
|---|---|---|---|
| anthropic | 1.14.0 | 2026-10-14 | MIT |
| fastapi | 0.143.2 | 2026-10-15 | MIT |
| google-genai | 2.31.0 | 2026-10-14 | Apache-2.0 |
| httpx | 0.28.1 | 2024-12-06 | BSD-3-Clause |
| lancedb | 0.40.0 | 2026-10-07 | Apache-2.0 |
| numpy | 2.5.4 | 2026-10-10 | BSD-3-Clause (+ bundled) |
| pdfplumber | 0.11.10 | 2026-06-15 | MIT |
| pydantic | 2.14.1 | 2026-10-11 | MIT |
| pydantic-settings | 2.16.0 | 2026-10-14 | MIT |
| pypdf | 6.20.1 | 2026-10-12 | BSD-3-Clause |
| pypdfium2 | 5.14.0 | 2026-10-04 | Apache-2.0 / BSD-3-Clause (+ PDFium) |
| segno | 1.6.6 | 2025-03-12 | BSD-3-Clause |
| uvicorn[standard] | 0.54.0 | 2026-09-25 | BSD-3-Clause |
| *dev:* playwright | 1.64.0 | 2026-10-13 | Apache-2.0 |
| *dev:* pytest | 9.1.1 | 2026-06-19 | MIT |
| *dev:* pytest-asyncio | 1.4.0 | 2026-05-26 | Apache-2.0 |
| *dev:* pyyaml | 6.0.3 | 2025-09-25 | MIT |
| *dev:* reportlab | 5.0.1 | 2026-08-20 | BSD |
| *dev:* ruff | 0.17.1 | 2026-10-15 | MIT |

Transitive versions are locked in `uv.lock` (71 packages plus the project itself; `uv lock` reports 72). `google-cloud-speech` and `google-cloud-texttospeech` were removed with the Voice pack (D20), taking 6 transitive packages with them (grpc, protobuf and others). `google-genai` caps `websockets` at 16.1.1.
Tooling: uv 0.13.1 (`winget astral-sh.uv`), GNU make 4.4.1 (`winget ezwinports.make`), Python 3.12.10.

---

## 3. Verification results

### 3.1 Claude API (Anthropic)

| # | Fact | Verified value | Status | Source |
|---|---|---|---|---|
| 1a | Model IDs | `claude-sonnet-5-5` and `claude-haiku-5-5` are both **Active**. Retirement not sooner than 2027-09-28 (Sonnet) and 2027-10-07 (Haiku) | ✅ | [ANT-DEP] |
| 1b | Alias or snapshot | Every model ID, including dateless IDs, is a pinned snapshot | ➕ | [ANT-MOD] |
| 1c | Context / output | 1M-token context, 128K max output (300K for batches, with a beta header) | ➕ | [ANT-MOD] |
| 2a | Haiku 5.5 price | $0.10 input / $0.50 output per MTok for prompts **≤100k tokens**. **Over 100k: $0.50 / $2.50** (cache reads and writes count toward the 100k) | ✅ ➕ | [ANT-PRC] |
| 2b | Sonnet 5.5 price | $2 / $10 per MTok; cache read $0.10 (0.05× input) | ✅ | [ANT-PRC] |
| 2c | Cache writes | Sonnet: $2.50 (5-min), $4 (1-hour). Haiku ≤100k: $0.125 / $0.20, read $0.01 | ➕ | [ANT-PRC] |
| 2d | Batch | 50% off input and output | ➕ | [ANT-PRC], [ANT-BAT] |
| 3a | Structured outputs shape | `output_config: {format: {type: "json_schema", schema: {...}}}`. GA, no beta header. Legacy `output_format` is deprecated | ✅ ➕ | [ANT-SO] |
| 3b | Supported models | Sonnet 5.5 and Haiku 5.5 are both listed | ✅ | [ANT-SO] |
| 3c | Schema limits | `additionalProperties` must be `false`. Unsupported: `minimum`, `maximum`, `multipleOf`, `minLength`, `maxLength`, `maxItems`, recursion. `minItems` only 0 or 1. `pattern` only for simple regex. Per request: ≤20 strict tools, ≤24 optional params, ≤16 union params. Grammar compile timeout 180 s; first use of a schema adds latency (cached 24 h). No explicit depth or size limit is stated | ✅ ➕ ❓(depth) | [ANT-SO] |
| 3d | Incompatibilities | API citations feature: returns a 400. Assistant prefill: returns a 400 | ✅ | [ANT-SO] |
| 3e | `stop_reason` | `refusal` returns HTTP 200, is billed, and may not match the schema. `max_tokens` output may be invalid. Treat both as failures | ✅ ➕ | [ANT-SO] |
| 4a | `inference_geo` values | `"us"` and `"global"` only; settable per request (including inside batches) | ✅ | [ANT-GEO] |
| 4b | Multiplier | `"us"` = **1.1×** on every token category | ✅ | [ANT-PRC] |
| 4c | Default | When omitted, the **workspace's `default_inference_geo`** applies (the platform default is `global`). `allowed_inference_geos` can restrict the choice | ⚠ D1 | [ANT-GEO], [ANT-SDK] |
| 4d | Data at rest | Workspace geo; `"us"` is the only option and is fixed when the workspace is created | ➕ | [ANT-GEO] |
| 5a | Effort | `output_config.effort` (not top-level), GA. Values: low, medium, high, xhigh, max | ➕ | [ANT-EFF] |
| 5b | Effort defaults | Sonnet 5.5: `high`. Haiku 5.5: `medium` | ➕ | [ANT-EFF] |
| 5c | Turning thinking off | Adaptive thinking is on by default. **Sonnet 5.5 rejects `thinking: {type: "disabled"}` with a 400**; its lowest setting is `{type: "between_tools"}` at effort high or below. Haiku 5.5 accepts `disabled`. `budget_tokens` returns a 400 on both | ⚠ D2 | [ANT-THK] |
| 5d | Thinking + structured outputs | Compatible. Haiku with thinking off may skip a needed tool call when JSON output is also requested. Sonnet at low effort can occasionally hit `max_tokens` | ➕ | [ANT-SO], [ANT-PH], [ANT-PS] |
| 5e | Latency guidance | Use lower effort first. At `low`, Sonnet skips thinking on most simple requests. Changing effort or thinking invalidates the prompt cache | ➕ | [ANT-PS], [ANT-THK] |
| 5f | Sampling parameters | **A non-default `temperature`, `top_p` or `top_k` returns a 400 on every request** | ⚠ D2 | [ANT-THK] |
| 6 | Prompt caching minimum | **512 tokens** for Sonnet 5.5 and Haiku 5.5; TTL 5 min (default) or `"1h"` | ➕ | [ANT-PC] |
| 7 | Audio input | **Not supported.** Input blocks: text, image, document, search_result (plus tool and thinking blocks) | ✅ | [ANT-MOD], [ANT-MSG] |
| 8a | Workspace limits | Spend and rate limits can be set per workspace: rate limits on the Console "Rate limits" page, spend limits on the "Workspaces" page | ✅ | [ANT-RL], [ANT-WS] |
| 8b | Default workspace | "You can't set limits on the default Workspace." | ✅ | [ANT-RL] |
| 8c | Scoped API keys | Keys can be scoped to one workspace | ✅ | [ANT-WS] |
| 8d | Auto-reload | Billing → Credit balance → "Manage auto-reload" → "Turn off". **Whether it is per organisation or per workspace is not stated** | ◐ | [ANT-PAY] |
| 8e | Credit expiry | Prepaid credits expire 1 year after purchase; cannot be extended | ➕ | [ANT-PAY] |
| 9 | Python SDK | `anthropic` 1.14.0 exposes `output_config` and `inference_geo` request params (checked in the installed source) | ✅ | [ANT-SDK] |
| 10 | Batches | 50% off. Most finish within 1 hour; batches expire at 24 h (expired requests are not billed). Structured outputs and caching work (cache hits are best-effort) | ✅ ➕ | [ANT-BAT] |
| 11a | Opus 5.5 model ID (added for D19) | `claude-opus-5-5` is **Active**; retirement not sooner than 2027-09-22. Comparative latency "Moderate" (Sonnet 5.5 "Fast", Haiku 5.5 "Fastest") | ➕ D19 | [ANT-DEP], [ANT-MOD] |
| 11b | Opus 5.5 price | $4 input / $20 output per MTok; cache writes $5 (5-min) / $8 (1-hour); cache read $0.20 (0.05× input); batch $2 / $10. Full 1M context at standard price (no long-prompt tier). `inference_geo: "us"` = 1.1× | ➕ D19 | [ANT-PRC] |
| 11c | Opus 5.5 features | Structured outputs: listed. Prompt-caching minimum: 512 tokens. Effort: all five levels, **default `medium`**. **Adaptive thinking is always on: `thinking: {type: "disabled"}` returns a 400 at every effort level** | ➕ D19 | [ANT-SO], [ANT-PC], [ANT-EFF] |
| 11d | Workspace rate limits | Limits are per model class (Opus 5.5 and Sonnet 5.5 each have their own row); workspace limits are set per limiter type (RPM, ITPM, OTPM) | ➕ | [ANT-RL] |

### 3.2 Agent Platform (formerly Vertex AI): embeddings, Gemini, SDK, free trial

| # | Fact | Verified value | Status | Source |
|---|---|---|---|---|
| 0 | Product name | Vertex AI is now **"Gemini Enterprise Agent Platform"**. Old URLs redirect (301) | ➕ | [GAP-PRC], [GCP-SC] |
| 1a | gemini-embedding-001 request | Model `gemini-embedding-001`; `task_type` RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY (default RETRIEVAL_QUERY) | ✅ | [GAP-E3], [GAP-E2] |
| 1b | 001 dimensions | Default 3072; `output_dimensionality` 768 supported. **Vectors must be re-normalised manually** at sizes other than 3072 | ⚠ D4 | [GAP-E1], [AID-EMB] |
| 1c | 001 input limits | 2,048 tokens per text (truncated unless `autoTruncate=false`); 20,000 tokens per request. Google's docs contradict each other: "250 input texts" vs "a single input text" per request | ◐ D4 | [GAP-E1] |
| 1d | 001 locations | **`me-central1` supported** (also me-west1, me-central2). `global` is used in the code samples but not ticked in the locations table | ◐ | [GAP-LOC], [GAP-E1] |
| 1e | 001 price | $0.15 per 1M online ($0.12 batch). The unit is labelled "count" | ✅ ◐(unit) | [GAP-PRC] |
| 1f | 001 languages | Arabic is listed explicitly | ✅ | [GAP-E3] |
| 2a | gemini-embedding-2 stage | **GA** (2026-04-22); `gemini-embedding-2-preview` is Public preview | ➕ | [GAP-E5] |
| 2b | embedding-2 request | **No `task_type`**. Query: `task: search result \| query: {content}`. Document: `title: {title} \| text: {content}` (`title: none` when there is no title) | ✅ | [GAP-E4] |
| 2c | embedding-2 dimensions | 128–3072; 768 recommended; already L2-normalised; 8,192 max input tokens | ✅ | [GAP-E4], [GAP-E5] |
| 2d | embedding-2 languages | "over 100 languages" (Gemini API docs). **Arabic is not named** for this model | ❓ → measured at M2 | [AID-EMB] |
| 2e | embedding-2 locations | **`global`, `us`, `eu` only. Not `me-central1`** | ⚠ D3 | [GAP-E5], [GAP-LOC] |
| 2f | embedding-2 price | $0.20 per 1M text tokens online ($0.10 batch) | ✅ | [GAP-PRC] |
| 3a | SDK | Use `google-genai`. The generative modules of the Vertex AI SDK (`google-cloud-aiplatform`) were deprecated 2025-06-24 and are removed from releases after 2026-06-24 | ➕ D6 | [GAP-SDK] |
| 3b | Client | `genai.Client(enterprise=True, project=..., location=...)`; `vertexai=True` is the legacy alias (confirmed in installed `google/genai/client.py` 2.31.0) | ➕ D6 | [GENAI-GH] |
| 4a | Transcription model | `gemini-3.5-transcribe` is GA but supports Arabic only as **`ar-EG`, Experimental**. `gemini-3.5-flash` is GA (used in Google's transcription sample; retires 2027-05-19 or later). `gemini-3.8-flash` is GA. **`gemini-2.5-flash` retires 2026-10-20** | ⚠ D7 | [GAP-TR], [GAP-AUD], [GAP-F25], [GAP-F35], [GAP-F38] |
| 4b | Audio MIME types | `audio/webm`, `audio/ogg`, `audio/mp4`, `audio/x-aac` (not `audio/aac`), `audio/wav`, … The Opus codec is not mentioned | ◐ D7 | [GAP-AUD] |
| 4c | Audio token rate | 25 tokens/s (Agent Platform pricing) vs 32 tokens/s (Gemini API docs). Budget for 32 | ◐ | [GAP-PRC], [AID-AUD] |
| 4d | Audio price | Per 1M tokens, global endpoint. 3.5 Flash: $1.50 input (audio included) / $9.00 output. 3.8 Flash: $0.75 / $3.75 until 2026-12-31. Regional endpoints cost about 10% more | ➕ | [GAP-PRC] |
| 4e | Generation locations | **No Gemini generation or transcription model is offered in any Middle East region.** 3.5 Flash: global, us, eu (+ some EU/APAC regions) | ⚠ D3 | [GAP-LOC] |
| 5a | Trial credit covers Agent Platform Gemini | Implied: $300 is given "to explore what they can do with Gemini". No formal product list exists | ◐ → owner checks the first invoice line at M2 | [GCP-FT] |
| 5b | Trial exclusions | Gemini API in AI Studio; generative AI **partner** models (so Claude via Agent Platform is excluded); GPUs; Marketplace; quota increases | ✅ | [GCP-FT] |
| 5c | Trial end | Billing is disabled and resources stop; 30-day grace period, then deletion | ✅ | [GCP-FT] |

### 3.3 Speech-to-Text V2, Chirp 3 (record only: voice removed, D20)

| # | Fact | Verified value | Status | Source |
|---|---|---|---|---|
| 1 | Model | `chirp_3`, Speech-to-Text **V2 API only** | ✅ | [STT-C3] |
| 2 | Locations | `us` and `eu` multi-regions (GA). Endpoint `{REGION}-speech.googleapis.com`. Preview in some extra regions | ✅ | [STT-C3], [STT-REL] |
| 3 | Language ID | `language_codes=["auto"]` or a candidate list such as `["ar-JO","en-US"]` ("language-agnostic transcription", GA). Detected language in `results[].language_code` | ✅ | [STT-C3], [STT-RECO] |
| 4 | Arabic stage | **`ar-JO` is Preview**; all 18 `ar-*` locales are Preview | ✅ | [STT-C3] |
| 5 | Adaptation | GA for chirp_3, **up to 1,000 phrases**, phrase sets inline or by reference. Boost for chirp_3 is not documented | ✅ ❓(boost) | [STT-C3], [STT-REC] |
| 6 | Encodings | `AutoDetectDecodingConfig` covers WAV, FLAC, MP3, OGG_OPUS, **WEBM_OPUS**, **MP4_AAC**, M4A_AAC, MOV_AAC, AMR. The `/docs/encoding` page is outdated | ◐ → test Chrome WebM and Safari MP4 at M4 | [STT-REC], [STT-ENC] |
| 7 | Word confidence / timestamps | **Not supported by Chirp 3** (listed under "doesn't support") | ⚠ D8 | [STT-C3] |
| 8 | Sync `Recognize` limit | 10 MB or **1 minute** of audio. Our clips are capped at 30 s | ➕ | [STT-QUO] |
| 9 | Price | V2 "Standard" models (the list names `chirp`, V2 only): **$0.016/min** for 0–500k min/month; requests rounded up to 1 s. **No V2 free tier** (the 60 free minutes apply to V1). `chirp_3` is not named separately | ✅ ◐ | [STT-PRC] |
| 10 | IAM | `roles/speech.client` includes `speech.recognizers.recognize`; the implicit recognizer `recognizers/_` works | ✅ | [IAM-SPEECH], [STT-RECO] |

### 3.4 Text-to-Speech, Chirp 3 HD (record only: voice removed, D20)

| # | Fact | Verified value | Status | Source |
|---|---|---|---|---|
| 1 | Arabic | `ar-XA` is supported by Chirp 3 HD (GA). `ar-XA` and `en-US` share 30 voice names of the form `<locale>-Chirp3-HD-<Name>`, e.g. `ar-XA-Chirp3-HD-Charon` (male), `ar-XA-Chirp3-HD-Kore` (female) | ✅ ➕ | [TTS-VOI], [TTS-C3] |
| 2 | Endpoints | global, us, eu and others. Hosts: `texttospeech.googleapis.com`, `eu-texttospeech.googleapis.com`, `us-texttospeech.googleapis.com`. One sentence on the endpoints page is ambiguous, so use the **global** endpoint | ◐ D9 | [TTS-C3], [TTS-END] |
| 3 | Output / limits | MP3 available for non-streaming calls. SSML is Preview for Chirp 3 HD. **5,000 bytes per request** (our 1,500-character answer cap is about 3,000 bytes in Arabic). 200 requests/min | ➕ | [TTS-C3], [TTS-QUO] |
| 4 | Price | **Chirp 3 HD: 0–1M characters free, then $30 per 1M** (page states "per month"; per-billing-account scope not stated on the page) | ✅ ◐(scope) | [TTS-PRC] |
| 5 | IAM | No TTS-specific role exists. The auth page names Service Usage Consumer in general guidance | ◐ (inferred) | [TTS-AUTH] |

### 3.5 Cloud Run, gcloud and project setup

| # | Fact | Verified value | Status | Source |
|---|---|---|---|---|
| 1 | Cloud Run region | `me-central1` (Doha) is listed, **Tier 2** pricing. Artifact Registry and Cloud Build also list it | ✅ | [RUN-LOC] |
| 2 | Deploy flags | `--source`, `--image`, `--region`, `--service-account`, `--set-secrets`, `--set-env-vars`, `--min/--max` (service level) and `--min-instances/--max-instances` (revision level), `--concurrency`, `--cpu`, `--memory`, `--timeout`, `--labels`, `--[no-]allow-unauthenticated`, `--build-service-account` all exist (GA) | ✅ | [GCL-RUN] |
| 3 | Source-deploy destination | Without `--image`, builds go to an auto-created **`cloud-run-source-deploy`** repository. With `--source` plus `--image`, the image name must equal the service name | ⚠ D11 | [RUN-SRC], [GCL-RUN] |
| 4 | Roles for source deploys | `roles/run.sourceDeveloper` + `roles/serviceusage.serviceUsageConsumer` + `roles/iam.serviceAccountUser` (on the runtime SA). The build SA needs `roles/run.builder`. **`--allow-unauthenticated` needs `run.services.setIamPolicy`** (in `roles/run.admin`) | ⚠ D12 | [RUN-SRC], [IAM-RUN], [RUN-PUB] |
| 5 | Default build SA | Compute Engine default SA, created automatically after the Run API is enabled. Google recommends replacing its Editor grant | ➕ D12 | [RUN-BSA], [CB-SA] |
| 6 | Extra APIs | `iam.googleapis.com` (create SAs), **`iamcredentials.googleapis.com` ("To impersonate a service account, you need to enable the Service Account Credentials API")**, `cloudresourcemanager.googleapis.com` (project IAM via gcloud). `billingbudgets.googleapis.com` is needed only for budgets created with gcloud | ⚠ D10 | [IAM-IMP], [IAM-SAC], [IAM-QS], [GCP-BAPI] |
| 7 | Default-enabled services | A new project has about 23 services enabled (logging, monitoring, storage, BigQuery family, …). Storage is used by source deploys | ➕ | [SU-DEF] |
| 8 | gcloud configuration | `gcloud config configurations create NAME --no-activate`. `--configuration` is a gcloud-wide flag. Read the project with **`gcloud config get project`** (`config get-value` is gone from the reference). Precedence: `--project` > `CLOUDSDK_CORE_PROJECT` > configuration. Behaviour when `CLOUDSDK_ACTIVE_CONFIG_NAME` names a missing configuration: **not documented** | ✅ ❓ | [GCL-CC], [GCL-CG], [SDK-PROP], [SDK-CONF] |
| 9 | Project ID rules | 6–30 characters, lowercase letters, digits and hyphens, starts with a letter, no trailing hyphen; no restricted strings (e.g. "google") | ✅ | [GCL-PC], [RM-PROJ] |
| 10 | Billing ID without CLI | Console → Billing → Account management. Linking can also be done in the Console | ✅ | [BIL-ID], [BIL-MOD] |
| 11 | Artifact Registry cleanup | JSON list of rules (`action.type` Keep or Delete; `condition.tagState`; `mostRecentVersions.keepCount`). **Keep wins over Delete; a Keep rule alone deletes nothing.** Changes apply within about a day. `--no-dry-run` "disables dry run functionality for the repository" ([AR-CP]); the command's reference lists only `--dry-run` and states no default, so `infra/04` passes `--no-dry-run` explicitly | ✅ ➕ | [AR-CP], [GCL-ARCP] |
| 12 | Secret Manager | `--replication-policy=automatic` or user-managed with `--locations`. **Cloud Run cannot use regional secrets.** `me-central1` is not confirmed for user-managed replication. Free tier: 6 active versions + 10,000 accesses per month **per billing account** | ⚠ D15 | [GCL-SC], [SM-LOC], [SM-REP], [RUN-SEC], [GCP-FT] |
| 13 | Logging | Cloud Run logs go to Cloud Logging automatically; free allotment 50 GiB per project per month | ✅ | [RUN-LOG] |

### 3.6 LanceDB

| # | Fact | Verified value | Status | Source |
|---|---|---|---|---|
| 1 | Version | 0.40.0 (2026-10-07). abi3 wheels for win_amd64 and manylinux x86_64 cover CPython ≥3.10 | ✅ | PyPI |
| 2 | Licence / mode | Apache-2.0. "LanceDB OSS runs inside your application process" | ✅ | [LDB-LIC], [LDB-FAQ], [LDB-ENT] |
| 3 | Local table | `db = lancedb.connect("path")`; `db.create_table(name, data, schema=schema, mode="overwrite")`; vector field `pa.list_(pa.float32(), dim)` | ✅ | [LDB-QS], [LDB-TC] |
| 4 | Cosine search | `tbl.search(v).distance_type("cosine").limit(k)`. `.metric()` is an alias that "may be deprecated". The default metric is `l2` | ⚠ (use `distance_type`) | [LDB-VS], installed `lancedb/query.py` |
| 5 | Exact search | "No index or `.bypass_vector_index()` → Exact kNN (100% recall)". We call `bypass_vector_index()` explicitly so search stays exact even if an index is ever built | ✅ | [LDB-VS] |

### 3.7 Licences

| Component | Licence | Notes | Source |
|---|---|---|---|
| Cytoscape.js 3.34.3 | MIT | M7 only | [CY-LIC] |
| segno 1.6.6 | BSD-3-Clause | **Chosen** QR library | [SEGNO-LIC] |
| qrcode 8.2 | BSD-3-Clause (+ MIT notice) | Not chosen: PyPI also shows a conflicting "Other/Proprietary" classifier | [QR-LIC] |
| IBM Plex Sans / Sans Arabic 1.1.0 | SIL OFL 1.1 | Self-hosting allowed with the licence and copyright included. Reserved Font Name "Plex": changing the format counts as modification, so serve IBM's `.woff2` files unchanged | [PLEX-LIC] |
| pdfplumber | MIT | | [PLUMB-LIC] |
| pypdf | BSD-3-Clause | | [PYPDF-LIC] |
| pypdfium2 | Apache-2.0 / BSD-3-Clause + PDFium licences | Ship the licence notices with the image | [PDFIUM] |
| gitleaks 8.30.1 | MIT | Binary used in CI | [GL-REL] |

### 3.8 CI and tooling

| Fact | Verified value | Source |
|---|---|---|
| actions/checkout | v7.0.1 → `3d3c42e5aac5ba805825da76410c181273ba90b1` (also checked with `git ls-remote`) | [CO-REL] |
| astral-sh/setup-uv | v10.3.0 → `1c37ad07a6a961277cf70c0d37d6f313000f5884`; there is no floating `v10` tag (also checked with `git ls-remote`) | [SUV-REL] |
| gitleaks | v8.30.1. `gitleaks_8.30.1_linux_x64.tar.gz` sha256 `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb` (from the release checksums file). Command: `gitleaks git --redact --exit-code 1` | [GL-REL] |
| gitleaks-action | v2 no longer runs on GitHub-hosted runners (Node 20 removed 2026-09-16). v3 needs `GITLEAKS_LICENSE` for **organization** repositories | [GL-ACT] |
| uv | 0.13.1. `uv sync --locked` fails if `uv.lock` would change. Dev dependencies go in `[dependency-groups] dev` | [UV-INST], [UV-CLI], [UV-DEP] |
| GNU make (Windows) | winget `ezwinports.make` 4.4.1, GPL-3.0 (a tool only, not shipped) | [WG-MAKE] |

---

## 4. Consequences

- **Claude client (M3):** `app/llm/client.py` never sends sampling parameters and sets `output_config.effort` per route. It treats `stop_reason` `refusal` or `max_tokens` as verification failures. Pydantic schemas must avoid unsupported keywords; the SDK's `parse()` helpers move them into field descriptions.
- **Embeddings (M2):** the M2 A/B also measures Arabic quality for `gemini-embedding-2`, since Arabic is not documented for it. `gemini-embedding-001` vectors are re-normalised after truncation to 768. Batch size is tested.
- **Voice:** removed (D20). M4 builds the API, UI and Trust pack part 1 only.
- **Prices:** `app/prices.py` (M3) cites this ADR's date.

---

## 5. Deviations from PROJECT_PLAN (flagged, not silently applied)

| ID | Plan says | Official docs say | Handling | Owner decision? |
|---|---|---|---|---|
| **D1** | `INFERENCE_GEO=us` default | When the param is omitted, the workspace `default_inference_geo` applies (platform default `global`). `us` costs 1.1×; neither option is in the Middle East | Keep `us` as configured and send it on every request. Optionally set the workspace default to match | **Yes**: `us` (+10% cost) or `global` |
| **D2** | "effort/thinking set low" | Sonnet 5.5 cannot disable thinking (lowest is `between_tools`); non-default `temperature`/`top_p`/`top_k` returns a 400 on both models | Sonnet `effort=low` with adaptive thinking; Haiku planner `thinking=disabled`; never send sampling params | No (technical) |
| **D3** | `VERTEX_LOCATION` "set in ADR"; Cloud Run `me-central1` | Only `gemini-embedding-001` is offered in `me-central1`. `gemini-embedding-2` and all Gemini generation/transcription models are global, us or eu only | `VERTEX_LOCATION=global`; `eu` if EU processing is preferred (about 10% more on pennies) | **Yes**: `global` or `eu` |
| **D4** | 768 dims for both models | 001 needs manual re-normalisation at 768. 001 batch-size docs contradict each other. Arabic is not stated for embedding-2 | Handle in M2 code; measure in the A/B | No |
| **D5** | — | Haiku 5.5 has a 5× price tier above 100k prompt tokens | Our prompts are about 2–6k tokens; the cost guard asserts a prompt-size ceiling | No |
| **D6** | `google-genai` **or** `google-cloud-aiplatform` | The aiplatform generative modules are removed; `enterprise=True` is the current flag | `google-genai==2.31.0` only | No |
| **D7** | "a current Gemini model" for STT; MediaRecorder WebM/MP4 | `gemini-2.5-flash` retires 2026-10-20. `gemini-3.5-transcribe` Arabic is `ar-EG` Experimental only. Send `audio/x-aac`, not `audio/aac` | Bake-off candidate `gemini-3.5-flash` | No |
| **D8** | "word confidences if available" (P-02) | Chirp 3 supports **no** word confidence and no timestamps | P-02 underlining applies only if Gemini wins the bake-off; otherwise documented in LIMITATIONS | No (P-02 is conditional) |
| **D9** | TTS endpoint "confirm at M0" | Regional endpoint wording is ambiguous; 5,000 bytes per request | Use the global endpoint; keep the 1,500-character answer cap | No |
| **D10** | Enable **only** run, cloudbuild, artifactregistry, secretmanager, aiplatform, speech, texttospeech, logging | `iam`, `iamcredentials` (impersonation) and `cloudresourcemanager` (project IAM) are required for step C. `billingbudgets` only for a CLI budget | `infra/02` gates the 3 behind `APPROVE_EXTRA_APIS=1`; the budget defaults to the Console route | **Yes**: approve the 3 extra APIs |
| **D11** | `gcloud run deploy --source .` + an `almamlaka` repo with keep-2 cleanup | `--source` alone pushes to `cloud-run-source-deploy`, bypassing the cleanup policy | M6 deploys with `--source . --image=me-central1-docker.pkg.dev/$P/almamlaka/<service>`. Staging and prod are separate packages (up to 4 images); proposal: promote the staging digest to prod without a rebuild | At M6 |
| **D12** | Deployer: "deploy roles on this project only" | Documented roles are `run.sourceDeveloper`, `run.builder`, `serviceUsageConsumer`, and `serviceAccountUser` on the runtime SA. `--allow-unauthenticated` needs `run.admin`. Google auto-creates the Compute default SA, which may hold Editor | The deployer also acts as the build SA (no third SA). `infra/03` grants the deployer's roles only with `APPROVE_DEPLOYER_ROLES=1`. The owner grants public invoker once at M6 instead of giving the deployer `run.admin`. Whether to remove Editor from the Compute default SA is an open question | **Yes**: approve the role set |
| **D13** | $25 budget with 50/80/100% alerts | By default budgets include credits, so a trial shows about $0 and alerts never fire. Console default thresholds are 50/90/100. The gcloud value is `exclude-all-credits` (lowercase) | Clear all Savings/credits (Console) or `--credit-types-treatment=exclude-all-credits`; set 80% explicitly | No |
| **D14** | Spend Caps on Cloud Run and Agent Platform "if eligible" | Public Preview; Console only; one project and service per cap; monthly; counts cost **before** credits. Eligible services: Gemini API, Agent Platform, Cloud Run, Cloud Run functions. **Not STT or TTS.** Free-trial eligibility not stated | Owner tries it in the Console (suggested $5 per cap) and records the result | **Yes**: cap amounts; record eligibility |
| **D15** | — | Cloud Run cannot use regional secrets; user-managed `me-central1` replication not confirmed | `--replication-policy=automatic` | No |
| **D16** | "gitleaks binary in CI" | gitleaks-action v2 is broken on hosted runners; v3 needs a licence for org repos | Pinned, checksum-verified binary | No |
| **D17** | §7.2 runtime deps | `google-cloud-speech` was missing but is needed for Chirp 3 | Added `google-cloud-speech==2.41.0`. **Reverted by D20** (both speech packages removed) | No |
| **D18** | §7.1 tree: `infra/setup_project.sh budget.sh` | — | `infra/01…07_*.sh` (one per setup step) + `_common.sh`; developer tools in `tools/` | No (layout) |
| **D21** | §4.4 control 4: ingestion "flags instruction-like or hidden text for human review" | M1 review: flagged hidden text left in a chunk would still reach the model | Implemented in `app/ingest/flags.py` and `extract.py`. **Hidden text is removed from chunk text and reported.** Since the M1 red team, it is judged on the page rendered by pdfium, not from colours: a character is visible only if its box shows ink against its surroundings. That catches white-on-white, transparency and soft masks, clipping, opaque covers, white outlines and spot colours. Tiny or off-page text is hidden too. **Optional content layers (/OCProperties) stop ingestion**, and so does a document with 0 sections. **Open (M5):** Arabic PDFs may extract in visual (reversed) order, so Arabic instruction patterns can't fire on them yet. It is fixed and tested with the Arabic fixtures FX-1/FX-2/FX-5. `make index` fails if that happens on the production corpus. **Invisible render modes (Tr 3/7)** on a page, or in a Form XObject it draws, **stop ingestion**, because pdfplumber can't tell which characters are invisible. Instruction-like text (EN/AR, matched after Arabic normalisation) stays in the chunk and is only reported. So I-02 (FX-1 hidden text, M5) tests removal plus the report, not the model's own resistance; H and I-01/I-03/I-04 still test the model. Locally the ING-02 oracle may run Git for Windows' xpdf `pdftotext`; CI requires poppler | No (owner may override) |
| **D22** | R10 / §5.6 / non-negotiable 15: name as plain text only; no logo, colours or look-alike styling (no brand permission) | The client brief the owner forwarded on 2026-10-15 asks: "Apply Almamlaka TV branding (name, colors/logo if possible)" | Not changed yet; UI branding is built at M4 | **Yes, before M4**: is there permission, and where do the official logo and colour values come from? |
| **D23** | §3.1 UI: static HTML + vanilla JS, no build step | Owner direction, 2026-10-15: React + TypeScript + Tailwind + shadcn, built around two supplied components (`particle-title`, `branching-reasoning-chat-input`) | The front end is a Vite + React + TypeScript app in `web/`. The build output is served by the same FastAPI service, so there is still one Cloud Run service and no CDN or external assets. The supplied components are adapted:<br>- multi-turn transcript, server-rendered citations, conflict callouts and RTL/bidi;<br>- the "approaches" deck shows the real pipeline trace (searches, documents, verification), **never invented scores**;<br>- no Unsplash or other remote images (CSP `default-src 'self'`). | Decided |
| **D24** | No report feature in the plan | Owner direction, 2026-10-15: an **"Executive report"** button that analyses all three documents and builds a report from a predefined branded template, on Claude Opus 5.5 | The same grounding and verification as chat: every statement carries `{chunk_id, quote}` and is verified, and conflicts (C1, C2, T1–T4) are reported, never resolved. The corpus is fixed, so the report is generated once per (corpus hash, template version, model) and cached; repeat clicks cost $0 and return the identical, verified report. About $0.10–0.20 per generation [Estimate]; regeneration needs the operator | Decided |
| **D20** | v1 core includes the **Voice pack** (§5.4): Chirp 3 or Gemini speech-to-text, Chirp 3 HD text-to-speech | Owner decision, 2026-10-15: remove speech so the project stays fully free on GCP; the only paid service is the Claude API. Speech-to-Text V2 has no free tier (§3.3 row 9), and the TTS free tier is counted per billing account, which this project shares with two other owner projects | **Removed.** Not enabled: `speech.googleapis.com`, `texttospeech.googleapis.com`. Removed: `roles/speech.client`, the runtime's `serviceusage.serviceUsageConsumer` (it was only for TTS; add it back only if the first embedding call at M2 needs it), both Google speech packages, and the `TTS_*`/`STT_*` settings. `FEATURE_VOICE=false`. **Not applicable** in `ACCEPTANCE_TESTS.md`, which is left unchanged: P-01…P-10, N-15, TV-07, and the TTS half of Q-07. D7, D8, D9 and D17 no longer apply | Decided |
| **D19** | Planner and verifier on Haiku 5.5, answer on Sonnet 5.5; §3.4 budget of about $0.007–0.017 per turn | Owner direction, 2026-10-15: "use Opus and Sonnet, neglect Haiku for the moment". List prices: Sonnet is 20× Haiku; Opus is 2× Sonnet (§3.1 rows 2, 11b). Opus 5.5 thinking cannot be turned off | Estimates (§3.4 per-turn figures × these price ratios; to be replaced by M3/M5 measurements): **(a)** plan, Haiku/Sonnet/Haiku ≈ $0.007–0.017 per turn; **(b)** Sonnet planner + Opus answer + Sonnet verifier ≈ $0.028–0.048, a **lower bound**: it assumes Opus uses as many tokens as Sonnet at `low` effort, but Opus thinking cannot be turned off and defaults to `medium`; **(c)** Sonnet on all three routes ≈ $0.022–0.032. With the §3.4 reviewer allowance of $11, that is about 650–1,550 turns for (a), 230–390 for (b) and 340–500 for (c). The $7 evaluation allowance grows to roughly $16 under (c) and $22 under (b), so (b) or (c) does not fit $25 unless evaluation repeats and reviewer turns are cut, or the Claude budget is raised. `.env.example` keeps the plan's defaults until the owner decides; the client lands at M3 | **Yes**: model per route, and whether the $25 Claude budget changes |

---

## 6. Inconsistencies inside the handoff documents (recorded; `docs/` copies left byte-identical)

1. PROJECT_PLAN §7.2 says "Not used: … vector DBs", but LanceDB is the approved vector DB (v0.3). **LanceDB is authoritative.**
2. docs/ENGINEERING_RULES.md says `make embed` writes `data/index/embeddings.npy`; PROJECT_PLAN §3.1/§7.1 say `data/index/lancedb/`.
   **Resolved at M2:**
   - `make embed` writes `data/index/embeddings/<model>.npy` plus a `.json` sidecar (chunk IDs and the
     `chunks.jsonl` hash, so stale vectors are refused).
   - At start-up these vectors are loaded into an **embedded LanceDB table** and searched exactly (cosine,
     vector index bypassed).
   - Why: LanceDB's own files contain random IDs and timestamps, so they can't be byte-reproducible in git;
     the `.npy` vectors are.
   - LanceDB stays the only vector database.
3. docs/ENGINEERING_RULES.md says "every Make target checks the active project"; ACCEPTANCE Q-05 says only targets touching GCP. **Q-05 is followed**, because `make check` must run in CI without gcloud.
4. "Explicit `--project` on every gcloud command" cannot hold for `projects create`, the project IAM commands (`projects add-iam-policy-binding`, `projects get-iam-policy`), `billing projects link` or budgets. Documented positional/filter forms are allow-listed in `tests/unit/test_infra_static.py`.
5. ACCEPTANCE K-03 names `SESSION_SECRET` and `CANARY_TOKEN`, which are fields of the `APP_SECRETS` bundle. K-10 uses `PUBLIC_MODE`, which is not in §7.3; it was added to `.env.example` (default false). SUB-06's "test flag" is still undefined (M6b).
6. PROJECT_PLAN §3.4 asks to "check that the other projects don't already use" Secret Manager's free tier. The tooling may not read other projects; **only the owner can check, in Billing → Reports.**
7. The §7.1 tree shows `adr/` under `submission/` (a formatting slip). The ADR is at `docs/adr/`.

## 7. Open questions for the owner

1. **D1:** `INFERENCE_GEO` `us` (+10%) or `global`?
2. **D3:** `VERTEX_LOCATION` `global` or `eu`?
3. **D10 / D12:** approve the 3 extra APIs and the deployer role set?
4. **D14:** Spend Cap amounts (suggested $5 for Cloud Run and $5 for Agent Platform), and whether the trial account offers them.
5. **Anthropic auto-reload scope:** the docs don't say whether it is per organisation. Is turning it off acceptable for anything else on the same Anthropic organisation?
6. **Compute Engine default SA:** remove its automatic Editor grant (hardening), or leave it?
7. **D19:** which model on each route (planner, answer, verifier) now that Haiku is set aside, and does the
   $25 Claude budget stay? Options and estimated costs are in §5.
8. **D22 (before M4):** the brief asks for Almamlaka TV branding "if possible". Is that permission? If yes, the
   owner supplies the official logo file and colour values, which are self-hosted, and the prototype
   disclaimer stays.

### Owner answers (2026-10-15): these decisions are final

| ID | Decision |
|---|---|
| D1 | `INFERENCE_GEO=global` |
| D3 | `VERTEX_LOCATION=global` |
| D10, D12 | Approved: run `infra/02` with `APPROVE_EXTRA_APIS=1` and `infra/03` with `APPROVE_DEPLOYER_ROLES=1` |
| D14 | Spend Caps of $5/month each on Cloud Run and Agent Platform, if the trial account offers them |
| Q5 (auto-reload) | The owner's other projects use a different Anthropic organisation; only the GCP billing account is shared. Auto-reload is turned off on the Almamlaka Anthropic organisation |
| Q6 (Compute default SA) | Not decided; left as Google creates it |
| D19 | **Claude Sonnet 5.5 for planner, answer and verifier.** Claude Opus 5.5 only for the Executive report (D24) |
| D22 | **Branding approved from the official website `https://almamlakatv.com/ar`**: name, logo and colours, self-hosted (no hotlinking). The owner may upload samples later to refine them. This overrides docs/ENGINEERING_RULES.md rule 15 and R10; the prototype disclaimer stays |
| D23 | UI in React + TypeScript + Tailwind + shadcn (see §5) |
| D24 | Executive report (see §5). Implemented at M3 as app/pipeline/report.py: generated only by the operator (`make report`), saved in data/reports/ keyed by (chunks hash, template exec-v1, model, language) and served read-only; a click never calls Claude |
| D25 | **Font: Almamlaka TV's own `ALMAMLAKAFONT`** for Arabic and English. It is the font the official site uses for both languages; the owner pointed to `/coming-soon`, and its English text renders in ALMAMLAKAFONT-Extrabold/Medium (checked in a browser). Three weights are self-hosted unmodified from `https://almamlakatv.com/fonts/`. The licence is not published, so it is accepted for this Almamlaka prototype and must not be reused elsewhere. IBM Plex is removed. **Layout follows almamlakatv.com:** two-tier header, red pill action, navy "trending" strip, red-bar headings, small corners |
| D26 | **Dense leg measured, shipped OFF behind `DENSE_ENABLED`** (2026-10-16). gold-v1, recall@5: raw questions BM25 0.69 (Arabic 0.14) vs hybrid gemini-embedding-2 0.99 (Arabic 1.00); with the planner's queries (production) BM25 1.00 vs hybrid 1.00, conflict evidence 5/5 both. No production gain, while each search adds a Vertex call (latency, per-minute quota: gemini-embedding-001 is blocked by a near-zero quota on the new project) and becomes a charge after the trial. Corpus vectors for gemini-embedding-2 are committed so it can be switched on as a safety net; reports in eval/reports/retrieval/. A/B spend $0.28 (planner) |

---

## 8. Sources (all accessed 2026-10-15; all returned HTTP 200)

**Anthropic**
- [ANT-DEP] https://platform.claude.com/docs/en/about-claude/model-deprecations.md
- [ANT-MOD] https://platform.claude.com/docs/en/models/overview.md
- [ANT-PRC] https://platform.claude.com/docs/en/about-claude/pricing.md
- [ANT-SO] https://platform.claude.com/docs/en/build-with-claude/structured-outputs.md
- [ANT-GEO] https://platform.claude.com/docs/en/manage-claude/data-residency.md
- [ANT-EFF] https://platform.claude.com/docs/en/build-with-claude/effort.md
- [ANT-THK] https://platform.claude.com/docs/en/build-with-claude/thinking.md
- [ANT-PH] https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-haiku-5-5.md
- [ANT-PS] https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5.md
- [ANT-PC] https://platform.claude.com/docs/en/build-with-claude/prompt-caching.md
- [ANT-MSG] https://platform.claude.com/docs/en/api/messages/create.md
- [ANT-RL] https://platform.claude.com/docs/en/api/rate-limits.md
- [ANT-WS] https://platform.claude.com/docs/en/manage-claude/workspaces.md
- [ANT-PAY] https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage
- [ANT-BAT] https://platform.claude.com/docs/en/build-with-claude/batch-processing.md
- [ANT-SDK] https://github.com/anthropics/anthropic-sdk-python/blob/v1.14.0/src/anthropic/types/message_create_params.py

**Google: Agent Platform, Gemini, billing.** Base for the GAP keys: `https://docs.cloud.google.com/gemini-enterprise-agent-platform/`
- [GAP-E1] …/models/embeddings/get-text-embeddings
- [GAP-E2] …/models/embeddings/task-types
- [GAP-E3] …/reference/models/text-embeddings-api
- [GAP-E4] …/models/embeddings/get-multimodal-embeddings
- [GAP-E5] …/models/gemini/embedding-2
- [GAP-LOC] …/resources/locations
- [GAP-AUD] …/models/capabilities/audio-understanding
- [GAP-TR] …/models/gemini/3-5-transcribe
- [GAP-F25] …/models/gemini/2-5-flash
- [GAP-F35] …/models/gemini/3-5-flash
- [GAP-F38] …/models/gemini/3-8-flash
- [GAP-PRC] https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing
- [GAP-SDK] https://docs.cloud.google.com/vertex-ai/generative-ai/docs/deprecations/genai-vertexai-sdk
- [GENAI-GH] https://github.com/googleapis/python-genai (plus the installed `google/genai/client.py` 2.31.0)
- [AID-EMB] https://ai.google.dev/gemini-api/docs/embeddings
- [AID-AUD] https://ai.google.dev/gemini-api/docs/audio
- [GCP-FT] https://docs.cloud.google.com/free/docs/free-cloud-features
- [GCP-SC] https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps
- [GCP-BLOG] https://cloud.google.com/blog/topics/cost-management/new-early-anomalies-and-spend-caps-on-google-cloud-budgets
- [GCP-BLOG2] https://cloud.google.com/blog/topics/cost-management/introducing-spend-caps-ai-cost-visibility-next26
- [GCP-BUD] https://docs.cloud.google.com/billing/docs/how-to/budgets
- [GCL-BUD] https://docs.cloud.google.com/sdk/gcloud/reference/billing/budgets/create
- [GCP-BAPI] https://docs.cloud.google.com/billing/docs/how-to/budget-api-setup

**Google: Speech-to-Text and Text-to-Speech**
- [STT-C3] https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3
- [STT-REC] https://docs.cloud.google.com/speech-to-text/docs/reference/rest/v2/projects.locations.recognizers
- [STT-RECO] https://docs.cloud.google.com/speech-to-text/docs/reference/rest/v2/projects.locations.recognizers/recognize
- [STT-QUO] https://docs.cloud.google.com/speech-to-text/docs/quotas
- [STT-ENC] https://docs.cloud.google.com/speech-to-text/docs/encoding
- [STT-REL] https://docs.cloud.google.com/speech-to-text/docs/release-notes
- [STT-PRC] https://cloud.google.com/speech-to-text/pricing
- [IAM-SPEECH] https://docs.cloud.google.com/iam/docs/roles-permissions/speech
- [TTS-C3] https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd
- [TTS-VOI] https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types
- [TTS-END] https://docs.cloud.google.com/text-to-speech/docs/endpoints
- [TTS-QUO] https://docs.cloud.google.com/text-to-speech/quotas
- [TTS-AUTH] https://docs.cloud.google.com/text-to-speech/docs/authentication
- [TTS-PRC] https://cloud.google.com/text-to-speech/pricing

**Google: Cloud Run, IAM, gcloud.** All gcloud commands used in `infra/` were also checked on their reference pages under https://docs.cloud.google.com/sdk/gcloud/reference/
- [RUN-LOC] https://docs.cloud.google.com/run/docs/locations
- [GCL-RUN] https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy
- [RUN-SRC] https://docs.cloud.google.com/run/docs/deploying-source-code
- [RUN-IMG] https://docs.cloud.google.com/run/docs/deploying
- [RUN-BSA] https://docs.cloud.google.com/run/docs/configuring/services/build-service-account
- [CB-SA] https://docs.cloud.google.com/build/docs/cloud-build-service-account-updates
- [IAM-RUN] https://docs.cloud.google.com/iam/docs/roles-permissions/run
- [RUN-PUB] https://docs.cloud.google.com/run/docs/authenticating/public
- [IAM-AIP] https://docs.cloud.google.com/iam/docs/roles-permissions/aiplatform
- [RUN-SEC] https://docs.cloud.google.com/run/docs/configuring/services/secrets
- [RUN-LOG] https://docs.cloud.google.com/run/docs/logging
- [IAM-IMP] https://docs.cloud.google.com/docs/authentication/use-service-account-impersonation
- [IAM-QS] https://docs.cloud.google.com/iam/docs/quickstart-client-libraries
- [IAM-SAC] https://docs.cloud.google.com/iam/docs/service-accounts-create
- [GCL-SAB] https://docs.cloud.google.com/sdk/gcloud/reference/iam/service-accounts/add-iam-policy-binding
- [GCL-PC] https://docs.cloud.google.com/sdk/gcloud/reference/projects/create
- [RM-PROJ] https://docs.cloud.google.com/resource-manager/docs/creating-managing-projects
- [GCL-BL] https://docs.cloud.google.com/sdk/gcloud/reference/billing/projects/link
- [BIL-MOD] https://docs.cloud.google.com/billing/docs/how-to/modify-project
- [BIL-ID] https://docs.cloud.google.com/billing/docs/how-to/find-billing-account-id
- [GCL-CC] https://docs.cloud.google.com/sdk/gcloud/reference/config/configurations/create
- [GCL-CG] https://docs.cloud.google.com/sdk/gcloud/reference/config/get
- [SDK-PROP] https://docs.cloud.google.com/sdk/docs/properties
- [SDK-CONF] https://docs.cloud.google.com/sdk/docs/configurations
- [SU-DEF] https://docs.cloud.google.com/service-usage/docs/enabled-service
- [AR-CP] https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy
- [GCL-ARCP] https://docs.cloud.google.com/sdk/gcloud/reference/artifacts/repositories/set-cleanup-policies
- [GCL-SC] https://docs.cloud.google.com/sdk/gcloud/reference/secrets/create
- [SM-LOC] https://docs.cloud.google.com/secret-manager/docs/locations
- [SM-REP] https://docs.cloud.google.com/secret-manager/docs/choosing-replication

**LanceDB, licences, CI**
- [LDB-LIC] https://github.com/lancedb/lancedb/blob/main/LICENSE
- [LDB-FAQ] https://docs.lancedb.com/faq/faq-oss
- [LDB-ENT] https://docs.lancedb.com/enterprise
- [LDB-QS] https://docs.lancedb.com/quickstart
- [LDB-TC] https://docs.lancedb.com/tables/create
- [LDB-VS] https://docs.lancedb.com/search/vector-search
- [CY-LIC] https://github.com/cytoscape/cytoscape.js/blob/unstable/LICENSE
- [SEGNO-LIC] https://github.com/heuer/segno/blob/master/LICENSE
- [QR-LIC] https://github.com/lincolnloop/python-qrcode/blob/main/LICENSE
- [PLEX-LIC] https://github.com/IBM/plex/blob/master/LICENSE.txt
- [PDFIUM] https://github.com/pypdfium2-team/pypdfium2
- [PLUMB-LIC] https://github.com/jsvine/pdfplumber/blob/stable/LICENSE.txt
- [PYPDF-LIC] https://github.com/py-pdf/pypdf/blob/main/LICENSE
- [GL-REL] https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1
- [GL-ACT] https://github.com/gitleaks/gitleaks-action
- [CO-REL] https://github.com/actions/checkout/releases/tag/v7.0.1
- [SUV-REL] https://github.com/astral-sh/setup-uv/releases/tag/v10.3.0
- [UV-INST] https://docs.astral.sh/uv/getting-started/installation/
- [UV-CLI] https://docs.astral.sh/uv/reference/cli/
- [UV-DEP] https://docs.astral.sh/uv/concepts/projects/dependencies/
- [WG-MAKE] https://github.com/microsoft/winget-pkgs/tree/master/manifests/e/ezwinports/make/4.4.1
