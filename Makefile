# LastMile developer commands. Run `make help` for the list.
SHELL := /bin/bash
EMU_ENV := FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCP_PROJECT_ID=demo-lastmile

.PHONY: help setup env emulators seed api web dev test test-unit test-scenario lint fmt types seed-gen check-types

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: env ## Install backend (uv) and frontend (npm) dependencies
	cd backend && uv sync
	npm ci
	cd frontend && npm ci
	-pre-commit install 2>/dev/null || echo "tip: 'uv tool install pre-commit && pre-commit install' enables git hooks"

env: ## Create local .env files from the examples (never overwrites)
	@test -f backend/.env || cp backend/.env.example backend/.env
	@test -f frontend/.env.local || cp frontend/.env.example frontend/.env.local

emulators: ## Start Firestore + Auth emulators (UI on http://127.0.0.1:4000)
	npx firebase emulators:start --config infra/firebase.json --project demo-lastmile --only firestore,auth

seed: ## Load the committed seed data into the emulator
	$(EMU_ENV) uv run --project backend python seed/seed_firestore.py

seed-gen: ## Regenerate seed JSON (deterministic, random seed 42)
	uv run --project backend python seed/generate_seed.py

api: ## Run the backend on http://127.0.0.1:8000 (reads backend/.env)
	cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

web: ## Run the frontend on http://127.0.0.1:5173
	cd frontend && npm run dev -- --host 127.0.0.1

dev: ## Emulators + seed + API + web together (Ctrl-C stops all)
	@trap 'kill 0' EXIT; \
	$(MAKE) emulators & \
	until curl -s 127.0.0.1:8080 >/dev/null; do sleep 1; done; \
	$(MAKE) seed && ($(MAKE) api & $(MAKE) web & wait)

test: ## All backend tests (starts emulators automatically) + frontend tests
	npx firebase emulators:exec --config infra/firebase.json --project demo-lastmile --only firestore \
	  "cd backend && uv run pytest"
	cd frontend && npm test

test-unit: ## Backend unit tests (emulator tests skip if it isn't running)
	cd backend && uv run pytest tests/unit

test-scenario: ## Scenario tests (needs `make emulators` running)
	cd backend && uv run pytest tests/scenario

lint: check-types ## Lint backend (ruff) and frontend (tsc + prettier)
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint
	npm run format:check

fmt: ## Format backend and frontend
	cd backend && uv run ruff check --fix . && uv run ruff format .
	npm run format

types: ## Regenerate frontend/src/types.gen.ts from backend/app/models.py
	cd backend && uv run python scripts/export_types.py

check-types: ## Fail if types.gen.ts is out of date
	@cd backend && uv run python scripts/export_types.py >/dev/null
	@git diff --quiet -- frontend/src/types.gen.ts || (echo "types.gen.ts is stale: run 'make types' and commit" && exit 1)
