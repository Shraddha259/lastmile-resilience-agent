#!/usr/bin/env bash
# LastMile [P1] deployment on Google Cloud at no cost (free tier / trial credit; docs/COSTS.md).
#
# NOT run by CI. Run each step yourself, in order, after `gcloud auth login` and
# `gcloud auth application-default login`. VERIFY flags against `gcloud <cmd> --help`.
#   PROJECT=<gcp-project-id> ./infra/deploy.sh setup     # one-time: APIs, DB, SA, secrets, seed
#   PROJECT=<gcp-project-id> ./infra/deploy.sh backend   # deploy lastmile-api to Cloud Run
#   PROJECT=<gcp-project-id> ./infra/deploy.sh frontend  # build + deploy hosting and Firestore rules
#   PROJECT=<gcp-project-id> ./infra/deploy.sh status    # print URLs and a health check
set -euo pipefail

: "${PROJECT:?Set PROJECT to your GCP project ID}"
REGION="${REGION:-asia-southeast1}"
SERVICE=lastmile-api
RUN_SA="lastmile-run@${PROJECT}.iam.gserviceaccount.com"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIREBASE=(npx --prefix "$ROOT" firebase --project "$PROJECT")

setup() {
  echo "Before continuing: billing linked to $PROJECT and a BUDGET ALERT created"
  echo "(e.g. \$1 / \$5 / \$10) in the Billing console. Alerts do not cap spend."
  read -r -p "Billing linked and budget alert created? [y/N] " ok
  [[ "$ok" == "y" ]] || exit 1

  gcloud config set project "$PROJECT"
  gcloud services enable run.googleapis.com firestore.googleapis.com \
    secretmanager.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
    iamcredentials.googleapis.com generativelanguage.googleapis.com apikeys.googleapis.com \
    firebase.googleapis.com identitytoolkit.googleapis.com

  # The free Firestore quota applies to the project's FIRST database: create (default) first.
  gcloud firestore databases create --location="$REGION" || echo "(Firestore DB already exists)"

  # Firebase on the same project (Hosting + Auth). Enable Anonymous sign-in in the
  # Firebase console afterwards: Authentication > Sign-in method > Anonymous.
  "${FIREBASE[@]}" projects:addfirebase "$PROJECT" || echo "(Firebase already added)"

  gcloud iam service-accounts create lastmile-run --display-name="LastMile Cloud Run" \
    || echo "(service account exists)"
  # Least privilege (NFR-S3, minus Vertex/Cloud Tasks roles not used in P1).
  for role in roles/datastore.user roles/secretmanager.secretAccessor roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding "$PROJECT" \
      --member="serviceAccount:${RUN_SA}" --role="$role" --condition=None >/dev/null
  done

  echo "Demo passcode for judges (typed here, stored only in Secret Manager):"
  read -r -s -p "DEMO_PASSCODE: " pass; echo
  printf '%s' "$pass" | gcloud secrets create demo-passcode --data-file=- \
    || printf '%s' "$pass" | gcloud secrets versions add demo-passcode --data-file=-
  unset pass

  # Gemini API key restricted to the Gemini API only (unrestricted keys are rejected
  # from June 2026). The key string goes straight into Secret Manager, never printed.
  if ! gcloud secrets describe gemini-api-key >/dev/null 2>&1; then
    key_name=$(gcloud services api-keys create --display-name="lastmile-gemini" \
      --api-target=service=generativelanguage.googleapis.com --format='value(response.name)')
    gcloud services api-keys get-key-string "$key_name" --format='value(keyString)' \
      | gcloud secrets create gemini-api-key --data-file=-
  else
    echo "(gemini-api-key secret exists)"
  fi

  echo "Seeding Firestore in $PROJECT (synthetic data only):"
  GCP_PROJECT_ID="$PROJECT" uv run --project "$ROOT/backend" python "$ROOT/seed/seed_firestore.py"
}

backend() {
  local origins="${ALLOWED_ORIGINS:-https://${PROJECT}.web.app,https://${PROJECT}.firebaseapp.com}"
  # Until M5 (approval UI) and M4 (live voice) ship: auto-approve dispatch so bot volunteers
  # finish cases, and a short ring timeout so the two live residents don't wait 6+ minutes.
  local m2="AUTO_APPROVE_DISPATCH=true@FORCE_FALLBACK=true@LIVE_RING_TIMEOUT_S=30"
  # Scale to zero between demos; max 1 instance so the in-process worker (PRD §5.3) sees
  # every job; CPU stays allocated while the instance lives (instance-based billing).
  gcloud run deploy "$SERVICE" --source "$ROOT/backend" --region "$REGION" \
    --service-account "$RUN_SA" \
    --allow-unauthenticated \
    --no-cpu-throttling --min-instances 0 --max-instances 1 \
    --cpu 1 --memory 512Mi --timeout 3600 --concurrency 80 \
    --set-secrets DEMO_PASSCODE=demo-passcode:latest,GEMINI_API_KEY=gemini-api-key:latest \
    --set-env-vars "^@^GCP_PROJECT_ID=${PROJECT}@GCP_REGION=${REGION}@TASKS_MODE=inline@DECISION_ENGINE=structured@PHASE=1@GENAI_MODE=real@GENAI_USE_VERTEX=false@LIVE_USE_AI_STUDIO=true@SIM_DIALOGUE_MODE=cached@ALLOWED_ORIGINS=${origins}@${m2}"

  echo "Tip: keep Artifact Registry small (VERIFY the command first):"
  echo "  gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy \\"
  echo "    --location=$REGION --policy=infra/ar-cleanup-policy.json"
}

write_env_production() {
  local api app_id
  api=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
  [[ -n "$api" ]] || { echo "Deploy the backend first."; exit 1; }
  app_id=$("${FIREBASE[@]}" --json apps:list WEB | node -e \
    'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const r=JSON.parse(s).result||[];console.log(r[0]?.appId||"")})')
  if [[ -z "$app_id" ]]; then
    "${FIREBASE[@]}" apps:create WEB lastmile-web >/dev/null
    app_id=$("${FIREBASE[@]}" --json apps:list WEB | node -e \
      'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>console.log(JSON.parse(s).result[0].appId))')
  fi
  # The Firebase web config is public by design (not a secret); the file stays uncommitted.
  "${FIREBASE[@]}" --json apps:sdkconfig WEB "$app_id" | API="$api" node -e '
    let s=""; process.stdin.on("data",d=>s+=d).on("end",()=>{
      const c = JSON.parse(s).result.sdkConfig;
      const api = process.env.API;
      console.log([
        `VITE_API_BASE_URL=${api}`,
        `VITE_WS_BASE_URL=${api.replace(/^https/, "wss")}`,
        "VITE_USE_EMULATORS=false",
        `VITE_FIREBASE_PROJECT_ID=${c.projectId}`,
        `VITE_FIREBASE_API_KEY=${c.apiKey}`,
        `VITE_FIREBASE_AUTH_DOMAIN=${c.authDomain}`,
        `VITE_FIREBASE_APP_ID=${c.appId}`,
      ].join("\n"));
    });' > "$ROOT/frontend/.env.production"
  echo "wrote frontend/.env.production"
}

frontend() {
  write_env_production
  (cd "$ROOT/frontend" && npm ci && npm run build)
  # Firebase Hosting's public dir must sit inside the firebase.json directory.
  rm -rf "$ROOT/infra/dist" && cp -R "$ROOT/frontend/dist" "$ROOT/infra/dist"
  (cd "$ROOT" && "${FIREBASE[@]}" deploy --config infra/firebase.json \
    --only hosting,firestore:rules,firestore:indexes)
}

status() {
  local api
  api=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
  echo "API:      $api"
  echo "Frontend: https://${PROJECT}.web.app"
  curl -s "$api/api/health" && echo
}

case "${1:-}" in
  setup) setup ;;
  backend) backend ;;
  frontend) frontend ;;
  status) status ;;
  *) echo "usage: PROJECT=<id> $0 {setup|backend|frontend|status}"; exit 1 ;;
esac
