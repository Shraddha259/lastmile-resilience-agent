# Contributing to LastMile

Welcome! This page gets you from clone to merged PR. The spec is [docs/PRD.md](docs/PRD.md); when in doubt, the PRD
wins, and if the PRD is ambiguous, pick the simplest option that passes the acceptance test and record it in
[docs/DECISIONS.md](docs/DECISIONS.md).

## 1. Set up (≈5 minutes)

```bash
make setup        # uv sync + npm ci, creates backend/.env and frontend/.env.local from the examples
make dev          # emulators + seed + API + web
```

No Gemini key is needed: `GENAI_MODE=fake` (the default) returns scripted model outputs. To try real models, put
**your own** AI Studio key in `backend/.env` (`GEMINI_API_KEY`, `GENAI_MODE=real`). Never commit it.

Optional git hooks (ruff, gitleaks, no `.env` files): `uv tool install pre-commit && pre-commit install`.

## 2. Pick a task

Tasks live in [docs/BACKLOG.md](docs/BACKLOG.md). Put your name in the `owner` column in your first PR (or turn the
task into a GitHub issue and assign yourself). Tasks are sized so two people rarely touch the same files.

## 3. Branch, commit, PR

- Branch from `main`: `feat/M3-decision-engine`, `fix/pump-ordering`, `docs/costs`.
- **Reference requirement IDs** in commits and test names (PRD §0.10):
  `feat(dispatcher): validate tool calls (FR-12)`, `test_FR_12_unknown_shelter_rejected`.
- Open a PR into `main` and fill in the template. CI must be green (lint, tests, secret scan).
- One approving review before merge. Squash-merge.
- Phase 2 work goes on the `phase2` branch, never on `main` (PRD §0.1 freeze rule).

## 4. House rules (from PRD §0 and §23)

1. **Only `transition_case()` writes `cases/*.status`** (`backend/app/policy/state_machine.py`).
2. **The LLM proposes, code decides.** Tool calls go through the validator; failures fall back to `policy/fallback.py`.
3. **No hard-coded model IDs, URLs, timeouts or limits.** Add them to `backend/app/config.py` and `.env.example`.
4. **Background work only through `worker.enqueue()`.** Job handlers must be idempotent.
5. **`incident_id` is never a tool parameter.** Tools read it from `agent/context.py`.
6. **Synthetic data only.** No real names, numbers, addresses, or photos. Mask phone numbers.
7. **No secrets in the repo**, logs, or browser storage. The demo passcode lives in React state only.
8. **Don't log transcripts or phone numbers** (NFR-S8). Log IDs, statuses, and lengths.
9. **Build only [P1] items** until M7 ships.
10. New frameworks need a line in `docs/DECISIONS.md`.

## 5. Common recipes

| I want to…                      | Do this                                                                                           |
| ------------------------------- | ------------------------------------------------------------------------------------------------- |
| Add or change a Firestore field | Edit `backend/app/models.py`, run `make types`, commit `frontend/src/types.gen.ts`                |
| Add a case status transition    | Edit `_rows()` in `policy/state_machine.py` + a test in `tests/unit/test_state_machine.py`        |
| Add a tool                      | Function in `agent/tools.py` (decorate with `@tool`, take `actor=`), register in `TOOLS`, test it |
| Add a background job            | `@worker.job("name")` handler in `services/jobs.py`; enqueue with a deterministic `dedupe_key`    |
| Change a prompt                 | Edit `backend/app/agent/prompts/*.md`; keep transcripts inside the delimited DATA block (NFR-S12) |
| Add/modify residents            | Edit `seed/generate_seed.py`, run `make seed-gen && make seed`, update risk test values if needed |
| Add a console component         | `frontend/src/components/`; status visuals come from `lib/status.ts` (colour + icon + text)       |

## 6. Tests

- `make test-unit` — pure logic + Firestore tests (emulator tests skip if it isn't running).
- `make test-scenario` — full runs against the emulator at `SIM_TIME_SCALE=100` (needs `make emulators`).
- `make test` — everything, starting the emulator for you.
- Name tests after requirement IDs: `test_AC_7_concurrent_reservations_respect_capacity`.

## 7. Getting help

Architecture overview: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Open a draft PR early if you're unsure. A
draft with a question is better than a big surprise.
