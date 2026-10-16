#!/usr/bin/env bash
# Step A (docs/SETUP_ACCOUNTS.md): create the pinned gcloud configuration "almamlaka", the NEW
# dedicated project, and link that project (only) to the trial billing account.
# Needs: GCP_PROJECT, OWNER_EMAIL, BILLING_ACCOUNT_ID (copied from the Console; never listed by CLI).
# The configuration is pointed at the project only after the project exists and carries our label,
# so a mistyped ID that belongs to another project is refused before anything is bound to it.
source "$(dirname "$0")/_common.sh"
: "${OWNER_EMAIL:?Set OWNER_EMAIL to the Google account that owns the trial billing account}"
: "${BILLING_ACCOUNT_ID:?Copy it from Console > Billing > Account management (do not list accounts)}"

banner "A1 configuration 'almamlaka' (created without activating it; no project set yet)"
# Run with CLOUDSDK_ACTIVE_CONFIG_NAME unset: Google does not document how gcloud behaves when that
# variable names a configuration that does not exist yet. This step is local only.
if exists env -u CLOUDSDK_ACTIVE_CONFIG_NAME gcloud config configurations describe almamlaka; then
  echo "exists: configuration 'almamlaka' (not created again)"
else
  run env -u CLOUDSDK_ACTIVE_CONFIG_NAME gcloud config configurations create almamlaka --no-activate
fi
run gcloud config set account "${OWNER_EMAIL}" --configuration=almamlaka

banner "A2 the new dedicated project"
if exists gcloud projects describe "${GCP_PROJECT}"; then
  if [[ "$(project_app_label)" != "${APP_LABEL}" ]]; then
    echo "REFUSED: project '${GCP_PROJECT}' already exists and is not labelled app=${APP_LABEL}." >&2
    echo "It is another project. Check the ID chosen in docs/SETUP_ACCOUNTS.md step 0." >&2
    exit 2
  fi
  echo "exists: project ${GCP_PROJECT}, labelled app=${APP_LABEL} (not created again)"
else
  run gcloud projects create "${GCP_PROJECT}" --name="Almamlaka Assistant" --labels="${LABELS}"
fi

banner "A3 link THIS project to the trial billing account"
run gcloud billing projects link "${GCP_PROJECT}" --billing-account="${BILLING_ACCOUNT_ID}"

banner "A4 point the configuration at the new project"
run gcloud config set project "${GCP_PROJECT}" --configuration=almamlaka
run gcloud config set run/region "${GCP_REGION}" --configuration=almamlaka
run gcloud config set artifacts/location "${GCP_REGION}" --configuration=almamlaka

banner "A5 check: must print ${GCP_PROJECT}"
run gcloud config get project --configuration=almamlaka
