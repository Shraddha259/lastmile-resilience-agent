# LastMile — notes for Claude

Flood alert → every vulnerable resident confirmed safe or handed to a human. Spec: `docs/PRD.md` (large —
read the section you need, don't load it whole). Python 3.12 / FastAPI backend, React 18 / Vite frontend,
Firestore, Gemini. Phase 1 only (P1 items) until milestone M7.

## Commands

- `make setup` · `make dev` (emulators + seed + API :8000 + web :5173) · `make help`
- `make test` (starts the Firestore emulator itself) · `make test-unit` · `make test-scenario` (needs `make emulators`)
- `make lint` (ruff, tsc, prettier, generated-types check) · `make fmt`
- `make types` after any change to `backend/app/models.py`; commit `frontend/src/types.gen.ts`
- Single backend test: `cd backend && uv run pytest tests/unit/test_risk.py -k FR_5`

## Hard rules (break these and the PR is wrong)

- Only `transition_case()` (`backend/app/policy/state_machine.py`) writes `cases/*.status`.
- LLM proposes, code decides: tool calls go through the validator; failures fall back to `policy/fallback.py`.
- Background work only via `worker.enqueue()`; handlers must be idempotent (re-check state, use `expected_version`).
- `incident_id` is never a tool/LLM parameter — tools read `agent/context.current_incident`.
- No hard-coded model IDs, URLs, timeouts, limits: add to `backend/app/config.py` + `.env.example`.
- Every LLM call goes through `services/genai.generate_json(..., fake=...)` so fake mode and tests work.
- Synthetic data only; never log transcripts or phone numbers; passcode lives in React state only.
- Must stay on the Google Cloud free tier (see `docs/COSTS.md`) — no Vertex, no always-on instances.

## Code style (differs from defaults)

- Python: ruff, line length 100, `X | None` unions, StrEnum enums, docstrings on public functions.
- Name tests after requirement IDs: `test_FR_12_...`, `test_AC_7_...`. Commits reference IDs too.
- Frontend: Prettier width 110, double quotes. Status UI always colour + icon + text (`lib/status.ts`).
- UI reads come from Firestore listeners (`lib/useFirestore.ts`); REST is for commands only.

## Before finishing a change

`make lint && make test`. Record any resolved ambiguity in `docs/DECISIONS.md` (D-xxx row).

## Imported notes

@docs/ARCHITECTURE.md
@docs/claude-notes/GOTCHAS.md
@docs/claude-notes/OPEN-QUESTIONS.md

Project decisions table: `docs/DECISIONS.md`. Work board: `docs/BACKLOG.md`.
Personal scratch notes: `.claude/scratch/` (gitignored).
