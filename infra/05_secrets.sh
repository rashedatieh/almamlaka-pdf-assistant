#!/usr/bin/env bash
# Step F (docs/SETUP_ACCOUNTS.md): exactly two Secret Manager secrets, readable only by the runtime
# service account. Secret values never touch disk, shell history, argv or this repository.
#   anthropic-api-key : the key of the Anthropic workspace "almamlaka-assistant" (step E first)
#   app-secrets       : JSON {"invite_token", "session_secret", "canary_token"}, generated here
# Safe to re-run: existing secrets are kept, and a secret that already has a version gets no second
# one (each version counts toward the shared free tier; rotation is a RUNBOOK step at M6).
source "$(dirname "$0")/_common.sh"
require_almamlaka_config
# Never trace this script: with `bash -x` the key would be printed.
{ set +x; } 2>/dev/null

if [[ "${APPLY}" == "1" ]] && ! command -v python >/dev/null 2>&1; then
  echo "REFUSED: python is not on PATH in this shell (step F3 needs it). Nothing was changed." >&2
  exit 2
fi

banner "F1 the two secrets (automatic replication: ADR-0001 D15)"
for name in anthropic-api-key app-secrets; do
  if exists gcloud secrets describe "${name}" --project="${GCP_PROJECT}"; then
    echo "exists: secret ${name}"
  else
    run gcloud secrets create "${name}" --replication-policy=automatic --labels="${LABELS}" --project="${GCP_PROJECT}"
  fi
done

banner "F2 Anthropic API key, typed at a hidden prompt"
# REPLACE_KEY=1 stores a new key even when one exists, then disables the older versions.
if [[ "${REPLACE_KEY:-0}" != "1" ]] && exists gcloud secrets versions describe latest --secret=anthropic-api-key --project="${GCP_PROJECT}"; then
  echo "SKIPPED: anthropic-api-key already has a version (re-run with REPLACE_KEY=1 to replace it)."
elif [[ "${APPLY}" == "1" ]]; then
  old_versions="$(gcloud secrets versions list anthropic-api-key --filter="state=ENABLED" --format="value(name)" --project="${GCP_PROJECT}" 2>/dev/null || true)"
  read -rsp "Paste the API key of workspace almamlaka-assistant, then press Enter: " ANTHROPIC_KEY
  echo
  if [[ -z "${ANTHROPIC_KEY}" ]]; then
    echo "REFUSED: the key is empty; nothing was stored. Re-run this script." >&2
    exit 2
  fi
  # A paste can carry a carriage return or spaces (a stored key with them fails with 401).
  ANTHROPIC_KEY="$(printf '%s' "${ANTHROPIC_KEY}" | tr -d '[:space:]')"
  if [[ "${ANTHROPIC_KEY}" != sk-ant-* ]]; then
    unset ANTHROPIC_KEY
    echo "REFUSED: that does not look like a Claude key (they start with sk-ant-). Nothing was stored." >&2
    exit 2
  fi
  printf '%s' "${ANTHROPIC_KEY}" | gcloud secrets versions add anthropic-api-key --data-file=- --project="${GCP_PROJECT}"
  unset ANTHROPIC_KEY
  for v in ${old_versions}; do
    run gcloud secrets versions disable "${v##*/}" --secret=anthropic-api-key --project="${GCP_PROJECT}"
  done
else
  echo "+ <hidden prompt> | gcloud secrets versions add anthropic-api-key --data-file=- --project=${GCP_PROJECT}"
fi

banner "F3 app-secrets generated with Python's secrets module and piped straight to Secret Manager"
GEN_APP_SECRETS='import json, secrets; print(json.dumps({"invite_token": secrets.token_urlsafe(24), "session_secret": secrets.token_urlsafe(48), "canary_token": "CANARY-" + secrets.token_hex(8)}), end="")'
if exists gcloud secrets versions describe latest --secret=app-secrets --project="${GCP_PROJECT}"; then
  echo "SKIPPED: app-secrets already has a version."
elif [[ "${APPLY}" == "1" ]]; then
  python -I -c "${GEN_APP_SECRETS}" | gcloud secrets versions add app-secrets --data-file=- --project="${GCP_PROJECT}"
else
  echo "+ python -I -c '<generate JSON>' | gcloud secrets versions add app-secrets --data-file=- --project=${GCP_PROJECT}"
fi

banner "F4 the runtime service account may read exactly these two secrets"
for name in anthropic-api-key app-secrets; do
  run gcloud secrets add-iam-policy-binding "${name}" --member="serviceAccount:${RUNTIME_SA}" --role=roles/secretmanager.secretAccessor --project="${GCP_PROJECT}"
done
