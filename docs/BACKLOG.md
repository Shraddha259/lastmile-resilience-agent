# Backlog (Phase 1)

Pick a task, put your name in **owner**, open a PR. Tasks list requirement IDs, the main files, and the
acceptance test ("done when"). Order follows PRD §22. Don't start a milestone until the previous gate passes.

Legend: ✅ done · 🔜 next · ⬜ open

## M0–M2 — Foundations, core state, loop without LLM ✅

| #   | Task                                                                          | IDs                 | Status |
| --- | ----------------------------------------------------------------------------- | ------------------- | ------ |
| 0.1 | Repo scaffold, config, models, utils, Makefile, CI, team docs                 | §7, §8, NFR-S1      | ✅     |
| 0.2 | Seed generator (seed 42) + committed JSON + loader                            | §19                 | ✅     |
| 0.3 | Firebase emulators, rules (read-only clients)                                 | NFR-S5              | ✅     |
| 1.1 | `transition_case()` + transitions table + guards                              | FR-1..FR-4          | ✅     |
| 1.2 | Risk scoring, shelter matching, volunteer selection                           | FR-5, §15.2, §15.3  | ✅     |
| 2.1 | In-process worker, pump, check-in / ring-timeout / TTL jobs, startup recovery | FR-10, FR-19        | ✅     |
| 2.2 | Simulator (cached dialogues), classifier + final status rule                  | FR-18, FR-21        | ✅     |
| 2.3 | Tools, fallback policy, dispatcher (MEDICAL fast path)                        | FR-11, FR-13, FR-20 | ✅     |
| 2.4 | Volunteer bot                                                                 | FR-23               | ✅     |
| 2.5 | API-1..API-4, kill switch, reset                                              | FR-30               | ✅     |
| 2.6 | Console v1: map, board, counter, stop/reset, SIMULATED tags                   | FR-40, FR-41, FR-22 | ✅     |

## M3 — Decisions (Fri 16 AM) 🔜

| #   | Task                                                                                          | IDs   | Files                                                                                        | Done when                                                                        | Owner |
| --- | --------------------------------------------------------------------------------------------- | ----- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ----- |
| 3.1 | Validator: allowed tools, resident match, enums, lengths, IDs in candidates, transition check | FR-12 | `agent/validator.py`, tests                                                                  | unit tests for wrong resident / disallowed tool / unknown shelter / long strings |       |
| 3.2 | Structured decision engine: prompt §12.2, schema, ≤3 actions, timeout, log `overall_reason`   | FR-14 | `agent/decision.py`, `agent/prompts/orchestrator.md`, `services/dispatcher.py::run_decision` | AC-4 passes; fallback < 20% of decisions on a real run                           |       |
| 3.3 | `build_context()`: resident, case, classification, candidate shelters, top-3 volunteers       | §12.6 | `services/dispatcher.py`                                                                     | context snapshot test                                                            |       |
| 3.4 | Agent log panel (newest first, actor badges, latency, cap 200)                                | §16.3 | `components/AgentLog.tsx`                                                                    | renders 300 events without freezing                                              |       |
| 3.5 | CaseDrawer: profile, risk reasons, timeline, transcripts, classification                      | §16.3 | `components/CaseDrawer.tsx`                                                                  | opens from row and marker click                                                  |       |
| 3.6 | `seed/generate_dialogues.py`: in-language dialogues via Gemini, reviewed, committed           | D-002 | `seed/`                                                                                      | 36 dialogues with `text` + `text_en`                                             |       |
| 3.7 | VERIFY free-tier model IDs; set defaults in `.env.example`                                    | D-019 | `config.py`                                                                                  | `/api/health` lists working models                                               |       |

## M4 — Live voice (Fri 16 PM, gate 15:00) ⬜

| #   | Task                                                                      | IDs        | Files                                         | Done when                       | Owner |
| --- | ------------------------------------------------------------------------- | ---------- | --------------------------------------------- | ------------------------------- | ----- |
| 4.1 | API-8 voice session tokens (one-time, 10 min)                             | §11.2      | `api/voice.py`                                | 409 unless live + RINGING       |       |
| 4.2 | Live bridge WS ⇄ Gemini Live (VERIFY SDK), live tools, agent speaks first | FR-15, §13 | `voice/live_bridge.py`, `voice/live_tools.py` | AC-8 manual                     |       |
| 4.3 | Text fallback (`LIVE_MODE=text`)                                          | §11.3      | `voice/live_bridge.py`                        | typed chat completes a check-in |       |
| 4.4 | Resident page: ringing, answer, captions, hang up                         | FR-42      | `pages/Resident.tsx`                          | AC-9                            |       |
| 4.5 | Audio worklet + recorder/player (16 kHz in, 24 kHz out)                   | §16.7      | `public/audio-worklet.js`, `src/audio/`       | vitest for conversions          |       |
| 4.6 | Kill switch closes live sessions within 2 s                               | AC-5       | `scenario.on_stop` hook                       | AC-5                            |       |

## M5 — Human loop (Sat 17 AM) ⬜

| #   | Task                                                       | IDs   | Files                                              | Done when                                         | Owner |
| --- | ---------------------------------------------------------- | ----- | -------------------------------------------------- | ------------------------------------------------- | ----- |
| 5.1 | API-5 approve/reject + TaskQueue cards                     | US-3  | `api/coordinator.py`, `components/TaskQueue.tsx`   | approve starts the bot; reject releases volunteer |       |
| 5.2 | API-6 overrides with note (≥5 chars)                       | US-4  | `api/coordinator.py`, CaseDrawer                   | coordinator can confirm/escalate                  |       |
| 5.3 | API-7 SITREP (grounded snapshot, IDs not names)            | FR-25 | `services/sitrep.py`, `components/SitrepPanel.tsx` | shows "as of" time                                |       |
| 5.4 | Next-of-kin toast on console                               | §15.4 | console                                            | toast text matches §15.4                          |       |
| 5.5 | AC-3 test (MEDICAL → ESCALATED < 2 s, before any LLM call) | AC-3  | `tests/scenario`                                   | passes                                            |       |

## M6 — Prove it (Sat 17 PM, feature freeze 18:00) ⬜

| #   | Task                                                           | IDs        | Done when                     | Owner |
| --- | -------------------------------------------------------------- | ---------- | ----------------------------- | ----- |
| 6.1 | Classifier eval: 12 transcripts (zh/ms/ta/en) + `run_evals.py` | SM-2, SM-3 | `docs/EVAL_RESULTS.md` filled |       |
| 6.2 | Guardrail eval: cases 1, 3, 4, 7, 9                            | SM-4       | 0 invented facts              |       |
| 6.3 | `tests/evals/metrics.py` (SM-1..SM-6) + 3 full runs            | §18        | numbers in EVAL_RESULTS       |       |
| 6.4 | Security pass (rules, CORS, rate limits, logs)                 | NFR-S*     | checklist in PR               |       |
| 6.5 | Deck + rough video draft                                       | HC-4       | shared with team              |       |

## M7 — Ship (Sun 18) ⬜

| #   | Task                                                                           | Done when                     | Owner |
| --- | ------------------------------------------------------------------------------ | ----------------------------- | ----- |
| 7.1 | First real deploy (`infra/deploy.sh setup/backend/frontend`), budget alert set | public URL works logged out   |       |
| 7.2 | README links, final video (< 3 min), deck PDF, tag `v1.0-submission`           | submitted hours before cutoff |       |

**Cut order if late (PRD §22):** SITREP button → CaseDrawer polish → guardrail evals.
**Never cut:** live call (voice or text), safe counter, MEDICAL escalation, kill switch, fallback policy.
