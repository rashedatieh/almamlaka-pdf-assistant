# SETUP_ACCOUNTS — account setup run by the owner

Run by: **the project owner**. (docs/ENGINEERING_RULES.md, "Operating constraints").
Written: 2026-10-15, milestone M0. Every command and flag below was checked against Google's and Anthropic's
official pages that day. The sources are in [`adr/0001-stack-and-models.md`](adr/0001-stack-and-models.md).

## Rules for every step

- **One project only.** Every command names the new dedicated project `$GCP_PROJECT` explicitly. Most use
  `--project`. These forms are the documented exceptions:
  - `projects create`, `projects add-iam-policy-binding`, `projects get-iam-policy` and
    `billing projects link` take the project as a positional argument.
  - A budget is filtered with `--filter-projects=projects/$GCP_PROJECT`.
  - `gcloud config …` lines read or change only your local `almamlaka` configuration, and `gcloud auth list`
    only shows your local credentials.
  `tests/unit/test_infra_static.py` (ACCEPTANCE_TESTS Q-06) enforces these rules on this file and on `infra/`.
- **Never run** `gcloud projects list`, `gcloud organizations …`, `gcloud billing accounts …`, or
  `gcloud config configurations activate`. Never set the project of any other configuration. Copy the billing
  account ID from the Console instead of listing billing accounts.
- **Scripts are dry runs by default.** Each script prints its exact commands. Read them, then re-run with
  `APPLY=1` to execute. Run the scripts in **Git Bash** from the repository root, using the gcloud CLI already
  installed on this PC.
- **Label guard.** Step A labels the new project `app=almamlaka-assistant`. Every later step, and
  `make gcp-guard`, refuses to run unless the `almamlaka` configuration points at `$GCP_PROJECT` **and** that
  project carries this label. Your other projects don't have the label (unless you add it), so a mistyped
  project ID cannot reach them.
- **Safe to re-run.** If a step fails halfway, fix the cause and run the same script again. With `APPLY=1`
  each script first checks, read-only, whether a configuration, project, service account, repository or
  secret already exists, and skips creating it.
- **Two choices that change the plan need your approval first** (the D-numbers are deviations listed in ADR-0001):
  - **D10 (extra APIs):** three APIs that Google documents as required for step C. They are gated behind
    `APPROVE_EXTRA_APIS=1`.
  - **D12 (deployer roles):** the role set for the deployer service account. Gated behind
    `APPROVE_DEPLOYER_ROLES=1`.

## Step 0 — choose values (nothing touches Google yet)

1. In the Console, open **Billing → Account management** for the trial billing account. Copy the
   **billing account ID** (format `XXXXXX-XXXXXX-XXXXXX`).
2. On **Billing → Overview**, note the **trial end date** and the remaining credit. PROJECT_PLAN §9 needs both.
3. Pick a project ID once and keep it. It must be 6–30 characters of lowercase letters, digits and hyphens,
   start with a letter, and not end with a hyphen. Don't create the project in the Console: step A creates
   and labels it, and refuses an existing project that lacks the label.

```bash
cd "/c/Users/USER/Desktop/Almamlaka TV/almamlaka-pdf-assistant"
export GCP_PROJECT=getai-almamlaka-assist-XXXX        # choose the suffix once; never reuse another project's ID
export OWNER_EMAIL=you@example.com                     # Google account that owns the trial billing account
export BILLING_ACCOUNT_ID=XXXXXX-XXXXXX-XXXXXX         # copied from Billing > Account management
export GCP_REGION=me-central1
gcloud auth list                                       # local only: OWNER_EMAIL must be listed as credentialed
```

Then create a local `.env` (git-ignored) containing `GCP_PROJECT=<your project ID>`, so that
`make gcp-guard` and the scripts in later milestones can find it.

## Step A — configuration, project, billing link (`infra/01_project_and_config.sh`)

```bash
bash infra/01_project_and_config.sh            # dry run: review the printed commands
APPLY=1 bash infra/01_project_and_config.sh    # execute
```

Commands it runs, in order (with `APPLY=1`, a create is skipped when the read-only check shows the
configuration or project already exists):

```bash
env -u CLOUDSDK_ACTIVE_CONFIG_NAME gcloud config configurations describe almamlaka
env -u CLOUDSDK_ACTIVE_CONFIG_NAME gcloud config configurations create almamlaka --no-activate
gcloud config set account "${OWNER_EMAIL}" --configuration=almamlaka
gcloud projects describe "${GCP_PROJECT}"
gcloud projects create "${GCP_PROJECT}" --name="Almamlaka Assistant" --labels="app=almamlaka-assistant,owner=rashed-atieh"
gcloud billing projects link "${GCP_PROJECT}" --billing-account="${BILLING_ACCOUNT_ID}"
gcloud config set project "${GCP_PROJECT}" --configuration=almamlaka
gcloud config set run/region "${GCP_REGION}" --configuration=almamlaka
gcloud config set artifacts/location "${GCP_REGION}" --configuration=almamlaka
gcloud config get project --configuration=almamlaka
```

- **What A does:** the `almamlaka` configuration is created **without activating it**. Your current default
  configuration, and your other projects, stay exactly as they are. Our scripts and the Makefile select
  `almamlaka` per command through `CLOUDSDK_ACTIVE_CONFIG_NAME`.
- **The configuration gets its project last,** after the project exists. If `$GCP_PROJECT` names an existing
  project without the label `app=almamlaka-assistant`, for example one of your other bots, the script stops
  with `REFUSED` before anything points at it.
- **If `gcloud auth list` did not show `OWNER_EMAIL`:** run `gcloud auth login --configuration=almamlaka`,
  then run the script again.
- **If the billing link fails:** link it in the Console instead, under **Billing → Account management →
  Projects linked to this billing account → Change billing** for this project only.
- **Check:** `make gcp-guard` must print `ok - configuration 'almamlaka' -> project '<your ID>'`.

## Step B — APIs (`infra/02_enable_apis.sh`)

```bash
bash infra/02_enable_apis.sh                                   # dry run
APPROVE_EXTRA_APIS=1 APPLY=1 bash infra/02_enable_apis.sh      # execute, after approving D10
```

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com logging.googleapis.com --project="${GCP_PROJECT}"
gcloud services enable iam.googleapis.com iamcredentials.googleapis.com cloudresourcemanager.googleapis.com --project="${GCP_PROJECT}"
gcloud services list --enabled --project="${GCP_PROJECT}"
```

The first command enables the 6 APIs of PROJECT_PLAN §3.6 that remain after the Voice pack was removed
(ADR-0001 D20). Speech-to-Text and Text-to-Speech are **not** enabled. The second is **D10**: Google
documents these three as required for step C:
- `iam` to create service accounts;
- `iamcredentials` for impersonation;
- `cloudresourcemanager` for project IAM bindings.

A new project also comes with about 23 Google default services already enabled (Logging, Monitoring, BigQuery,
Cloud Storage and others). Leave them on: source deploys stage code in Cloud Storage.

## Step C — service accounts, no key files (`infra/03_service_accounts.sh`)

```bash
bash infra/03_service_accounts.sh
APPROVE_DEPLOYER_ROLES=1 APPLY=1 bash infra/03_service_accounts.sh     # after approving D12
```

Without `APPROVE_DEPLOYER_ROLES=1`, the script creates both accounts and the runtime roles and skips the
deployer's roles (the last five commands below). The deployer isn't needed before M6.

```bash
gcloud iam service-accounts create almamlaka-runtime --display-name="Almamlaka runtime" --description="Cloud Run runtime identity" --project="${GCP_PROJECT}"
gcloud iam service-accounts create almamlaka-deployer --display-name="Almamlaka deployer" --description="Builds and deploys; impersonated by the owner" --project="${GCP_PROJECT}"
gcloud iam service-accounts add-iam-policy-binding "almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com" --member="user:${OWNER_EMAIL}" --role=roles/iam.serviceAccountTokenCreator --project="${GCP_PROJECT}"
gcloud projects add-iam-policy-binding "${GCP_PROJECT}" --member="serviceAccount:almamlaka-runtime@${GCP_PROJECT}.iam.gserviceaccount.com" --role=roles/aiplatform.user
gcloud projects add-iam-policy-binding "${GCP_PROJECT}" --member="serviceAccount:almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com" --role=roles/run.sourceDeveloper
gcloud projects add-iam-policy-binding "${GCP_PROJECT}" --member="serviceAccount:almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com" --role=roles/run.builder
gcloud projects add-iam-policy-binding "${GCP_PROJECT}" --member="serviceAccount:almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com" --role=roles/serviceusage.serviceUsageConsumer
gcloud iam service-accounts add-iam-policy-binding "almamlaka-runtime@${GCP_PROJECT}.iam.gserviceaccount.com" --member="serviceAccount:almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com" --role=roles/iam.serviceAccountUser --project="${GCP_PROJECT}"
gcloud iam service-accounts add-iam-policy-binding "almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com" --member="serviceAccount:almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com" --role=roles/iam.serviceAccountUser --project="${GCP_PROJECT}"
```

| Identity | Roles (all on this project only) | Why |
|---|---|---|
| **Runtime SA** | Agent Platform User (`roles/aiplatform.user`) | Embeddings |
| | Secret accessor on each of the 2 secrets | Granted in step F |
| **Deployer SA** | `run.sourceDeveloper` | Google's documented role set for source deploys (D12) |
| | `run.builder` | The deployer is also the build identity, so no third service account is needed |
| | Service Usage Consumer | Part of the same documented set |
| | Service Account User on the runtime SA and on itself | Deploy as the runtime SA; run builds as itself |
| **You (owner)** | Token Creator on the deployer SA only | Impersonation instead of key files |

- **Impersonation is used per command**, starting at M6:
  `--impersonate-service-account="almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com"`. It is not set
  globally, so your own owner commands in steps D–G keep working.
- **Making the service public** needs `run.services.setIamPolicy`, which the deployer doesn't have (D12). At M6,
  after the first deploy, you grant public invoker access once yourself. That step will be in `RUNBOOK.md`.

## Step D — Artifact Registry with keep-last-2 cleanup (`infra/04_artifact_registry.sh`)

```bash
bash infra/04_artifact_registry.sh
APPLY=1 bash infra/04_artifact_registry.sh
```

```bash
gcloud artifacts repositories create almamlaka --repository-format=docker --location="${GCP_REGION}" --description="Almamlaka assistant images" --labels="app=almamlaka-assistant,owner=rashed-atieh" --project="${GCP_PROJECT}"
gcloud artifacts repositories set-cleanup-policies almamlaka --location="${GCP_REGION}" --policy=infra/cleanup_policy.json --no-dry-run --project="${GCP_PROJECT}"
```

- **How the policy keeps 2:** [`infra/cleanup_policy.json`](../infra/cleanup_policy.json) holds a Delete rule for
  every version and a Keep rule for the 2 most recent versions. Keep wins over Delete, so only the newest 2 stay.
- **Deletion is switched on explicitly** with `--no-dry-run`. Google's cleanup-policy page documents this flag.
  The command's reference page doesn't say what happens when neither `--dry-run` nor `--no-dry-run` is given.
- **Timing:** Google applies policy changes within about a day.
- **The policy only covers images built into this repository.** Plain `gcloud run deploy --source` would push to
  an auto-created `cloud-run-source-deploy` repository instead. M6 deploys with
  `--image=me-central1-docker.pkg.dev/$GCP_PROJECT/almamlaka/...` to keep images here (D11).

## Step E — Anthropic Console (manual)

1. In the Claude Console, open **Workspaces** and create the workspace **`almamlaka-assistant`**. Spend and rate
   limits cannot be set on the Default workspace.
2. Set that workspace's **spend limit to $20 per month**.
3. On the **Rate limits** page, choose the workspace and set limits below the organisation's limits. Suggested
   values (my suggestion; the plan gives none):
   - 30 requests per minute
   - 100,000 input tokens per minute
   - 20,000 output tokens per minute
   Rate limits are per model, so set them for the two models the app calls (decision D19): **Sonnet 5.5**
   (chat) and **Opus 5.5** (Executive report).
4. The inference geo is **global** (decision D1). Optionally set the workspace's `default_inference_geo` to
   `global` to match `INFERENCE_GEO`.
5. Create an **API key in the `almamlaka-assistant` workspace**:
   - Copy it once.
   - Paste it only at the hidden prompt in step F.
   - Never paste it into `.env`, a chat or a file.
   - Your other projects must never use this key.
6. Turn auto-reload off:
   - Open **Billing → Credit balance → Manage auto-reload → Turn off**, then confirm with **Turn off** again.
   - The docs don't say whether this setting is per workspace or for the whole organisation. That is fine
     here: the owner's other projects use a different Anthropic organisation (owner, 2026-10-15).
   - Prepaid credits expire one year after purchase.
7. Save screenshots of the workspace limits and of auto-reload OFF in `docs/evidence/` (ACCEPTANCE_TESTS Q-08).
   Make sure no key is visible in them.

## Step F — exactly two secrets (`infra/05_secrets.sh`)

Do step E first, so the API key exists.

```bash
bash infra/05_secrets.sh
APPLY=1 bash infra/05_secrets.sh       # asks for the API key at a hidden prompt
```

These lines run **inside the script only. Don't paste them into a terminal:** typing the key on a command
line puts it in your shell history. If the script stops partway, run it again. It keeps existing secrets,
and it never adds a second version to a secret that already has one.

```bash
gcloud secrets create anthropic-api-key --replication-policy=automatic --labels="app=almamlaka-assistant,owner=rashed-atieh" --project="${GCP_PROJECT}"
gcloud secrets create app-secrets --replication-policy=automatic --labels="app=almamlaka-assistant,owner=rashed-atieh" --project="${GCP_PROJECT}"
printf '%s' "${ANTHROPIC_KEY}" | gcloud secrets versions add anthropic-api-key --data-file=- --project="${GCP_PROJECT}"
python -I -c "${GEN_APP_SECRETS}" | gcloud secrets versions add app-secrets --data-file=- --project="${GCP_PROJECT}"
gcloud secrets add-iam-policy-binding anthropic-api-key --member="serviceAccount:almamlaka-runtime@${GCP_PROJECT}.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor --project="${GCP_PROJECT}"
gcloud secrets add-iam-policy-binding app-secrets --member="serviceAccount:almamlaka-runtime@${GCP_PROJECT}.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor --project="${GCP_PROJECT}"
```

- **What `app-secrets` holds:** JSON with three fields: `invite_token`, `session_secret` and `canary_token`. The
  script generates it with Python's `secrets` module and pipes it straight to Secret Manager, so nothing is
  written to disk.
- **When you need the invite token (M6):** read it back with
  `gcloud secrets versions access latest --secret=app-secrets --project="${GCP_PROJECT}"`.
- **Replication is automatic** (D15). Cloud Run cannot use regional secrets, and Google's docs don't confirm
  `me-central1` for user-managed replication.
- **The free tier is shared.** Secret Manager's free tier (6 active versions per month) is counted per **billing
  account**, so your other two projects use the same allowance. Only you can check their usage, under
  **Billing → Reports**, filtered by service "Secret Manager".

## Step G — $25 budget and Spend Caps

**Budget: Console route (preferred; needs no extra API).**

1. Open **Billing → Budgets & alerts → Create budget**.
2. Name: `almamlaka-assistant-25usd`.
3. Scope:
   - Projects: **only this project**.
   - Services: all.
   - **Savings / credits: clear every option, including Promotions.** Otherwise the trial credit nets the spend
     to about $0 and the alerts never fire (D13).
4. Amount: **Specified amount, $25 per month.** The currency must match the billing account's currency.
5. Actions: alert thresholds at **50%, 80% and 100%** of actual spend. The Console's defaults are 50/90/100, so
   change 90 to 80. Email the billing admins.
6. Click **Finish**.

**Budget: CLI route (`infra/06_budget_cli.sh`, only if you approve D10 for the Budget API).**

```bash
APPROVE_BUDGET_API=1 bash infra/06_budget_cli.sh
APPROVE_BUDGET_API=1 APPLY=1 bash infra/06_budget_cli.sh
```

```bash
gcloud services enable billingbudgets.googleapis.com --project="${GCP_PROJECT}"
gcloud billing budgets create --billing-account="${BILLING_ACCOUNT_ID}" --display-name="almamlaka-assistant-25usd" --budget-amount=25USD --calendar-period=month --filter-projects="projects/${GCP_PROJECT}" --credit-types-treatment=exclude-all-credits --threshold-rule=percent=0.5 --threshold-rule=percent=0.8 --threshold-rule=percent=1.0 --billing-project="${GCP_PROJECT}"
```

**Spend Caps (Public Preview; Console only; D14).**

- **How to create one:** open **Billing → Budgets & alerts → Create budget → Spend cap enforcement**. Choose this
  project and **one** service, set the monthly amount, then click **Finish**.
- **Create two caps:**
  - **Cloud Run**, suggested $5 per month
  - **Agent Platform (formerly Vertex AI)**, suggested $5 per month
  Expected use of both is near $0, so these amounts are my suggestion; adjust as you see fit.
- **What the cap does:** it pauses new usage of that service until you lift the cap or the next month starts. It
  counts cost **before** credits, so it works during the trial.
- **Speech-to-Text and Text-to-Speech, which caps don't cover, are not used:** the Voice pack was removed
  (ADR-0001 D20).
- **Required role:** Billing Account Administrator, or Billing Account Costs Manager plus project Editor.
- **Free-trial eligibility is not documented.** If the trial account doesn't offer "Spend cap enforcement",
  record "Spend Caps not available on trial account (2026-10-15)" in `docs/evidence/` (ACCEPTANCE_TESTS Q-09).

## Step H — verify (`infra/07_verify.sh`, read-only)

```bash
APPLY=1 bash infra/07_verify.sh > docs/evidence/gcp-verify.txt
```

Commands it runs, in order:

```bash
# H1 configuration
gcloud config get project --configuration=almamlaka
# H2 enabled APIs
gcloud services list --enabled --project="${GCP_PROJECT}"
# H3 project roles of the two service accounts; H3b the Compute Engine default service account
gcloud projects get-iam-policy "${GCP_PROJECT}" --flatten="bindings[].members" --filter="bindings.members:almamlaka-" --format="table(bindings.role,bindings.members)"
gcloud projects get-iam-policy "${GCP_PROJECT}" --flatten="bindings[].members" --filter="bindings.members:compute@developer.gserviceaccount.com" --format="table(bindings.role,bindings.members)"
# H4 secrets and who may read them
gcloud secrets list --project="${GCP_PROJECT}" --format="value(name)"
gcloud secrets get-iam-policy anthropic-api-key --project="${GCP_PROJECT}"
gcloud secrets get-iam-policy app-secrets --project="${GCP_PROJECT}"
# H5 who may impersonate the deployer; keys on both service accounts
gcloud iam service-accounts get-iam-policy "almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com" --project="${GCP_PROJECT}"
gcloud iam service-accounts keys list --iam-account="almamlaka-runtime@${GCP_PROJECT}.iam.gserviceaccount.com" --project="${GCP_PROJECT}"
gcloud iam service-accounts keys list --iam-account="almamlaka-deployer@${GCP_PROJECT}.iam.gserviceaccount.com" --project="${GCP_PROJECT}"
# H6 Artifact Registry repository and cleanup policy
gcloud artifacts repositories describe almamlaka --location="${GCP_REGION}" --project="${GCP_PROJECT}"
```

Expected results (ACCEPTANCE_TESTS Q-09):

| Check | Expected |
|---|---|
| Secrets | exactly 2 (`anthropic-api-key`, `app-secrets`); each grants `secretAccessor` to the runtime SA only |
| Service-account keys | `keys list` shows no user-managed keys on either SA |
| Deployer impersonation | only you hold Token Creator on the deployer |
| Artifact Registry | the `almamlaka` repository has the 2 cleanup rules |
| Compute Engine default SA | Section H3b shows it. Google creates it automatically and may grant it Editor; we don't use it. Whether to remove that grant is an open question in ADR D12. |
| Console | the budget (and Spend Caps, or "not available") are visible |

The output contains no secret values. It does contain **your Google account e-mail** (the Token Creator
binding on the deployer), and a committed file ends up in the source zip sent to Almamlaka TV. Review
`docs/evidence/gcp-verify.txt` before committing it. You can replace the e-mail with `user:<owner>`.

## Step I — record the values

Record:
- the project ID;
- whether D10 and D12 are approved and applied;
- whether Spend Caps were available;
- the trial end date;
- any errors you hit.
