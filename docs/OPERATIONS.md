# Operations

For the production Docker stack on Ubuntu EC2, follow [EC2 deployment](EC2_DEPLOYMENT.md), including its host-operated backup procedure. The instructions below describe the original local host-process installation of Next.js, FastAPI, Celery worker and Celery beat, with PostgreSQL 17/pgvector and Redis in Docker.

## Processes and readiness

Use README launch commands for a local demo. `deploy/school-insight-{api,web,worker,scheduler}.service` provide restart-on-failure host service templates. Paths target this checkout and Conda base; adapt them before installing on a different machine. They are supplied templates, not globally installed services. Run exactly one scheduler. Redis/PostgreSQL must start before application jobs. Build `web/` before starting Next.js in production.

```bash
/home/jony/miniconda3/bin/python scripts/check_operations.py
```

This checks database, Redis, API and worker and reports the latest backup's restore status. A missing/unverified backup or one older than 36 hours makes the check fail. `GET /api/health` returns 503 if DB/Redis fail. Admin `GET /api/operations` exposes process counters and same-tenant audit events. Logs rotate under `.runtime/logs/operations.jsonl` at 2 MB with five backups. They contain request IDs, routes, status, durations and exception class names, not private question/SQL/exception bodies. Counters reset on process restart; audit records persist. Hook readiness into your own monitoring system for alerts; no external monitoring account is assumed.

## HTTPS

The public Caddy config is `deploy/Caddyfile`. Set `SITE_DOMAIN` to a domain you control and `SITE_CONTACT_EMAIL` for certificate issuance. Point DNS to the host, allow ports 80/443, and have the host Caddy service load this configuration. Keep API/PostgreSQL/Redis on loopback or a private network. Caddy proxies Next.js, including SSE with immediate flushing.

Set in `.env` before restarting the API:

```dotenv
COOKIE_SECURE=true
PRODUCT_WEB_ORIGINS=https://your-school-domain.example
```

The `.example` hostname is a placeholder, not a deployed site. HTTPS requires an actual domain and reachable host; no domain was supplied for this project. The existing machine may run Caddy for another service: merge reviewed site configuration rather than overwriting `/etc/caddy/Caddyfile` blindly. The app sends HSTS when secure cookies are enabled. Do not set Secure cookies for plain HTTP local development, because browsers will not send them there.

For isolated local TLS verification without modifying system trust:

```bash
caddy run --config deploy/Caddyfile.local --adapter caddyfile
```

This listens on `https://localhost:3443`, uses Caddy's internal CA, disables port-80 redirects, and does not install its CA globally. A test client can trust only `~/.local/share/caddy/pki/authorities/local/root.crt`. Public browser trust still requires a public certificate or explicit local trust installation.

## Backup and restore verification

```bash
/home/jony/miniconda3/bin/python scripts/backup_product.py --verify-restore
```

The backup contains a PostgreSQL custom-format dump of `school_ai`, uploaded PDFs and a SHA-256 manifest. Counts and dump share an exported PostgreSQL MVCC snapshot. Verification creates a **new randomly named database**, restores the dump, compares user/student/document/account counts and drops only that verification database. It never replaces the running school database. Direct local restore verification has been exercised successfully.

Celery beat schedules `insight.backup_daily` daily at **02:00 Asia/Kolkata**. The worker performs the backup and restore check. The current helper targets this installation's `chat_postgres_1` container, localhost:55433 and `.runtime/services.env`. Adapt backup tooling when moving the control database elsewhere. External tenant source databases need their own backup policies; the control backup does not dump independently managed tenant servers.

Default output is `.runtime/backups/<timestamp>`. Set `PRODUCT_BACKUP_DIRECTORY` to a mounted, separately protected storage location for durable copies. Same-disk backups help recovery from accidental changes but do not protect against losing the host. The app does not assume access to your cloud storage. Retention is operator-managed: there is no automatic backup deletion.

API keys and database connection secrets are deliberately excluded. Preserve `.env`, `.runtime/product.json`, `.runtime/services.env` and `.runtime/tenants.json` separately with appropriate access restrictions. Restoring to a different PostgreSQL cluster also requires recreating restricted login roles/grants using a trusted administrator. The verification restore uses the existing cluster's roles. Do not restore over production without an operator-reviewed recovery plan and a current backup.

## Updates

Back up first, install pinned dependencies in Conda base, run `scripts/migrate_product.py`, build the frontend, then restart the four application processes. Migration is additive to control metadata. Do not rerun the supplied SQL dump against an existing school database. Bootstrap explicitly refuses to overwrite an existing school schema.

Passwords remain local Argon2 hashes. Admin-issued recovery/setup links expire in 15 minutes and must be shared privately after verifying identity; no email integration is assumed. Changing/resetting a password revokes all sessions. Never copy `.runtime/demo-accounts.json`, API keys or recovery links into tickets or logs.

## Provider failures and optional services

An installed key does not guarantee remaining quota or access to every model. Model IDs are server allowlisted; choose a provider/model in the sidebar. Rate-limit errors explain how to recover without exposing provider exception content. Switching providers always starts a new conversation and is a user action.

LangSmith is optional. Keep tracing disabled for local-only operation. Set your key and explicitly publish evaluation results only if you intend to send those inputs/outputs to your LangSmith account. See EVALUATION.md. A successful local test is not a claim of a hosted LangSmith run or public HTTPS deployment.
