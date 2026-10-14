# Open questions

> How to update: add `YYYY-MM-DD — question — owner/default`. When resolved, move the answer to `docs/DECISIONS.md` (or GOTCHAS) and delete the line here.

- 2026-10-14 — Are the PRD default model IDs available on the Gemini API free tier, and what are their daily request limits? — default: verify before M3 (BACKLOG 3.7).
- 2026-10-14 — Does the Gemini Live model work on the free tier for zh/en voice? — default: `LIVE_MODE=text` fallback at the M4 gate.
- 2026-10-14 — Exact Cloud Run free allowance for instance-billed (`--no-cpu-throttling`) services — default: min 0 / max 1 instances, budget alert.
- 2026-10-14 — Emergency number for the demo location — default `999` (PRD Q3).
- 2026-10-14 — Who reviews the machine-translated alert texts (zh, ms, ta, yue)? — default: flagged "machine translated" in UI.
- 2026-10-14 — Should `AUTO_APPROVE_DISPATCH` default to false once the approval UI lands (M5)? — default: yes, per PRD §7.
