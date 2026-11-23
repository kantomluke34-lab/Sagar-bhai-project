# Release evidence: Mechman CRM / lifecycle and UX hardening

- Source commit and reviewed diff: pending
- Build artifact digest and provenance: pending
- Deployment environment and standing authorization reference: existing main-branch Vercel/Contabo CI/CD authorized in this thread
- CI run and policy version: pending
- Owner, reviewers, date/time: Codex lead; UI/UX, backend/security, tester reviews; 2026-11-23 IST

| Gate | Exact command, link, or measurement | Result | Blocker or exception owner |
| --- | --- | --- | --- |
| Requirements and happy path | `PROJECT_BRIEF.md` | Defined | — |
| Failure paths and recovery | specialist audits | P0/P1 findings mapped | Lead |
| Lint, typecheck, build | `uv run ruff check mechman_bot tests`; `npm run build`; `git diff --check` | Passed | — |
| Unit, integration, contract, end-to-end | isolated PostgreSQL 16: `TEST_DATABASE_URL=... uv run pytest -q`; `npm test -- --run` | Passed: 52 backend tests, including PostgreSQL integration/concurrency; 20 frontend tests | — |
| Security and secrets | `npm audit --omit=dev`; admin mutation matrix tests; fail-closed webhook tests; no credential values logged | Passed; 0 npm vulnerabilities | — |
| Accessibility and UI states (viewport, assistive technology, motion setting, observed result) | 390/768/1024/1440 + keyboard pending | Blocked: live browser control unavailable during initial recon | UI reviewer |
| Query plan, migration, restore | additive `ALTER TABLE ... IF NOT EXISTS` and partial unique indexes exercised against isolated PostgreSQL 16 | Passed; rollback remains application-only and does not drop columns | — |
| Load, SLO and capacity | no scaling change; baseline unknown | Not claimed | Owner |
| IaC plan, cost and blast radius | no infrastructure change | N/A | — |
| Staging smoke and rollback rehearsal | pending | Pending | Lead |
| Canary comparison and live digest | pending | Pending | Lead |
| Post-deploy synthetic and telemetry window | pending | Pending | Lead |

## Decision
- Proceed, stop, or roll back: proceed to commit CI; stop before declaring release complete until CI and live smoke pass.
- Evidence for decision and remaining risk: backend, PostgreSQL, frontend, build, lint, dependency, security, tester, and UI review gates pass. Live responsive/browser evidence remains unavailable in this chat.
- On-call route and runbook: existing project deployment workflow; formal on-call is not documented.
- User-visible outcome: pending.
- Follow-up owner and due date: current task.
