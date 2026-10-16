#!/usr/bin/env bash
# LastMile [P1] deployment on the Google Cloud free tier (PRD §21, docs/COSTS.md).
#
# NOT run by CI. Review every step, run it yourself, and VERIFY flags against current
# gcloud docs. Usage:
#   PROJECT=<gcp-project-id> ./infra/deploy.sh setup     # one-time project setup
#   PROJECT=<gcp-project-id> ./infra/deploy.sh backend   # deploy lastmile-api
#   PROJECT=<gcp-project-id> ./infra/deploy.sh frontend  # build + deploy hosting and rules
set -euo pipefail

: "${PROJECT:?Set PROJECT to your GCP project ID}"
REGION="${REGION:-asia-southeast1}"
RUN_SA="lastmile-run@${PROJECT}.iam.gserviceaccount.com"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

setup() {
  echo "Before continuing: link a billing account and create a BUDGET ALERT"
  echo "(e.g. \$1 / \$5 / \$10) in the Billing console. Alerts do not cap spend."
  read -r -p "Budget alert created? [y/N] " ok
  [[ "$ok" == "y" ]] || exit 1

  gcloud config set project "$PROJECT"
  gcloud services enable run.googleapis.com firestore.googleapis.com \
    secretmanager.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
    iamcredentials.googleapis.com
  # Free Firestore quota applies only to the (default) database.
  gcloud firestore databases create --location="$REGION" || true

  gcloud iam service-accounts create lastmile-run --display-name="LastMile Cloud Run" || true
  # Least privilege (NFR-S3, minus Vertex/Cloud Tasks roles not used in P1 free tier).
  for role in roles/datastore.user roles/secretmanager.secretAccessor roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding "$PROJECT" \
      --member="serviceAccount:${RUN_SA}" --role="$role" --condition=None >/dev/null
  done

  echo "Create secrets (values are read from your terminal, never from files in the repo):"
  read -r -s -p "DEMO_PASSCODE: " pass; echo
  printf '%s' "$pass" | gcloud secrets create demo-passcode --data-file=- \
    || printf '%s' "$pass" | gcloud secrets versions add demo-passcode --data-file=-
  read -r -s -p "GEMINI_API_KEY (AI Studio, free tier): " key; echo
  printf '%s' "$key" | gcloud secrets create gemini-api-key --data-file=- \
    || printf '%s' "$key" | gcloud secrets versions add gemini-api-key --data-file=-
  unset pass key

  echo "Seed Firestore (asks for confirmation because it targets the real project):"
  GCP_PROJECT_ID="$PROJECT" uv run --project "$ROOT/backend" python "$ROOT/seed/seed_firestore.py"
}

backend() {
  local origins="${ALLOWED_ORIGINS:-https://${PROJECT}.web.app,https://${PROJECT}.firebaseapp.com}"
  # Free tier: scale to zero between demos; one instance max so the in-process worker
  # (PRD §5.3) sees every job; CPU stays allocated while the instance lives. VERIFY flags.
  gcloud run deploy lastmile-api --source "$ROOT/backend" --region "$REGION" \
    --service-account "$RUN_SA" \
    --allow-unauthenticated \
    --no-cpu-throttling --min-instances 0 --max-instances 1 \
    --cpu 1 --memory 512Mi --timeout 3600 --concurrency 80 \
    --set-secrets DEMO_PASSCODE=demo-passcode:latest,GEMINI_API_KEY=gemini-api-key:latest \
    --set-env-vars "^@^GCP_PROJECT_ID=${PROJECT}@GCP_REGION=${REGION}@TASKS_MODE=inline@DECISION_ENGINE=structured@PHASE=1@GENAI_MODE=real@GENAI_USE_VERTEX=false@LIVE_USE_AI_STUDIO=true@SIM_DIALOGUE_MODE=cached@ALLOWED_ORIGINS=${origins}"

  # Keep Artifact Registry under the free storage allowance (VERIFY command and policy format).
  echo "Tip: add an Artifact Registry cleanup policy keeping the 2 newest images:"
  echo "  gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy \\"
  echo "    --location=$REGION --policy=infra/ar-cleanup-policy.json"
}

frontend() {
  test -f "$ROOT/frontend/.env.production" || {
    echo "Create frontend/.env.production (VITE_API_BASE_URL, VITE_WS_BASE_URL, Firebase web config)."
    exit 1
  }
  (cd "$ROOT/frontend" && npm ci && npm run build)
  # Firebase Hosting's public dir must sit inside the firebase.json directory.
  rm -rf "$ROOT/infra/dist" && cp -R "$ROOT/frontend/dist" "$ROOT/infra/dist"
  (cd "$ROOT" && npx firebase deploy --config infra/firebase.json --project "$PROJECT" \
    --only hosting,firestore:rules,firestore:indexes)
}

case "${1:-}" in
  setup) setup ;;
  backend) backend ;;
  frontend) frontend ;;
  *) echo "usage: PROJECT=<id> $0 {setup|backend|frontend}"; exit 1 ;;
esac
