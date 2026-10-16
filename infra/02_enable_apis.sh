#!/usr/bin/env bash
# Step B (docs/SETUP_ACCOUNTS.md): enable the APIs this project uses, in THIS project only.
# B1 is the list in PROJECT_PLAN §3.6 minus Speech-to-Text and Text-to-Speech, which were removed
# with the Voice pack (ADR-0001 D20). B2 holds the three APIs that Google documents as required for
# step C; it runs only after the owner approves ADR-0001 deviation D10.
source "$(dirname "$0")/_common.sh"
require_almamlaka_config

banner "B1 the 6 APIs of PROJECT_PLAN §3.6 that remain without voice (ADR-0001 D20)"
run gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com logging.googleapis.com --project="${GCP_PROJECT}"

banner "B2 ADR-0001 D10: IAM, IAM Credentials (impersonation) and Resource Manager (project IAM)"
if [[ "${APPROVE_EXTRA_APIS:-0}" == "1" ]]; then
  run gcloud services enable iam.googleapis.com iamcredentials.googleapis.com cloudresourcemanager.googleapis.com --project="${GCP_PROJECT}"
else
  echo "SKIPPED: re-run with APPROVE_EXTRA_APIS=1 once deviation D10 is approved (step C needs these)."
fi

banner "B3 check: APIs enabled in THIS project"
run gcloud services list --enabled --project="${GCP_PROJECT}"
