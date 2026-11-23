# Project brief: Mechman CRM lifecycle and UX hardening

## Outcome and boundaries
- User outcome and primary journey: administrators can build DM flows, manage Meta templates, schedule campaigns, understand delivery outcomes, and safely retire records through consistent, accessible interfaces.
- Repository, commit, service, environment: `kantomluke34-lab/Sagar-bhai-project`, baseline `7ebd998`, React portal on Vercel and FastAPI/PostgreSQL on the authorized Contabo production service.
- In scope / out of scope: DM Flows, Campaigns, Templates, their API/repository/data paths, authorization, concurrency, failure states, and responsive UX. No new infrastructure tier, CAM redesign, WABA credential rotation, or destructive purge.
- Budget, timeline, data class, residency, allowed external actions: preserve recipient PII and consent/delivery audit history; no paid service changes. Code, tests, push, and the existing scoped CI/CD deployment are authorized by the user in this thread.
- Production deployment authorization policy and expiry: repository main-branch CI/CD and existing Contabo/Vercel deployment path only; no database destruction or credential changes.

## Current system evidence
- Entry points and request/data flow: `portal/src/pages/{DmFlows,Campaigns,Templates}.jsx` → `mechman_bot/api.py` → `repository.py`/PostgreSQL → `waba.py`/Meta; delivery results return through `webhook.py`.
- Existing tests, CI, IaC, monitoring, incidents: pytest, Vitest, Vite build, PostgreSQL CI integration, GitHub Actions deployment, `/readyz`; Campaign #4 exposed misleading completion and sender-throttle handling.
- Baseline traffic, latency, error rate, data size/growth, cost: unknown; no scaling component is justified by this change.
- SLO, RPO, RTO, peak and failure assumptions: not formally defined. Preserve current deployment rollback and database backup path; schema changes are additive.
- Unknowns and how they will be resolved: live browser automation is temporarily unavailable; responsive/keyboard acceptance remains a release gate and must be recorded in `RELEASE_EVIDENCE.md`.

## Requirements and acceptance examples
| Requirement | Happy path example and observable result | Failure or recovery example | Owner | Proof |
| --- | --- | --- | --- | --- |
| Truthful campaign lifecycle | all accepted → Completed; mixed failures → Finished with failures | all failed never displays plain Completed | Backend + frontend | unit/integration/UI test |
| Safe campaign removal | terminal campaign archives and disappears from active list while audit remains | running campaign returns 409 and remains intact | Backend | PostgreSQL integration test |
| Secure mutations | admin can mutate target resources | non-admin receives 403 | Security | endpoint matrix |
| Webhook authenticity | valid signed Meta webhook is processed | missing secret/signature fails closed | Security | webhook tests |
| Template submission correctness | one draft produces one Meta submission | concurrent request cannot submit twice | Backend | concurrency test |
| Consistent UX | stable action groups/cards/drawers across target routes | dirty close/destructive actions require confirmation | UI/UX | interaction + viewport checks |

## Phases
| Phase | Goal | Scope | Required inputs | Happy path | Failure paths | Verification | Recovery/rollback |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Discover | Trace every visible control to persistence/external result | live screenshots, code, endpoints, tests | current source and production evidence | complete lifecycle map | missing live access explicitly recorded | specialist audits | no mutation |
| Design | Define smallest safe lifecycle and UI contracts | soft archive, role matrix, truthful statuses, shared interaction primitives | audit findings | contracts map to existing architecture | destructive purge and speculative infrastructure rejected | reviewed brief | revise before schema/code |
| Build | Implement security, lifecycle, template, and UI phases | additive schema, API/repository/UI changes | accepted design | admin journeys work end-to-end | races, stale state, Meta faults are explicit | focused tests per phase | additive fields; prior code remains readable |
| Review and test | Independent correctness/security/UX review | backend, frontend, PostgreSQL, accessibility | built revision | happy paths and highest-risk failures pass | any P0/P1 blocks release | canonical gates | patch or stop |
| Release and observe | Deploy exact reviewed commit through existing CI/CD | Vercel/Contabo | green gates and authorization | live routes and readiness healthy | CI/smoke failure rolls back/stops | run link, live smoke | existing CI rollback |

## Architecture decisions
- Simplest viable design and measured trigger for added components: retain the monolith and PostgreSQL; no cache, queue, replica, partition, or shard is justified.
- API, data, transaction, consistency and authorization invariants: database role is authoritative; high-impact mutations require admin; transitions lock rows; campaign removal is soft archive; external submissions use durable intermediate states.
- Load balancer, cache, replication, partition or shard decision and tradeoff: no change.
- UI/UX states and accessibility requirements: one primary action per surface, grouped secondary/destructive actions, 44px touch targets, dialog semantics/focus return, surface-scoped alerts, truthful non-color-only status labels.
- Rollout, migration, failover, and rollback path: additive nullable/defaulted columns first; application tolerates existing rows; CI deploys same commit; rollback must not drop new columns.
- Independent reviewers and stop conditions: UI/UX designer, backend/security reviewer, and tester; any unresolved forged-webhook, duplicate-send, audit-loss, or misleading-terminal-state defect blocks release.
