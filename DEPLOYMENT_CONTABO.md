# Contabo backend and PostgreSQL deployment

The production split is:

- Vercel frontend: `https://mechman-crm.vercel.app`
- Contabo API: `https://api.207-180-203-160.nip.io`
- PostgreSQL: private Docker network only; port 5432 is not published

The `nip.io` hostname currently resolves to the Contabo IPv4 address and lets Caddy obtain a trusted certificate without waiting for a custom domain. Replace it with the final API domain later without changing the application architecture.

## Server prerequisites

- Ubuntu/Debian-compatible Contabo VPS with root SSH access.
- Ports 22, 80, and 443 permitted by the Contabo firewall.
- Docker Engine with the Compose plugin.
- Auto Backup enabled in Contabo; application-level database backups remain required.

This repository must be copied to its own `/opt/mechman-crm` directory. It must not share environment files, databases, Docker networks, volumes, or domains with Innovative Hair Studio.

## Production environment

Create `/opt/mechman-crm/.env` with mode `600`. Use newly generated values for the PostgreSQL password, JWT secret, and CRM admin password.

```dotenv
POSTGRES_DB=mechman
POSTGRES_USER=mechman
POSTGRES_PASSWORD=GENERATE_ON_SERVER
DATABASE_URL=postgresql+asyncpg://mechman:GENERATE_ON_SERVER@postgres:5432/mechman

APP_DOMAIN=api.207-180-203-160.nip.io
FRONTEND_ORIGIN=https://mechman-crm.vercel.app
PUBLIC_BOOKING_URL=https://mechman-crm.vercel.app/book
CORS_ORIGINS=https://mechman-crm.vercel.app

JWT_SECRET=GENERATE_ON_SERVER
JWT_EXPIRE_MINUTES=720
ADMIN_USERNAME=admin
ADMIN_PASSWORD=GENERATE_ON_SERVER
MEETING_DURATION_MINUTES=60

META_PHONE_NUMBER_ID=1395187090344267
META_WABA_ID=29459993996925480
META_API_VERSION=v26.0
WHATSAPP_ACCESS_TOKEN=
META_APP_ID=2545072705904292
WHATSAPP_WEBHOOK_VERIFY_TOKEN=
META_APP_SECRET=

CAMPAIGN_POLL_SECONDS=10
MEDIA_ROOT=/app/media
MAX_MEDIA_BYTES=104857600

NOTIFICATION_POLL_SECONDS=30
LOG_LEVEL=INFO
LOG_FORMAT=json
SLOW_REQUEST_MS=1000
```

Leaving the three WABA secrets blank intentionally disables outbound WhatsApp while CRM testing is in progress.

The `campaign_media` Docker volume stores uploaded media used by scheduled and recurring campaigns. Include it in server backup planning; do not delete it during routine deployments.

## Start and verify

```bash
cd /opt/mechman-crm
docker compose config -q
docker compose build app
docker compose up -d
docker compose ps
curl --fail https://api.207-180-203-160.nip.io/healthz
curl --fail https://api.207-180-203-160.nip.io/readyz
```

Expected readiness response:

```json
{"status":"ready","database":"ok"}
```

Then open `https://mechman-crm.vercel.app/login` and sign in with the generated CRM administrator password.

## Operational logging

Every service writes to stdout/stderr and uses Docker's `json-file` driver with five 10 MB files per container. This prevents an unbounded log file from consuming the VPS disk.

Application request logs are JSON and include:

- UTC timestamp and severity;
- logger and event name;
- request ID, method, path and status;
- client IP and duration in milliseconds;
- exception stack trace for failed requests.

Authorization headers, request bodies, WhatsApp message bodies, tokens, passwords, and app secrets are not logged.

Useful commands:

```bash
docker compose logs --since=15m app
docker compose logs --since=15m postgres
docker compose logs --since=15m caddy
docker compose logs -f --tail=100 app
docker compose ps
docker stats --no-stream
df -h
```

Filter errors when `jq` is available:

```bash
docker compose logs --since=1h --no-log-prefix app 2>&1 \
  | jq -R 'fromjson? | select(.level == "ERROR" or .level == "CRITICAL")'
```

Trace a reported request by copying its `X-Request-ID` response header and searching:

```bash
docker compose logs --since=24h app | grep 'REQUEST_ID_HERE'
```

PostgreSQL emits statements taking at least 750 ms, startup/shutdown events, and errors to stderr. It does not log every query or query parameter.

## Backups

Create a compressed logical backup:

```bash
install -d -m 700 /var/backups/mechman
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > /var/backups/mechman/mechman-$(date -u +%F-%H%M%S).sql.gz
```

Copy backups off-server and test restoration periodically. Contabo Auto Backup is useful disaster recovery, but it is not a substitute for PostgreSQL logical backups.

## WABA activation after CRM testing

1. Inject the three owner-held WABA secrets into `.env` and restart only the app:
   `docker compose up -d --force-recreate app`.
2. Set the Meta callback URL to `https://api.207-180-203-160.nip.io/webhook`.
3. Subscribe the app to the `messages` webhook field.
4. Sync templates and confirm `mechman_welcome` is actually `APPROVED`.
5. Send one owner-authorized template to a test recipient and verify the delivery webhook.
6. In CRM Contacts, record the test recipient's opt-in source/date, then create a one-recipient campaign and verify accepted, delivered, and read states.

No production WhatsApp send is part of the initial CRM deployment.

## Automated deployments

The GitHub `production` environment stores the Contabo SSH key and pinned host
key. Pushes to `main` deploy only after backend and frontend CI pass. The workflow
preserves `/opt/mechman-crm/.env`, takes a PostgreSQL backup before changing the
app container, verifies `/readyz`, and rolls back the app image on failure.

Vercel remains connected directly to the same GitHub repository with `portal/`
as the project root. It builds production from `main`; no Vercel token is stored
in GitHub Actions.
