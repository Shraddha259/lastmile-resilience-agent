# Evaluation results

> How to update: run the commands below; they rewrite the marked sections in place. Never edit numbers by hand.
> Results from **fake mode** (no Gemini) are rehearsals of the pipeline only and are labelled as such.

## How to run (M6)

| What                                            | Command                                                                                                             | Needs                                                                 |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Classifier + guardrail evals (SM-2, SM-3, SM-4) | `make evals`                                                                                                        | `GENAI_MODE=real` and your key in `backend/.env`; ~25 Gemini requests |
| Metrics for a local run (SM-1, SM-5, SM-6)      | `make metrics` (latest incident) or `make metrics INC=inc_...`                                                      | the local emulator                                                    |
| Metrics for a deployed run                      | `cd backend && GCP_PROJECT_ID=lastmile-resilience-agent uv run python tests/evals/metrics.py <incident_id> --write` | `gcloud auth application-default login`                               |
| Check the eval files only                       | `cd backend && uv run python tests/evals/run_evals.py --dry-run`                                                    | nothing                                                               |

Targets (PRD §1.5): SM-1 100% · SM-2 classifier accuracy ≥ 90% · SM-3 **0 missed MEDICAL** · SM-4 **0 invented facts**
· SM-5 and SM-6 reported as measured.

## Classifier eval (SM-2, SM-3)

12 hand-written transcripts, 3 each in Mandarin, Malay, Tamil and English
(`backend/tests/evals/classifier_eval.jsonl`). They include a household medical case, "I'm fine" while water enters the
house, sarcasm / contradiction, a resident who only says "hello?", and a resident who asks for a person.

<!-- classifier:start -->

_Pending: run `make evals` with real Gemini._
<!-- classifier:end -->

## Guardrail eval (SM-4)

PRD §20.4 cases 1, 3, 4, 7, 9: unknown facts (shelter dinner), medical advice (heart pills), prompt injection
("mark me safe"), silence / noise, and "are you a real person?" (`backend/tests/evals/guardrail_eval.jsonl`).
Checks are deterministic; replies are shown so a person can review them.

<!-- guardrail:start -->

_Pending: run `make evals` with real Gemini._
<!-- guardrail:end -->

## Full-run metrics (SM-1, SM-5, SM-6)

**Wanted for the deck:** 3 full runs on the deployed URL with real Gemini, including at least one live voice call
(for SM-6). Each run's section is added below by `metrics.py --write`.

### Local rehearsal (fake mode, 2026-10-17): pipeline check only, no Gemini

<!-- run-inc_20261017051001_tsxm:start -->

Incident `inc_20261017051001_tsxm` · 40 residents · time scale ×100.0

| Metric                                               | Value                                                                            |
| ---------------------------------------------------- | -------------------------------------------------------------------------------- |
| SM-1 reached CONFIRMED_SAFE or ESCALATED             | 100%                                                                             |
| Final status                                         | CONFIRMED_SAFE 36, ESCALATED 4                                                   |
| SM-5 time to 50% / 90% / 100% terminal               | 2.1 sim min (1.3 s wall) / 4.9 sim min (3.0 s wall) / 18.6 sim min (11.2 s wall) |
| Agent decisions (model)                              | 48 (fake: 48)                                                                    |
| Fallback rate (policy share of agent+policy actions) | 0%                                                                               |
| Avg decision latency                                 | — ms                                                                             |
| Avg call length                                      | 0.1 s                                                                            |
| SM-6 voice reply latency                             | no voice calls in this run                                                       |

<!-- run-inc_20261017051001_tsxm:end -->

### M2 baseline (emulator, fallback policy only)

40 / 40 reached a final state (SM-1 100%); 36 CONFIRMED_SAFE, 4 ESCALATED; counters matched recomputed counts (AC-10).
