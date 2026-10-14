# Architecture

PRD reference: §5 (architecture), §9 (data model), §11 (API), §12 (orchestrator).

```
Browser (React SPA, Firebase Hosting)
  │  REST commands (X-Demo-Passcode)            ▲ Firestore onSnapshot (read-only, anonymous auth)
  ▼                                             │
FastAPI on Cloud Run (one instance, in-process worker)
  api/        scenarios.py (API-2..4), health.py (API-1)
  services/   worker ─► jobs (checkin, ring_timeout, pump, ttl) ─► dispatcher ─► fallback / decision engine
              classifier · risk · shelters · volunteers · tasks_service · scenario · genai · db
  policy/     state_machine.transition_case()  ◄── the ONLY writer of case status
  agent/      tools.py (shared by fallback + LLM) · context.py (incident scope) · prompts/
  sim/        simulator (cached dialogues) · volunteer_bot
  ▼
Firestore (default DB): residents, shelters, volunteers, scenarios, dialogues,
                        incidents/{id}/{cases, checkins, tasks, agent_events, sitreps}
Gemini API (free tier): classifier, decisions (M3), live voice (M4), SITREP (M5)
```

## Event flow for one resident

```
POST /api/scenarios ─► start_scenario: rank (risk.py) ─► 40 cases PENDING ─► enqueue pump + ttl
pump (every 3 s / scale) ─► PENDING → QUEUED (priority order, ≤ MAX_CONCURRENT_CHECKINS) ─► enqueue checkin
checkin ─► live: QUEUED → RINGING (+ ring_timeout job)      simulated: QUEUED → CONTACTING
        ─► simulator replays dialogue ─► classifier ─► final_status rule ─► CONTACTING → <status>
        ─► emit CHECKIN_COMPLETED ─► dispatch job
dispatcher ─► MEDICAL? escalate now (FR-20) ─► else decision engine (M3) ─► fallback until settled (≤3 steps)
tools ─► reserve_shelter / dispatch_volunteer / schedule_retry / contact_next_of_kin / escalate / confirm_safe
volunteer_bot ─► accept → picked up → arrived → done  ─► AT_SHELTER → CONFIRMED_SAFE
```

## Key invariants

| Invariant                                                                            | Where enforced                                                                               |
| ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| Only `transition_case()` writes status; (from, to, actor) must be in the table       | `policy/state_machine.py`                                                                    |
| Counters + audit event written in the same commit as the status                      | `transition_case()`                                                                          |
| Agent confirms safe only from SAFE_IN_PLACE with confidence ≥ min and no review flag | `check_guard()`                                                                              |
| MEDICAL escalates before any LLM call                                                | `services/dispatcher.py::_decide`                                                            |
| No case is left in an action-required status                                         | fallback loop + safety-net escalation in the dispatcher                                      |
| Jobs are idempotent                                                                  | each handler re-checks case state; check-in start uses `expected_version`                    |
| Kill switch                                                                          | `scenario.stop_incident` → `worker.cancel_incident` (cancels waiting jobs, refuses new ones) |
| Incident scope can't be chosen by the LLM                                            | `agent/context.current_incident` ContextVar                                                  |

## Where to put new things

- **New job** → `services/jobs.py` with `@worker.job`. Same name/payload as the PRD's INT-x endpoint.
- **New REST command** → a router in `api/`, passcode dependency, errors via `util/errors.py`.
- **New LLM call** → `services/genai.generate_json(...)` with a `fake=` output for tests and keyless dev.
- **New UI data** → read from Firestore with `lib/useFirestore.ts`; never add REST reads.

## Phase switches (keep interfaces stable)

| Switch              | P1 (now)                            | P2                                             |
| ------------------- | ----------------------------------- | ---------------------------------------------- |
| `TASKS_MODE`        | `inline` (in-process worker)        | `cloud` (Cloud Tasks, `/internal/*` with OIDC) |
| `DECISION_ENGINE`   | `structured` (one Gemini JSON call) | `adk` (ADK agent, same tools)                  |
| `SIM_DIALOGUE_MODE` | `cached` (free tier)                | `turns` (persona LLM)                          |
