#!/usr/bin/env bash
# Step G, CLI alternative (docs/SETUP_ACCOUNTS.md). The Console route in step G is preferred: it
# needs no extra API. This script enables billingbudgets.googleapis.com in THIS project (ADR-0001
# deviation D10) and creates a $25 budget filtered to THIS project, measured BEFORE credits, so the
# trial credit cannot hide spend (D13). Spend Caps have no documented CLI: use the Console (D14).
source "$(dirname "$0")/_common.sh"
require_almamlaka_config
: "${BILLING_ACCOUNT_ID:?Copy it from Console > Billing > Account management (do not list accounts)}"

if [[ "${APPROVE_BUDGET_API:-0}" != "1" ]]; then
  echo "SKIPPED: prefer the Console steps (docs/SETUP_ACCOUNTS.md step G)."
  echo "To use this CLI route instead, approve deviation D10 and re-run with APPROVE_BUDGET_API=1."
  exit 0
fi

banner "G1 Cloud Billing Budget API in THIS project (quota project for the budget call)"
run gcloud services enable billingbudgets.googleapis.com --project="${GCP_PROJECT}"

banner "G2 \$25/month budget on THIS project only, alerts at 50/80/100%, credits excluded"
run gcloud billing budgets create --billing-account="${BILLING_ACCOUNT_ID}" --display-name="almamlaka-assistant-25usd" --budget-amount=25USD --calendar-period=month --filter-projects="projects/${GCP_PROJECT}" --credit-types-treatment=exclude-all-credits --threshold-rule=percent=0.5 --threshold-rule=percent=0.8 --threshold-rule=percent=1.0 --billing-project="${GCP_PROJECT}"
