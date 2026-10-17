# Security review (M6)

> How to update: re-run the checks below before each release and update the date, results and findings.
> Scope: the P1 code on `main` and the deployed demo. This is a self-review, not a formal security approval.

_Reviewed 2026-10-17 (M3–M5 merged, M6 evals branch)._

## Checks (PRD §17)

| ID      | Requirement                     | How checked                                                                                                                                                     | Result                        |
| ------- | ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| NFR-S1  | No secrets in repo or history   | `gitleaks dir . --redact`; CI secret-scan job; only `.env.example` files tracked                                                                                | ✅ no leaks                   |
| NFR-S2  | Secrets in Secret Manager       | `deploy.sh`: `demo-passcode`, `gemini-api-key` via `--set-secrets`; key restricted to the Gemini API                                                            | ✅                            |
| NFR-S3  | Least-privilege runtime account | `lastmile-run`: datastore.user, secretmanager.secretAccessor, logging.logWriter only                                                                            | ✅                            |
| NFR-S4  | Keyless CI deploy               | Workload Identity Federation limited to `Shraddha259/lastmile-resilience-agent`; no keys in GitHub                                                              | ✅ design (setup pending)     |
| NFR-S5  | Clients read-only               | `infra/firestore.rules`: authenticated reads of incidents/residents/shelters/volunteers; all writes denied; everything else (incl. `voice_sessions`) denied     | ✅                            |
| NFR-S6  | Passcode + rate limit + caps    | Every `POST` router has `require_passcode`; SlowAPI per-IP limit; `MAX_ACTIVE_INCIDENTS=1`; 30-min TTL                                                          | ✅ (see F-1)                  |
| NFR-S7  | Synthetic data only             | Seed is generated, fictional, phone numbers masked; footer and "Synthetic data" labels                                                                          | ✅                            |
| NFR-S8  | No transcripts/phones in logs   | grep of all `log.*` calls: IDs, statuses, codes, latencies only                                                                                                 | ✅                            |
| NFR-S9  | CORS + WebSocket origin         | `ALLOWED_ORIGINS` for REST; `/ws/voice` rejects other `Origin`s (4403); one-time 10-min tokens bound to the call attempt                                        | ✅                            |
| NFR-S10 | AI discloses it is automated    | Voice prompt rule; guardrail eval g9 and a check on every eval call's first sentence                                                                            | ✅ (verify with `make evals`) |
| NFR-S11 | Budget + concurrency caps       | Budget alert required before deploy; max 8 concurrent check-ins; max 1 instance                                                                                 | ✅ (alert is a manual step)   |
| NFR-S12 | Prompt-injection hardening      | Resident speech, transcripts, context and snapshots are passed inside delimited DATA blocks; tools limited per status and validated in code; SITREP IDs checked | ✅ (verify with guardrail g4) |
| §23     | Passcode never stored           | Passcode is React state only: no localStorage, sessionStorage or cookies                                                                                        | ✅                            |

## Findings

| #   | Severity | Finding                                                                                                                                                                                                                    | Recommendation                                                                                                 |
| --- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| F-1 | Low      | The rate limiter keys on the **first** `X-Forwarded-For` entry, which a client can set itself, so one caller could spread requests over fake IPs. The passcode, the one-active-incident cap and the TTL still bound abuse. | VERIFY how Cloud Run's front end appends the client IP, then key on the address it adds (not the first entry). |
| F-2 | Info     | Anyone who opens the site gets an anonymous sign-in and can read resident, case and transcript data. Fine for a synthetic demo; **not** acceptable with real people.                                                       | Phase 3: real authentication and role-based rules before any pilot with real residents.                        |
| F-3 | Info     | The Gemini **free** tier may use prompts to improve Google products (D-001). Acceptable only because all data is synthetic.                                                                                                | Use a paid tier / Vertex AI with data-use terms reviewed before any real data.                                 |
| F-4 | Info     | `/api/health` shows model names and AI counters publicly. No secrets, useful for judges.                                                                                                                                   | Keep; remove counters in a production build.                                                                   |

## Not in scope

Penetration testing, dependency CVE audit (`npm audit` / `pip-audit`), and a formal Valtech or client security review.
Any real-world use needs the relevant security and data-protection owners to review first.
