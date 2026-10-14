# LastMile — from disaster alert to confirmed safety

When a flood alert is issued, LastMile finds every vulnerable resident in the alert zone, ranks them by risk,
checks on each one in their own language, and takes the next step (shelter, a volunteer, next-of-kin, or a human
coordinator) until every person is **confirmed safe** or **handed to a human**.

Built for the Google Cloud AI Builder Cup 2026 (theme: Sustainability & Social Impact).
All data is synthetic. No real residents, names, phone numbers or addresses.

|                         |                                                     |
| ----------------------- | --------------------------------------------------- |
| Spec                    | [docs/PRD.md](docs/PRD.md) (single source of truth) |
| Architecture            | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)        |
| Work board              | [docs/BACKLOG.md](docs/BACKLOG.md)                  |
| How to contribute       | [CONTRIBUTING.md](CONTRIBUTING.md)                  |
| Design decisions        | [docs/DECISIONS.md](docs/DECISIONS.md)              |
| Free-tier budget        | [docs/COSTS.md](docs/COSTS.md)                      |
| Demo URL / video / deck | _added at M7_                                       |

## Status

Phase 1 MVP, milestones **M0–M2 done**. The full 40-resident loop runs locally on the deterministic fallback
policy with the coordinator console v1. Next up: M3 (Gemini decision engine), M4 (live voice).

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

## Responsible AI

The LLM proposes, code decides: tool calls are validated against the state machine; the agent can only confirm
"safe" from a high-confidence safe-in-place answer; anything medical is escalated to a human **before** any LLM call;
a kill switch stops all calls; every action is in an audit log shown on the console.
