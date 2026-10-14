# Free-tier budget

Goal: run LastMile within Google Cloud / Firebase no-cost quotas. A billing account must still be linked for Cloud
Run, so **set budget alerts** ($1 / $5 / $10). Alerts don't cap spend.

> Quota numbers change. Every figure marked **VERIFY** must be checked against the current pricing pages
> (Cloud Run, Firestore, Gemini API rate limits, Firebase Hosting) before deploying.

## Per-run usage (measured on the emulator, M2, fallback only)

Source: `test_AC_2_AC_10_full_run_fallback_only` (`db.STATS`), 40 residents.

| Resource                            | Per run                                                     | Notes                                                                   |
| ----------------------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------- |
| Firestore writes (backend)          | **~790**                                                    | Status changes + audit events + check-ins + tasks. Test asserts < 3,000 |
| Firestore reads (backend)           | **~2,200**                                                  | Mostly the pump reading 40 cases per tick, plus tool lookups            |
| Firestore reads (each open console) | ~600 (estimate)                                             | One read per changed document per listening client                      |
| Firestore deletes (Reset)           | ~700 (estimate)                                             | Cases, check-ins, tasks, audit events                                   |
| Gemini calls                        | 36 classifier (cached dialogues) + ~40–60 decisions from M3 | ~100 per run. Fake mode = 0                                             |
| Cloud Run                           | ~10 min active + up to 15 min idle per demo                 | Instance billing while alive (`--no-cpu-throttling`)                    |

## Daily / monthly headroom

| Quota (VERIFY)          | Free allowance                         | Runs that fit                                 |
| ----------------------- | -------------------------------------- | --------------------------------------------- |
| Firestore writes        | 20k / day                              | ~20 runs/day                                  |
| Firestore reads         | 50k / day                              | ~15 runs/day with 2 consoles open             |
| Firestore deletes       | 20k / day                              | ~25 resets/day                                |
| Gemini API requests/day | depends on model (VERIFY in AI Studio) | the limiting factor: plan ~5–10 real runs/day |
| Cloud Run vCPU-seconds  | monthly free allowance (VERIFY)        | ~25 min × 1 vCPU per demo                     |

## Levers if we get close to a limit

1. `GENAI_MODE=fake` for development; `real` only for demos and evals.
2. Raise the pump interval or use Firestore count aggregation instead of listing cases.
3. Lower `GEMINI_RPM` (the rate limiter spaces calls; 429s back off and fall back to policy).
4. Use a cheaper/higher-quota model for the classifier via `GEMINI_AGENT_MODEL`.
5. `MAX_ACTIVE_INCIDENTS=1` and `INCIDENT_TTL_MIN=30` already cap abuse of the public demo.
