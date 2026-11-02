# Mechman Sales Meeting CRM

A focused, single-administrator CRM for Mechman Solutions. It joins the official Meta WhatsApp Cloud API, the bilingual CAM Assistant flow, contact and meeting management, an internal calendar, message history, manual agent takeover, Meta template administration, and scheduled reminders/follow-ups.

This repository is independent from Innovative Hair Studio. It contains no IHS branding, data, credentials, deployment configuration, or hair-studio domain modules.

## Included modules

- Official WABA webhook with GET verification, `X-Hub-Signature-256` validation, and idempotent message ingestion.
- English/Gujarati deterministic CAM Assistant based on `Mechman CAM Assistant.html`.
- Guided pricing and product-knowledge flows for software, post-processors, and training.
- Persistent inbound, bot, administrator, template, reminder, and follow-up message logs.
- Per-conversation **Take Over** and explicit **Return to Bot** controls.
- Free-form admin replies only inside Meta's 24-hour customer-service window.
- Approved-template sending outside the service window.
- Local draft, submission, status sync, and safe versioning for Meta templates.
- Contact and sales-meeting CRM with stage, status, assignment, notes, and audit history.
- Public booking form with server-calculated availability and conflict protection.
- Internal month calendar; no Google or Outlook dependency.
- Configurable meeting reminders and 1/3-day follow-ups with exactly-once delivery records.
- Single administrator authentication with bcrypt and JWT.
- Async PostgreSQL with SQLAlchemy 2.
- React/Vite portal using the Mechman navy, steel, amber, and industrial control-panel design language, deployed separately on Vercel.
- Backend-only Docker Compose deployment for Contabo with PostgreSQL 16 and Caddy-managed HTTPS.
- Structured JSON application, request, webhook, scheduler, Caddy access, PostgreSQL slow-query, and bounded Docker logs.

Explicitly excluded: invoices, quotations, packages, broad ERP workflows, marketing campaigns, multi-role access, and all IHS-specific features.

## Production WABA configuration

Non-secret asset identifiers from the owner-approved handoff are supplied as defaults:

| Setting | Value |
|---|---|
| Graph API | `v26.0` |
| Phone number ID | `1395187090344267` |
| WABA ID | `29459993996925480` |

The following values are secrets and must only be injected through the Contabo server environment or another approved secret store:

- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_WEBHOOK_VERIFY_TOKEN`
- `META_APP_SECRET`

No production token or app secret is included in this repository.

## Local setup

Requirements: Python 3.11+, Node.js 20+, PostgreSQL 16.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'

cd portal
npm install
npm run build
cd ..

cp .env.example .env
```

Set a local PostgreSQL URL, a unique `JWT_SECRET`, and a strong `ADMIN_PASSWORD`, then run:

```bash
set -a
source .env
set +a
.venv/bin/mechman-dashboard
```

Open `http://localhost:8000/login`. The public booking form is at `/book` and API documentation is at `/docs`.

The application creates the initial schema and administrator on first startup. Changing `ADMIN_PASSWORD` later does not silently overwrite an existing administrator password.

## Main routes

| Portal | API |
|---|---|
| Dashboard | `/api/dashboard/analytics` |
| Meetings | `/api/meetings` |
| Calendar | `/api/meetings?date_from=…&date_to=…` |
| CRM Contacts | `/api/crm/contacts` |
| WhatsApp Inbox | `/api/conversations` |
| Message Templates | `/api/templates` |
| Reminder Settings | `/api/settings/notifications` |
| Booking Form | `/api/public/slots`, `/api/public/meetings` |
| Meta Webhook | `/webhook` |

## WhatsApp takeover behavior

1. The assistant handles incoming messages by default.
2. Incoming and outgoing messages are persisted before/after processing.
3. Selecting **Take Over** pauses bot replies for that conversation.
4. The administrator may send free-form messages during the 24-hour service window or an approved template when permitted by Meta policy.
5. Selecting **Return to Bot** resumes automation. There is no automatic timeout.

## Meta template behavior

- Draft and rejected templates may be edited.
- Pending and approved templates are immutable locally; create a new version to change their content.
- **Submit to Meta** calls the WABA template endpoint.
- **Sync Meta** imports/updates status, category, content, ID, and rejection reason.
- Only templates with `APPROVED` status are offered in the inbox.
- The handoff's `mechman_welcome` template can be imported with **Sync Meta** after production secrets are configured. It must not be sent until Meta reports it as approved.

## Validation

```bash
.venv/bin/ruff check mechman_bot tests
.venv/bin/pytest
cd portal && npm test && npm run build
```

An optional real-PostgreSQL smoke test runs when `TEST_DATABASE_URL` is supplied:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/testdb \
  .venv/bin/pytest tests/test_postgres_integration.py
```

## Contabo deployment

See [DEPLOYMENT_CONTABO.md](DEPLOYMENT_CONTABO.md). Deployment deliberately stops before entering secrets into Meta or sending a production test message; those steps require the owner-approved values and external account access.

Current deployment targets:

- Frontend: `https://mechman-crm.vercel.app`
- Backend: `https://api.207-180-203-160.nip.io` (becomes available after the Contabo stack is installed)

## CI/CD

`.github/workflows/ci-cd.yml` runs backend lint/tests against PostgreSQL 16 and
frontend tests/builds for every pull request and every push to `main`.

After both jobs pass on `main`, GitHub Actions:

1. synchronizes the release to `/opt/mechman-crm` without touching `.env`;
2. creates a compressed PostgreSQL backup;
3. builds an immutable image tagged with the Git commit SHA;
4. waits for the container health check and public `/readyz` response; and
5. automatically restores the previous image if deployment fails.

The frontend is deployed independently by the existing Vercel Git integration.
The Vercel project uses `portal/` as its root, deploys `main` to production, and
provides `VITE_API_URL` through the Vercel environment settings.
