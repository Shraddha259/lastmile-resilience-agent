# Open questions

> How to update: add `YYYY-MM-DD — question — owner/default`. When resolved, move the answer to `docs/DECISIONS.md` (or GOTCHAS) and delete the line here.

- 2026-10-16 — Which Live model ID does our key accept (config: `gemini-3.1-flash-live-preview`, listed as legacy; Google now recommends Gemini 3.8 Live), and does zh/en voice sound acceptable? — check with `scripts/check_models.py`, then one real call; default `LIVE_MODE=text`.
- 2026-10-15 — Cloud Run instance-based free allowance: pricing page says 240k vCPU-s / 450k GiB-s, free-tier page says 180k / 360k — default: assume the lower; min 0 / max 1.
- 2026-10-17 — What are the daily/per-minute limits for `gemini-3.5-flash-lite` on our key, and is a full judging window (19 Oct – 6 Nov) of runs within them? — check the Quotas page; set `GEMINI_RPM` just below the per-minute limit.
- 2026-10-14 — Emergency number for the demo location — default `999` (PRD Q3).
- 2026-10-14 — Who reviews the machine-translated alert texts (zh, ms, ta, yue)? — default: flagged "machine translated" in UI.
- 2026-10-14 — Should `AUTO_APPROVE_DISPATCH` default to false once the approval UI lands (M5)? — default: yes, per PRD §7.
