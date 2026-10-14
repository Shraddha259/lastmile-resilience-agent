# Claude notes — decisions

> How to update: add a dated one-line entry at the top (`YYYY-MM-DD — decision — why`). Full design decisions go in `docs/DECISIONS.md`; this file is for working agreements about how we use Claude in this repo.

- 2026-10-14 — Claude config is shared via `CLAUDE.md` + `.claude/settings.json`; personal tweaks go in `.claude/settings.local.json` (gitignored) — keeps team behaviour consistent.
- 2026-10-14 — Claude may run lint/test/build without asking; deploys and `gcloud` always ask — deploys cost money and touch shared infra.
- 2026-10-14 — Claude cannot read `.env*` files (including `.env.example`); variables are documented in `backend/app/config.py` — keeps secrets out of context.
- 2026-10-14 — Use the `pr-check` skill before PRs and the `prd-reviewer` agent for policy/agent/dispatcher changes.
