## What & why

<!-- One or two sentences. Link the BACKLOG task or issue. -->

## Requirement IDs

<!-- e.g. FR-12, AC-4. Every PR touches at least one (PRD §0.10). -->

## Phase

- [ ] P1 (MVP) — the only phase allowed on `main` until M7 is done
- [ ] P2 — goes to the `phase2` branch, not `main`

## Checks

- [ ] `make lint` passes
- [ ] `make test` passes (or explain what was skipped)
- [ ] Status changes go through `transition_case()` only (FR-1)
- [ ] No secrets, real names, phone numbers, or `.env` files
- [ ] `make types` run if `backend/app/models.py` changed
- [ ] `docs/DECISIONS.md` updated if I resolved an ambiguity

## Screenshots (UI changes)
