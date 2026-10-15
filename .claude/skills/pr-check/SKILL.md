---
name: pr-check
description: Pre-PR checklist for LastMile. Use before opening or updating a pull request, or when asked "is this ready to merge?". Runs lint/tests and checks the repo's hard rules against the current diff.
---

# PR check

Run these in order and report a short pass/fail table. Do not fix anything unless asked.

1. `git diff --stat main...HEAD` (or `git status` if nothing is committed) — list changed areas.
2. `make lint` and `make test`. Report failures with the first relevant error lines.
3. If `backend/app/models.py` changed: confirm `frontend/src/types.gen.ts` changed too (`make check-types`).
4. Hard rules on the diff (use `git diff`):
   - New writes to a case `status` outside `policy/state_machine.py` → FAIL (FR-1).
   - `incident_id` added as a tool/LLM argument → FAIL (FR-11).
   - Hard-coded model IDs, URLs or timeouts instead of `config.py` → FAIL.
   - `asyncio.create_task` / background work outside `worker.enqueue` → FAIL.
   - Logging of transcripts, phone numbers or passcodes → FAIL (NFR-S8).
   - Real-looking personal data or secrets → FAIL; also run `gitleaks dir . --redact`.
5. Requirement IDs (FR-x / AC-x / NFR-x) appear in new test names and in the PR title or commits.
6. If an ambiguity was resolved, `docs/DECISIONS.md` has a new D-xxx row.

Finish with: READY / NOT READY and the list of blocking items.
