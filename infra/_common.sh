#!/usr/bin/env bash
# Shared preamble for infra/*.sh. It is sourced by each step script; never run it directly.
#
# Safety rules (docs/ENGINEERING_RULES.md "Operating constraints"; PROJECT_PLAN §3.6):
#   * Only the dedicated project in GCP_PROJECT is ever addressed. Every gcloud command passes it
#     explicitly (--project, or the documented positional project argument).
#   * Every gcloud call runs under the "almamlaka" configuration.
#   * DRY RUN by default: commands are printed, not executed. Re-run with APPLY=1 to execute.
#   * Nothing here lists projects, organizations or billing accounts.
# These scripts are run by the project owner (docs/SETUP_ACCOUNTS.md), never by CI.
set -euo pipefail

: "${GCP_PROJECT:?Set GCP_PROJECT to the NEW dedicated project ID (docs/SETUP_ACCOUNTS.md step 0)}"
if [[ ! "${GCP_PROJECT}" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
  echo "REFUSED: GCP_PROJECT='${GCP_PROJECT}' is not a valid project ID." >&2
  exit 2
fi
if [[ -n "${CLOUDSDK_CORE_PROJECT:-}" && "${CLOUDSDK_CORE_PROJECT}" != "${GCP_PROJECT}" ]]; then
  echo "REFUSED: CLOUDSDK_CORE_PROJECT=${CLOUDSDK_CORE_PROJECT} would override the project; unset it." >&2
  exit 2
fi
export CLOUDSDK_ACTIVE_CONFIG_NAME=almamlaka

APPLY="${APPLY:-0}"
GCP_REGION="${GCP_REGION:-me-central1}"
# Step A labels the new project app=almamlaka-assistant. Later steps refuse any project without it,
# so a mistyped ID can never reach one of the owner's other projects.
APP_LABEL="almamlaka-assistant"
LABELS="app=${APP_LABEL},owner=rashed-atieh"
RUNTIME_SA="almamlaka-runtime@${GCP_PROJECT}.iam.gserviceaccount.com"
DEPLOYER_SA="almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com"
INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Print a command; execute it only when APPLY=1.
run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  if [[ "${APPLY}" == "1" ]]; then
    "$@"
  fi
}

banner() {
  printf '\n== %s ==\n' "$*"
}

# True only when APPLY=1 and the given read-only command succeeds, i.e. the resource already exists.
# Lets a step be re-run after a partial failure. Dry runs never call gcloud and print every create.
exists() {
  [[ "${APPLY}" == "1" ]] || return 1
  "$@" >/dev/null 2>&1
}

# The app label of GCP_PROJECT (reads that project only); empty if it is missing or unreadable.
project_app_label() {
  gcloud projects describe "${GCP_PROJECT}" --format="value(labels.app)" 2>/dev/null || true
}

# Refuse unless the "almamlaka" configuration points at GCP_PROJECT and that project carries the
# label set in step A (the same rules as tools/gcp_guard.py). Every step after 01 calls this; it is
# skipped in dry runs.
require_almamlaka_config() {
  [[ "${APPLY}" == "1" ]] || return 0
  local active label
  active="$(gcloud config get project --configuration=almamlaka 2>/dev/null || true)"
  if [[ "${active}" != "${GCP_PROJECT}" ]]; then
    echo "REFUSED: configuration 'almamlaka' points at '${active:-<unset>}', expected '${GCP_PROJECT}'." >&2
    echo "Run infra/01_project_and_config.sh first (docs/SETUP_ACCOUNTS.md step A)." >&2
    exit 2
  fi
  label="$(project_app_label)"
  if [[ "${label}" != "${APP_LABEL}" ]]; then
    echo "REFUSED: project '${GCP_PROJECT}' is not labelled app=${APP_LABEL}, so it is not the project created in step A." >&2
    exit 2
  fi
}

if [[ "${APPLY}" == "1" ]]; then
  echo "APPLY=1: commands below are EXECUTED against project ${GCP_PROJECT}."
else
  echo "DRY RUN: commands are printed only. Re-run with APPLY=1 to execute them."
fi
