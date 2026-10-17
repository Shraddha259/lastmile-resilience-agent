# Gotchas

> How to update: add a dated one-line entry (`YYYY-MM-DD — symptom — cause/fix`). Delete entries once the code makes them impossible.

- 2026-10-14 — Firestore rejects GeoJSON polygons ("invalid nested entity") — no nested arrays; geometry is `{type, points: [{lat, lng}]}`.
- 2026-10-14 — Emulator "Transaction lock timeout" — don't read the incident doc inside transactions (hot doc); never cancel a job mid-transaction (kill switch only cancels waiting jobs).
- 2026-10-14 — `firebase emulators:start` hangs on "downloading ...jar" in sandboxed shells — download the jar with curl into `~/.cache/firebase/emulators/`.
- 2026-10-14 — Live residents R-001/R-002 take minutes to finish in dev — `LIVE_RING_TIMEOUT_S` is not time-scaled; keep it small in `backend/.env`.
- 2026-10-14 — Leaflet divIcon badges render 12px wide — use class `lm-badge` (CSS sets width/height auto).
- 2026-10-14 — CI fails "types.gen.ts is stale" — run `make types` after editing `backend/app/models.py`.
- 2026-10-14 — Prettier must not touch `docs/PRD.md` or `types.gen.ts` — both are in `.prettierignore`.
- 2026-10-14 — A residents' risk score of 0 is valid (60–69, independent, upper floor, far from river).
- 2026-10-15 — Gemini API rejects unrestricted API keys from June 2026 — `deploy.sh setup` creates a key restricted to `generativelanguage.googleapis.com`.
- 2026-10-15 — Gemini free tier is best-effort and can drop to ~20 requests/day per model — quota exhaustion falls back to the rule-based policy; don't rely on it for judging.
- 2026-10-16 — Auth emulator logs `securetoken ... 400` in the browser — stale anonymous token from an earlier emulator session; harmless, the app signs in again.
- 2026-10-16 — React "destroy is not a function" / blank page — an expression-bodied `useEffect` returned `scrollIntoView()`, which newer Chrome makes a Promise; always use a block body.
- 2026-10-16 — Emulator REST reads return nothing — add `Authorization: Bearer owner` to bypass rules when inspecting data with curl.
- 2026-10-16 — With Auto-approve off, cases escalate as "No volunteer available" — every unapproved dispatch holds its volunteer (only 8); approve or reject quickly, or demo with Auto-approve on.
- 2026-10-16 — Test setup fails with emulator `409 Conflict` on the wipe — a previous test's job still holds a transaction; `fresh_db` now waits for jobs and retries.
- 2026-10-17 — Cloud Run logs `429 Too Many Requests` on a Gemini model — that model's quota is used up; switch `GEMINI_AGENT_MODEL` to one that answers 200 (D-044).
- 2026-10-17 — Many `decision failed` with `TimeoutError` — decisions wait behind classifier calls in the `GEMINI_RPM` queue; keep `AGENT_TIMEOUT_S` ≥ 60 and `GEMINI_RPM` near the real per-minute limit.
- 2026-10-17 — `job failed … 404 No document to update …/checkins/…` after a Reset — a leftover job from the deleted incident finished late; harmless. Press STOP ALL CALLS, wait ~1 min, then Reset.
- 2026-10-17 — Settings changed only in the Cloud Run console disappear after the next `deploy.sh backend` (`--set-env-vars` replaces all) — set them in `deploy.sh` / GitHub repo variables.
