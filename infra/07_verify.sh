#!/usr/bin/env bash
# Step H (docs/SETUP_ACCOUNTS.md): read-only checks of THIS project for ACCEPTANCE_TESTS Q-09.
# Every command reads this project only; budgets and Spend Caps are checked in the Console.
source "$(dirname "$0")/_common.sh"
require_almamlaka_config

banner "H1 configuration 'almamlaka' -> ${GCP_PROJECT}"
run gcloud config get project --configuration=almamlaka

banner "H2 enabled APIs"
run gcloud services list --enabled --project="${GCP_PROJECT}"

banner "H3 project-level roles held by the two service accounts"
run gcloud projects get-iam-policy "${GCP_PROJECT}" --flatten="bindings[].members" --filter="bindings.members:almamlaka-" --format="table(bindings.role,bindings.members)"

banner "H3b roles of the Compute Engine default service account (created by Google; unused here)"
run gcloud projects get-iam-policy "${GCP_PROJECT}" --flatten="bindings[].members" --filter="bindings.members:compute@developer.gserviceaccount.com" --format="table(bindings.role,bindings.members)"

banner "H4 exactly two secrets, each readable by the runtime service account"
run gcloud secrets list --project="${GCP_PROJECT}" --format="value(name)"
for name in anthropic-api-key app-secrets; do
  run gcloud secrets get-iam-policy "${name}" --project="${GCP_PROJECT}"
done

banner "H5 who may impersonate the deployer; no user-managed keys on either account"
run gcloud iam service-accounts get-iam-policy "${DEPLOYER_SA}" --project="${GCP_PROJECT}"
for sa in "${RUNTIME_SA}" "${DEPLOYER_SA}"; do
  run gcloud iam service-accounts keys list --iam-account="${sa}" --project="${GCP_PROJECT}"
done

banner "H6 Artifact Registry repository and its cleanup policy"
run gcloud artifacts repositories describe almamlaka --location="${GCP_REGION}" --project="${GCP_PROJECT}"
