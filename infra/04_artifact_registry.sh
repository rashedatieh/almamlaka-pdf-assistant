#!/usr/bin/env bash
# Step D (docs/SETUP_ACCOUNTS.md): Docker repository "almamlaka" with a keep-last-2 cleanup policy.
# Keep wins over Delete, so the pair of rules in cleanup_policy.json deletes everything except the
# two most recent versions. Google applies policy changes within about a day.
source "$(dirname "$0")/_common.sh"
require_almamlaka_config

banner "D1 Docker repository 'almamlaka' in ${GCP_REGION}"
if exists gcloud artifacts repositories describe almamlaka --location="${GCP_REGION}" --project="${GCP_PROJECT}"; then
  echo "exists: repository almamlaka (not created again)"
else
  run gcloud artifacts repositories create almamlaka --repository-format=docker --location="${GCP_REGION}" --description="Almamlaka assistant images" --labels="${LABELS}" --project="${GCP_PROJECT}"
fi

# --no-dry-run is passed explicitly: Google's reference page for this command states no default.
banner "D2 cleanup policy with deletion ON (--no-dry-run)"
run gcloud artifacts repositories set-cleanup-policies almamlaka --location="${GCP_REGION}" --policy="${INFRA_DIR}/cleanup_policy.json" --no-dry-run --project="${GCP_PROJECT}"
