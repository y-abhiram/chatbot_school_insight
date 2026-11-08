# School Insight

A working, read-only AI assistant for the supplied school PostgreSQL database and 24-page user manual. The application opens into a role-aware conversation at **http://127.0.0.1:3000/chat**. The separate dashboard is at **/overview**.

## Start on this machine

For **AWS EC2 with Docker and HTTPS**, use the [EC2 deployment guide](docs/EC2_DEPLOYMENT.md). It includes isolated database import, runtime secrets, persistent volumes, backups and local Docker verification. The commands below retain the original host-process setup.

Use **Conda base** for the local setup. PostgreSQL 17 with pgvector and Redis run in Docker; the API, frontend, worker and scheduler run directly on the host. Production containers use `compose.production.yml` separately.

Open four separate terminals and leave each running. Docker must be running before starting Terminal 1.

**Terminal 1 — database, Redis, and API:**

```bash
cd /home/jony/Documents/chat
bash scripts/product_services.sh
bash scripts/run_product_api.sh
```

**Terminal 2 — website:**

```bash
cd /home/jony/Documents/chat/web
npm run build && npm run start
```

**Terminal 3 — background worker:**

```bash
cd /home/jony/Documents/chat
bash scripts/run_product_worker.sh
```

**Terminal 4 — scheduler:**

```bash
cd /home/jony/Documents/chat
bash scripts/run_product_scheduler.sh
```

Once the API and website are ready, open **http://127.0.0.1:3000/chat** and sign in using the local demo credentials below. Ask **“How many students are there?”** An administrator should receive **4** from the supplied sample data.

Python launch scripts use `/home/jony/miniconda3/bin/python`. API: `127.0.0.1:8100`; frontend: `127.0.0.1:3000`. The API is proxied through Next.js, so frontend provider keys are unnecessary. Stop a foreground process with Ctrl+C. Host service templates are in `deploy/`; see [operations](docs/OPERATIONS.md).

## Accounts and provider keys

Local demo credentials are in **`.runtime/demo-accounts.json`**, readable only by their owner. Usernames and roles come from the supplied source database. App passwords were generated separately and stored as Argon2 hashes in `insight_app.accounts`; the source's example password hashes were not used or changed. Keep the credential file private.

View the credentials locally:

```bash
cat /home/jony/Documents/chat/.runtime/demo-accounts.json
```

Administrators can provision active source users and issue single-use, 15-minute setup/recovery links under **School workspace → Team management**. Share links privately with the verified account holder. Everyone can change their own password in **Account settings**. Changing or resetting a password revokes existing sessions. Recovery does not send email automatically.

Keep existing API keys in `.env`; do not replace it with the example. `python scripts/configure_ai.py` provides masked local configuration. OpenAI, Gemini and Groq appear in the chat's model selector. Configure exact allowed model IDs through `OPENAI_MODELS`, `GEMINI_MODELS` and `GROQ_MODELS`. Provider changes start a new conversation. Quota failures are visible; the application does not silently send a conversation to another provider.

## Implemented behaviour

- Natural-language SQL reports, manual answers with original page citations, and combined answers through LangGraph.
- Personalised welcome, suggested questions, follow-ups, report summaries, drafts and recommendations.
- Actual model response streaming for conversational/manual text; SQL results appear only after validation and execution. SQL summaries are calculated from real rows.
- Interactive tables, sorting/search/pagination, CSV export, charts, inspectable executed SQL, copy/regenerate, feedback and persistent private conversation/query history.
- Responsive chat and overview dashboard, loading/cancellation/error/empty states, model selection, account settings, source/schema inspection and PDF ingestion status.
- Student access to their own records; faculty access to assigned sections/subjects and their own leave; administrators get school-wide reports. The assistant cannot edit school records, approve leave, send messages or schedule events.
- Independent organisation database connections, reviewed reporting-view contracts, tenant-specific documents and app accounts. See [onboarding](docs/ONBOARDING.md).
- Single-use password recovery, verified account provisioning, audit events, health/readiness checks, rotating operational logs, daily backup scheduling and verified restore tooling.

## Installation and initialisation

Dependencies for the current product are pinned in `requirements.txt`:

```bash
/home/jony/miniconda3/bin/python -m pip install -r requirements.txt
cd web
npm ci
```

On a **new** local installation, start data services, then run `python scripts/bootstrap_product.py` and `python scripts/ingest_manual.py`. Bootstrap refuses to import into a database that already contains the school schema. The supplied dump drops/recreates `school`; never execute it against valuable existing data. This checkout is already initialised. For additive updates use:

```bash
/home/jony/miniconda3/bin/python scripts/migrate_product.py
```

The school schema has 29 tables and four original report views. The catalogue is discovered from PostgreSQL, not guessed from the PDF. `docs/verified-schema.json` records the imported schema. Runtime secrets, PDFs, models, backups and logs remain under `.runtime/` and are excluded from source control.

## Verification

```bash
/home/jony/miniconda3/bin/python -m pytest tests_product -q
/home/jony/miniconda3/bin/python scripts/evaluate_acceptance.py --provider openai --model gpt-5.4-mini
LIVE_BROWSER_AI=1 node scripts/browser_chat_focus.mjs
/home/jony/miniconda3/bin/python scripts/backup_product.py --verify-restore
/home/jony/miniconda3/bin/python scripts/check_operations.py
```

The final [verification report](docs/verification.json) records 86 passing automated tests, 48 browser checks and 17/17 required question checks across OpenAI and Gemini. Gemini is configured as the current demo default; all providers remain selectable.

Live evaluations require an available provider quota and incur API usage. See [evaluation](docs/EVALUATION.md) for expected-result methodology and recorded results. Browser checks use the locally installed Chromium path, overrideable through `CHROMIUM_BIN`. Use `browser_chat_focus.mjs`, `browser_faculty_focus.mjs` and `browser_completion.mjs` for the current product.

## Documentation and deployment

- [Architecture and security boundaries](docs/ARCHITECTURE.md)
- [API and streaming protocol](docs/API.md); live OpenAPI: `http://127.0.0.1:8100/api/docs`
- [Operations, HTTPS, backup and restore](docs/OPERATIONS.md)
- [Onboarding another organisation](docs/ONBOARDING.md)
- [Evaluation and LangSmith publication](docs/EVALUATION.md)
- [School role scope](docs/CHAT_ACCESS.md)

Public HTTPS needs your domain/DNS and host configuration; follow [EC2 deployment](docs/EC2_DEPLOYMENT.md). LangSmith publication needs your own LangSmith API key and explicit opt-in; local evaluation works without it. Neither external account/domain activation is implied by the included configuration.

Cloud prompts contain the question, bounded recent conversation, permitted schema and relevant manual excerpts. SQL report narratives use local deterministic summaries; follow-up history can contain names or prior report facts. Select providers according to your school's data-sharing requirements. Trace publication can include question/answer/report content and is disabled by default.

The application code is in `product/` and `web/`; its tests are in `tests_product/`. Obsolete prototype code, launch scripts and virtual environments have been removed. Keep `.runtime/` for database connection settings, credentials, indexed documents, model files and backups.

## Requirements and implementation limits

The supplied request asks for a chatbot that answers questions using the database test data and accompanying manual. The manual describes school workflows, including writes, and requires student/faculty access to be filtered by the logged-in user (page 22, section 11.5). It does not specify approved reporting views or a read-only chatbot; these are implementation choices. The current assistant answers permitted record questions and explains manual workflows; executing school-record changes was not requested and is not implemented.

Ambiguous questions may need clarification. Unsupported queries and provider failures are operational limits, not customer requirements. The saved acceptance checks cover named examples, not every possible input. Historical verification reports retain their original results; rerun the checks above to establish current readiness.
