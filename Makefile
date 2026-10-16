# almamlaka-pdf-assistant task runner (targets: README "Run locally").
#
# Every recipe is one plain command (`uv run ...` or `echo`), so it works whether GNU make uses sh
# or cmd.exe on Windows. Without make, run the command shown in the recipe directly (see README).
#
# Isolation (PROJECT_PLAN §3.6, ACCEPTANCE_TESTS Q-05): every target that touches GCP lists
# `gcp-guard` as its first prerequisite once implemented. Stubs below touch nothing and exit 0.

# Any gcloud call made under make uses the dedicated configuration.
export CLOUDSDK_ACTIVE_CONFIG_NAME := almamlaka
export PYTHONUTF8 := 1
# Development default; check/test force replay so tests can never make live LLM calls (Q-04).
export LLM_MODE ?= replay
check test lint: export LLM_MODE := replay

UV ?= uv
MODE ?= default
URL ?=

.DEFAULT_GOAL := help
.PHONY: help setup check lint test manifest gcp-guard index fixtures embed eval-retrieval report report-pdf cost-report eval \
	run e2e radar smoke screenshots demo-video release-zip graph

help:
	@echo Targets: setup check lint test manifest gcp-guard index fixtures embed eval-retrieval report report-pdf cost-report eval run e2e radar smoke screenshots demo-video release-zip graph

## ---- implemented at M0 ---------------------------------------------------------------------

setup:
	$(UV) sync --locked

check: lint test

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

test:
	$(UV) run pytest

manifest:
	$(UV) run python -m tools.corpus_manifest

gcp-guard:
	$(UV) run python -m tools.gcp_guard

## ---- implemented at M1 ---------------------------------------------------------------------

# data/index/{chunks.jsonl,bboxes.json,manifest.json} + data/derived/pages/*.png from corpus/.
index:
	$(UV) run python -m app.ingest.build_index

# fixtures/pdf/FX-3.pdf, FX-4.pdf (FX-1, FX-2, FX-5 land at M5).
fixtures:
	$(UV) run python -m fixtures.make_fixtures

## ---- implemented at M2 ---------------------------------------------------------------------

# Corpus vectors for one embedding model (LIVE Vertex call, GCP trial credit, about $0.0003).
# Dry run by default; the owner confirms with: make embed EMBED_MODEL=gemini-embedding-2 CONFIRM=--yes
EMBED_MODEL ?= gemini-embedding-2
CONFIRM ?=
embed: gcp-guard
	$(UV) run python -m app.retrieval.embed_corpus --model $(EMBED_MODEL) $(CONFIRM)

# Retrieval A/B on gold-v1 (ACCEPTANCE §M). Offline by default (BM25, raw questions, replayed cassettes).
RETRIEVAL_CONFIG ?= bm25
RETRIEVAL_QUERIES ?= raw
eval-retrieval:
	$(UV) run python -m eval.run_retrieval --config $(RETRIEVAL_CONFIG) --queries $(RETRIEVAL_QUERIES)

## ---- implemented at M3 ---------------------------------------------------------------------

# Executive report (ADR D24): LIVE Claude Opus 5.5 call, about $0.10-0.20 per language. Dry run by
# default; the owner confirms with: make report REPORT_LANG=en CONFIRM=--yes
# Records the cassette and saves data/reports/executive-<lang>-<key>.json, which ships with the app.
REPORT_LANG ?= en
report: export LLM_MODE := record
report:
	$(UV) run python -m app.pipeline.report --lang $(REPORT_LANG) $(CONFIRM)

# Server for local development: the Vite dev server (web/) proxies /api to it.
run:
	$(UV) run uvicorn app.server:app --host 127.0.0.1 --port 8000

# Live smoke test of a deployed service (LIVE Claude calls, about $0.20-0.40):
#   make smoke URL=https://<service> INVITE=<invite_token>
INVITE ?=
smoke:
	$(UV) run python -m tools.smoke --url $(URL) --invite "$(INVITE)"

# Typeset A4 PDFs of the saved executive reports (local Playwright + Edge; $0).
report-pdf:
	$(UV) run python -m tools.report_pdf --lang all

## ---- stubs (PROJECT_PLAN §7.4 milestone in which each target lands) --------------------------

cost-report eval:
	@echo make $@: not implemented until M3

e2e:
	@echo make $@: not implemented until M4

radar:
	@echo make $@: not implemented until M5


screenshots demo-video release-zip:
	@echo make $@: not implemented until M6b

graph:
	@echo make $@: not implemented until M7
