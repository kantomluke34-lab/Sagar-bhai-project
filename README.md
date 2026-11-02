# Mechman WhatsApp bot and meeting CRM

A deterministic WhatsApp enquiry bot, custom meeting scheduler, and authenticated CRM dashboard for Mechman Solutions. The bot copy and routing are hard-coded from `mechmansolution.com`; no LLM is used at runtime...
## Included
..
- Natural A–F WhatsApp flow for Products, Services, Solutions, About, Contact, and Book a meeting.
- Open-ended qualification questions and a direct custom-booking link at the end of every branch.
- Operations modules and typed API contracts for the official Meta WhatsApp Cloud API integration.
- Simple Name, Phone, Email, and Date/Time meeting form with server-generated availability, business-hour validation, and conflict protection.
- Password-protected dashboard with analytics, meeting filters, status/stage management, CRM contacts, and audit history.
- Configurable WhatsApp reminders before calls and 1-day/3-day follow-ups, with editable timing, templates, and persistent delivery history.
- SQLite persistence with WAL mode, parameterized queries, transactions, schema migration, and message idempotency.
- Responsive React interface and a production multi-stage Docker image.
- Automated conversation, booking, auth, CRM, and migration tests.

See [BOT_FLOW.md](BOT_FLOW.md) for the WhatsApp conversation and [SITE_DECODE.md](SITE_DECODE.md) for the website-derived knowledge map.

## Local setup

Requirements: Python 3.10+ and Node.js 20+.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

cd portal
npm install
npm run build
cd ..

cp .env.example .env
```

Set a unique `JWT_SECRET` and strong `ADMIN_PASSWORD` in your environment. This project intentionally does not auto-load `.env`; export it with your process manager or shell. For a local shell:

```bash
set -a
source .env
set +a
mechman-dashboard
```

Open:

- Dashboard: `http://localhost:8000/login`
- Booking form: `http://localhost:8000/book`
- API documentation: `http://localhost:8000/docs`

The first run creates the configured administrator. Changing `ADMIN_PASSWORD` later does not silently overwrite an existing account.

## Reminders and follow-ups

Open **Settings** in the dashboard to configure:

- Whether reminders are enabled and how many minutes before the meeting they send (60 by default).
- Whether follow-ups are enabled and the comma-separated delays (1 and 3 days by default).
- The natural-language reminder and follow-up templates.

Supported placeholders are `{name}`, `{date}`, `{time}`, `{minutes}`, and `{days}`. Reminders only send for confirmed or scheduled meetings. Follow-ups send for confirmed, scheduled, or completed meetings. Each delivery is recorded with a unique meeting/type key, so a restart cannot send the same message twice.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `BOT_DATABASE` | `data/mechman-bot.db` | Conversations, CRM, meetings, users, and history |
| `PUBLIC_BOOKING_URL` | `http://localhost:5173/book` | Booking link sent by the bot |
| `CORS_ORIGINS` | local Vite origins | Comma-separated dashboard origins allowed to call the API |
| `JWT_SECRET` | none | Required; at least 32 characters |
| `JWT_EXPIRE_MINUTES` | `720` | Dashboard session lifetime |
| `DASHBOARD_AUTH_ENABLED` | `true` | Set to `false` only for a local dashboard demo without sign-in |
| `ADMIN_USERNAME` | `admin` | Initial administrator username |
| `ADMIN_PASSWORD` | none | Required; at least 10 characters |
| `MEETING_DURATION_MINUTES` | `60` | Slot length: 30, 45, 60, 90, or 120 |
| `TEAM_ALERT_NUMBER` | empty | Optional staff alert destination |
| `LOG_LEVEL` | `INFO` | Application logging level |

Current booking hours are Monday–Saturday, 9:00 AM–6:30 PM Asia/Kolkata. They are defined centrally in `mechman_bot/api.py` so the slot endpoint and server-side validation cannot drift apart.

## Development

Run the API and Vite separately for hot reload:

```bash
# terminal 1
mechman-dashboard

# terminal 2
cd portal
npm run dev
```

Vite proxies `/api` and `/healthz` to port 8000. Set `PUBLIC_BOOKING_URL=http://localhost:5173/book` during this workflow.

Quality checks:

```bash
ruff format --check .
ruff check .
pytest
cd portal && npm run build
```

Seed five idempotent local demo records:

```bash
set -a
source .env
set +a
.venv/bin/python scripts/seed_sample_data.py
```

## Docker

```bash
docker build -t mechman-crm .
docker run --env-file .env -p 8000:8000 -v mechman-data:/app/data mechman-crm
```

## Separate dashboard deployment

The `portal/` directory can be deployed as a Vite project on Vercel. Set
`VITE_API_URL` in Vercel to the public HTTPS URL of the FastAPI service, then add
the Vercel site origin to `CORS_ORIGINS` on the backend. The backend still needs
an always-on container host and a durable `/app/data` volume for SQLite.

The portal includes protected operations modules for the official Meta WhatsApp
Cloud API deployment:

- **Conversations** — inbound history, human takeover, return-to-bot, and manual replies.
- **WABA Status** — sender and Cloud API connection health.
- **Templates** — local drafts, Meta sync, editing, and approval submission.
- **Webhook** — callback URL, verification/signature readiness, and event flow.

These pages target the v3 backend endpoints. Typed request/response contracts live
in `mechman_bot/waba_schemas.py`. The Meta webhook, sender, and persistence handlers
must be supplied by the production WABA service; this repository no longer includes
a linked-device WhatsApp transport.

For a same-computer demo with the backend kept local, install a trusted local
certificate and run the API as a macOS per-user HTTPS service:

```bash
./scripts/install_local_https_demo.sh
```

The installer uses `mkcert`, serves FastAPI at `https://localhost:8443` in a
detached `screen` session, updates Vercel's production `VITE_API_URL`, and
redeploys the portal. Certificates and logs are stored under the ignored
`data/local-https/` directory. The Vercel demo can reach this API only from this
Mac because `localhost` resolves on the visitor's device. Restart the installer
after reboot. Stop the service with
`./scripts/uninstall_local_https_demo.sh`.

## Architecture

```text
mechman_bot/
  content.py       website-grounded hard-coded copy
  flow.py          deterministic conversation state machine
  api.py           public booking and authenticated dashboard API
  auth.py          bcrypt and JWT authentication
  storage.py       SQLite repository, CRM, meetings, and audit history
  notifications.py transport-neutral reminder/follow-up scheduler
  waba_schemas.py  typed Meta WABA request/response contracts
  web.py           FastAPI application lifecycle
portal/
  src/             React booking form and operations dashboard
tests/
  test_flow.py     transport-independent conversation tests
  test_api.py      booking, auth, CRM, and migration tests
  test_notifications.py scheduler timing and idempotency tests
```

## Production path

Use the official Meta WhatsApp Cloud API for production messaging. The local
conversation engine, booking flow, CRM, and notification queue are transport-neutral.
Connect the production WABA webhook and sender implementation to those services;
the dashboard contracts and operations pages are already structured for the v3 API.
