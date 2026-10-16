# LastMile — from disaster alert to confirmed safety

When a flood alert is issued, LastMile finds every vulnerable resident in the alert zone, ranks them by risk,
checks on each one in their own language, and takes the next step (shelter, a volunteer, next-of-kin, or a human
coordinator) until every person is **confirmed safe** or **handed to a human**.

Built for the Google Cloud AI Builder Cup 2026 (theme: Sustainability & Social Impact).
All data is synthetic. No real residents, names, phone numbers or addresses.

|                         |                                                     |
| ----------------------- | --------------------------------------------------- |
| Spec                    | [docs/PRD.md](docs/PRD.md) (single source of truth) |
| How it works (simple)   | [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)        |
| Architecture            | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)        |
| Work board              | [docs/BACKLOG.md](docs/BACKLOG.md)                  |
| How to contribute       | [CONTRIBUTING.md](CONTRIBUTING.md)                  |
| Design decisions        | [docs/DECISIONS.md](docs/DECISIONS.md)              |
| Free-tier budget        | [docs/COSTS.md](docs/COSTS.md)                      |
| Demo URL / video / deck | _added at M7_                                       |

## Status

Phase 1 MVP, milestones **M0–M2 done**, **M3 built** (decision engine, validator, agent log, case drawer) **M4 built** (live call: text
chat and Gemini Live voice) and **M5 built** (approve/reject, overrides, SITREP). Next up: verify real Gemini +
Live with the project key, deploy, then M6 (evals, metrics, deck, video).

## Quickstart (local, no cloud account or API key needed)

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 22+, Java 21 (for the Firestore emulator), GNU make.

```bash
make setup     # install backend + frontend deps, create local .env files
make dev       # emulators + seed + API (:8000) + web (:5173)
```

Open <http://127.0.0.1:5173>, enter the passcode from `backend/.env` (`DEMO_PASSCODE`), press
**Run Flood Scenario**. Emulator UI: <http://127.0.0.1:4000>.

Prefer separate terminals? `make emulators`, then `make seed`, `make api`, `make web`.

```bash
make test      # backend unit + scenario tests (emulator) + frontend tests
make lint      # ruff, tsc, prettier, generated-types check
make help      # everything else
```

## How it works (one paragraph)

FastAPI on Cloud Run holds an in-process job worker. Starting a scenario creates one **case** per at-risk resident,
ranked by a deterministic risk score. A **pump** starts check-ins in priority order (max 8 at once). Each check-in is
a simulated or live call; a **classifier** turns the transcript into a status. The **dispatcher** decides the next
action (Gemini structured output from M3, with a deterministic **fallback policy** that can finish any case on its
own). Every status change goes through one function, `transition_case()`, which enforces the state machine and
writes an audit event. The React console reads Firestore live; REST is used for commands only.

## Repository layout

```
backend/   FastAPI app (app/), tests (unit, scenario), scripts/export_types.py
frontend/  React 18 + Vite + Tailwind console; src/types.gen.ts is generated from backend models
seed/      Synthetic data generator + committed JSON + Firestore loader
infra/     firebase.json, Firestore rules, deploy.sh (free-tier flags; run manually)
docs/      PRD, architecture, decisions, backlog, costs, eval results
```

## Deploy to Google Cloud (Firebase Hosting + Cloud Run)

The web app goes to Firebase Hosting, the API to Cloud Run and the data to Firestore. Cloud Run needs a linked
billing account (Blaze plan), but the demo is sized to stay inside the free allowances (`docs/COSTS.md`).
Create a **budget alert** first: alerts notify you, they do not cap spend. Run the steps in order from the repo
root; each one assumes the previous one succeeded.

```bash
export PROJECT=<your-gcp-project-id>
export REGION=asia-southeast1
export SERVICE=lastmile-api
```

### One-time setup

1. **Prerequisites.** Install `gcloud` and Node. Create a Firebase/GCP project and link billing.
2. **Log in** (three separate logins; the seed script needs the third):
   ```bash
   gcloud auth login
   npx firebase login
   gcloud auth application-default login
   ```
3. **Demo passcode.** Pick one (for example `openssl rand -base64 12`) and keep it: you type it into the web app.
4. **Setup script.** Enables APIs, creates Firestore, adds Firebase, creates the `lastmile-run` service account
   (least privilege), stores the passcode as the `demo-passcode` secret, creates a Gemini API key restricted to the
   Gemini API and stores it as `gemini-api-key`, then seeds synthetic data. It prompts for the passcode (hidden
   input) and for confirmation before seeding. If you would rather use a key from AI Studio
   (<https://aistudio.google.com/apikey>, in a project **without billing** so it stays on the free tier; decline any
   "upgrade to paid" prompt), create the `gemini-api-key` secret yourself before running this step:
   ```bash
   PROJECT=$PROJECT ./infra/deploy.sh setup
   ```
5. **Frontend env.** Nothing to do: `deploy.sh frontend` (step 10) registers the Firebase web app if needed and
   writes `frontend/.env.production` (gitignored) from the Cloud Run URL and the Firebase web config.
6. **Enable Firebase Authentication.** In the console open Build → Authentication → **Get started**, then
   Sign-in method → **Anonymous** → Enable → Save. The console's live reads need anonymous sign-in. (`/pilot`
   additionally needs the Google provider.)

### Every deploy

7. **Check quality**, then **deploy the backend** (a few minutes; answer `Y` to prompts):
   ```bash
   make lint && make test
   CLOUDSDK_CORE_PROJECT=$PROJECT PROJECT=$PROJECT ./infra/deploy.sh backend
   gcloud run services describe $SERVICE --region $REGION --project $PROJECT --format='value(status.url)'
   ```
   `PROJECT=$PROJECT ./infra/deploy.sh status` also prints the API and site URLs plus a health check.
8. **Set the Gemini model and rate.** `deploy.sh backend` now sets them on every deploy (override with
   `GEMINI_AGENT_MODEL=... GEMINI_FALLBACK_MODEL=... GEMINI_RPM=...`); to change them without redeploying:
   ```bash
   gcloud run services update $SERVICE --region $REGION --project $PROJECT \
     --update-env-vars GEMINI_RPM=4,GEMINI_AGENT_MODEL=gemini-2.5-flash-lite,GEMINI_FALLBACK_MODEL=gemini-3.5-flash-lite
   ```
9. **Check the backend:**
   ```bash
   curl -s https://<service-url>/api/health      # expect "status":"ok" and your model names
   ```
10. **Deploy the frontend, Firestore rules and indexes.** Builds the app, copies it to `infra/dist` (Hosting must
    read from inside `infra/`) and deploys:
    ```bash
    PROJECT=$PROJECT ./infra/deploy.sh frontend
    curl -s -o /dev/null -w '%{http_code}\n' https://$PROJECT.web.app/     # expect 200
    ```
11. **Try it.** Open `https://$PROJECT.web.app`, enter the passcode, start the scenario. Residents should move from
    Waiting to Done / Help on the way / Human needed. Press **Reset** afterwards.

### Deploy from GitHub Actions (manual)

`.github/workflows/deploy.yml` deploys on demand: **Actions → deploy → Run workflow** (only from `main`; it runs
lint and tests first, then `infra/deploy.sh backend|frontend|status`). It uses **Workload Identity Federation**, so
no Google key is stored in GitHub. One-time setup by a project owner (VERIFY flags with `--help`):

```bash
export REPO=Shraddha259/lastmile-resilience-agent
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
gcloud iam service-accounts create lastmile-deploy --project $PROJECT
gcloud iam workload-identity-pools create github --location=global --project $PROJECT
gcloud iam workload-identity-pools providers create-oidc github --location=global \
  --workload-identity-pool=github --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository \
  --attribute-condition="assertion.repository=='$REPO'" --project $PROJECT
gcloud iam service-accounts add-iam-policy-binding lastmile-deploy@$PROJECT.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser --project $PROJECT \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"
for r in roles/run.admin roles/cloudbuild.builds.editor roles/artifactregistry.writer roles/storage.admin \
         roles/firebasehosting.admin roles/firebaserules.admin roles/datastore.indexAdmin roles/firebase.viewer \
         roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $PROJECT --role=$r --condition=None \
    --member=serviceAccount:lastmile-deploy@$PROJECT.iam.gserviceaccount.com >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding lastmile-run@$PROJECT.iam.gserviceaccount.com \
  --role=roles/iam.serviceAccountUser --project $PROJECT \
  --member=serviceAccount:lastmile-deploy@$PROJECT.iam.gserviceaccount.com
```

Then in GitHub **Settings → Secrets and variables → Actions → Variables** add (these are not secrets):
`GCP_PROJECT_ID`, `GCP_WIF_PROVIDER` (`projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/providers/github`),
`GCP_DEPLOY_SA` (`lastmile-deploy@<PROJECT>.iam.gserviceaccount.com`), and optionally `GEMINI_AGENT_MODEL`,
`GEMINI_FALLBACK_MODEL`, `GEMINI_RPM` (verify models first with `backend/scripts/check_models.py`). Create an
environment named `production` (add required reviewers there to approve each deploy).

### Operations

- **Change the Gemini key.** Add a secret version (hidden input), then point the service at it:
  ```bash
  read -s -p "New Gemini key: " K; echo
  printf '%s' "$K" | gcloud secrets versions add gemini-api-key --data-file=- --project $PROJECT; unset K
  gcloud secrets versions list gemini-api-key --project $PROJECT      # note the new version number
  gcloud run services update $SERVICE --region $REGION --project $PROJECT \
    --update-secrets GEMINI_API_KEY=gemini-api-key:<new-version>
  ```
- **Read recent errors:**
  ```bash
  gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE AND severity>=WARNING" \
    --limit 20 --freshness 30m --project $PROJECT
  ```
- **Roll back** to an earlier revision (list them with `gcloud run revisions list --service $SERVICE --region $REGION`):
  ```bash
  gcloud run services update-traffic $SERVICE --region $REGION --project $PROJECT --to-revisions <revision>=100
  ```
- **No Gemini calls at all** (demo with the rule-based policy only): add `GENAI_MODE=fake` to `--update-env-vars`;
  use `GENAI_MODE=real` to switch back.

### Gemini troubleshooting

| Log message / symptom                      | Meaning                                | Fix                                                |
| ------------------------------------------ | -------------------------------------- | -------------------------------------------------- |
| `429 Too Many Requests` on a model         | No or low free quota for that model    | Lower `GEMINI_RPM`, or switch `GEMINI_AGENT_MODEL` |
| `404 ... no longer available to new users` | Model retired for new keys             | Pick a model that your key can call (below)        |
| `503 ... high demand`                      | Temporary overload on Google's side    | Retry; use a lighter (`-lite`) model               |
| Cases still finish but without Gemini      | Calls failed, rule-based fallback used | Expected safety behaviour, not an outage           |

Model availability changes. List what your key can call (the key never leaves your shell), then test one:

```bash
K=$(gcloud secrets versions access latest --secret gemini-api-key --project $PROJECT)
curl -s -H "x-goog-api-key: $K" "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200" | grep '"name"'
curl -s -o /dev/null -w '%{http_code}\n' -H "x-goog-api-key: $K" -H 'Content-Type: application/json' \
  -d '{"contents":[{"parts":[{"text":"Reply with the word ok"}]}]}' \
  "https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent"; unset K
```

Notes: a failed "Could not upload file" during `deploy.sh backend` is usually transient, so retry. Never paste the
Gemini key or passcode into chat, tickets or commits.

## Responsible AI

The LLM proposes, code decides: tool calls are validated against the state machine; the agent can only confirm
"safe" from a high-confidence safe-in-place answer; anything medical is escalated to a human **before** any LLM call;
a kill switch stops all calls; every action is in an audit log shown on the console.
