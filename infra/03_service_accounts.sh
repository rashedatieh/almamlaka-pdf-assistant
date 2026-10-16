#!/usr/bin/env bash
# Step C (docs/SETUP_ACCOUNTS.md): runtime and deployer service accounts with roles on THIS project
# only. No key files are ever created: the owner impersonates the deployer.
# The deployer's roles follow ADR-0001 deviation D12 and run only with APPROVE_DEPLOYER_ROLES=1.
# Safe to re-run: existing service accounts are kept, and role bindings are idempotent.
source "$(dirname "$0")/_common.sh"
require_almamlaka_config
: "${OWNER_EMAIL:?Set OWNER_EMAIL to the Google account that will impersonate the deployer}"

banner "C1 service accounts"
created=0
if exists gcloud iam service-accounts describe "${RUNTIME_SA}" --project="${GCP_PROJECT}"; then
  echo "exists: ${RUNTIME_SA}"
else
  run gcloud iam service-accounts create almamlaka-runtime --display-name="Almamlaka runtime" --description="Cloud Run runtime identity" --project="${GCP_PROJECT}"
  created=1
fi
if exists gcloud iam service-accounts describe "${DEPLOYER_SA}" --project="${GCP_PROJECT}"; then
  echo "exists: ${DEPLOYER_SA}"
else
  run gcloud iam service-accounts create almamlaka-deployer --display-name="Almamlaka deployer" --description="Builds and deploys; impersonated by the owner" --project="${GCP_PROJECT}"
  created=1
fi
if [[ "${APPLY}" == "1" && "${created}" == "1" ]]; then
  echo "Waiting 60 s: Google advises waiting after creating a service account before granting roles."
  sleep 60
fi

banner "C2 the owner may impersonate the deployer (grant on that one service account)"
run gcloud iam service-accounts add-iam-policy-binding "${DEPLOYER_SA}" --member="user:${OWNER_EMAIL}" --role=roles/iam.serviceAccountTokenCreator --project="${GCP_PROJECT}"

banner "C3 runtime role for embeddings (secret access is granted per secret in step F)"
run gcloud projects add-iam-policy-binding "${GCP_PROJECT}" --member="serviceAccount:${RUNTIME_SA}" --role=roles/aiplatform.user

banner "C4 ADR-0001 D12: deployer roles to deploy from source and run the build as itself"
if [[ "${APPROVE_DEPLOYER_ROLES:-0}" == "1" ]]; then
  for role in roles/run.sourceDeveloper roles/run.builder roles/serviceusage.serviceUsageConsumer; do
    run gcloud projects add-iam-policy-binding "${GCP_PROJECT}" --member="serviceAccount:${DEPLOYER_SA}" --role="${role}"
  done
  run gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA}" --member="serviceAccount:${DEPLOYER_SA}" --role=roles/iam.serviceAccountUser --project="${GCP_PROJECT}"
  run gcloud iam service-accounts add-iam-policy-binding "${DEPLOYER_SA}" --member="serviceAccount:${DEPLOYER_SA}" --role=roles/iam.serviceAccountUser --project="${GCP_PROJECT}"
else
  echo "SKIPPED: re-run with APPROVE_DEPLOYER_ROLES=1 once deviation D12 is approved (needed before M6)."
fi
