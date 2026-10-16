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
