#!/usr/bin/env bash
# Deploy (PROJECT_PLAN §7.5 step 7): build from source with the deployer as build identity (D12), push to
# the 'almamlaka' repository with keep-2 cleanup (D11), run as the runtime service account with the two
# secrets. Flags checked against Google's docs (ADR-0001 §3 row 2; [RUN-BSA] for --build-service-account).
# Dry run by default: APPLY=1 executes. Every command names THIS project only (label-guarded).
source "$(dirname "$0")/_common.sh"
require_almamlaka_config

SERVICE="${SERVICE:-almamlaka-assistant}"
DAILY_BUDGET_USD="${DAILY_BUDGET_USD:-2.00}"
IMAGE="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/almamlaka/${SERVICE}"
cd "${INFRA_DIR}/.."

banner "G0 the build runs on Cloud Build (free tier); the image needs the saved index"
if [[ ! -f data/index/chunks.jsonl ]]; then
  echo "REFUSED: data/index/chunks.jsonl is missing; run make index first." >&2
  exit 2
fi
ls data/reports/executive-*.json 2>/dev/null || echo "note: no saved executive report yet (make report); the button shows the outline"

banner "G1 build and deploy ${SERVICE} as the deployer (impersonated), private until G2"
run gcloud run deploy "${SERVICE}" --project="${GCP_PROJECT}" --region="${GCP_REGION}" \
  --source . --image="${IMAGE}" \
  --build-service-account="projects/${GCP_PROJECT}/serviceAccounts/${DEPLOYER_SA}" \
  --impersonate-service-account="${DEPLOYER_SA}" \
  --service-account="${RUNTIME_SA}" \
  --set-secrets="ANTHROPIC_API_KEY=anthropic-api-key:latest,APP_SECRETS=app-secrets:latest" \
  --set-env-vars="APP_ENV=prod,LLM_MODE=live,INFERENCE_GEO=global,DAILY_BUDGET_USD=${DAILY_BUDGET_USD},RATE_LIMIT_PER_MIN=10,MAX_TURNS_PER_SESSION=30,INVITE_REQUIRED=${INVITE_REQUIRED:-false}" \
  --min-instances=0 --max-instances=1 --concurrency=40 --cpu=1 --memory=1Gi --timeout=300 \
  --labels="${LABELS}" --no-allow-unauthenticated --quiet

banner "G2 public access (your own account: the deployer cannot change IAM, D12). The app keeps its invite gate"
run gcloud run services add-iam-policy-binding "${SERVICE}" --project="${GCP_PROJECT}" --region="${GCP_REGION}" \
  --member=allUsers --role=roles/run.invoker

banner "G3 service URL"
run gcloud run services describe "${SERVICE}" --project="${GCP_PROJECT}" --region="${GCP_REGION}" --format="value(status.url)"
echo "Reviewer link: <URL>/?invite=<invite_token>. Read the token yourself with:"
echo "  gcloud secrets versions access latest --secret=app-secrets --project=${GCP_PROJECT}"
