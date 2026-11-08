# API

FastAPI listens on `127.0.0.1:8100`. Browsers use Next.js `/api/*` proxy routes on port 3000. OpenAPI is served at `/api/docs` and `/api/openapi.json`. Most routes require an `insight_session` cookie; unauthenticated access returns 401. Admin routes return 403 for other roles. Inputs reject unexpected fields.

| Method/path | Purpose |
|---|---|
| GET `/api/health` | Database and Redis readiness; 503 on failure |
| POST `/api/auth/login` | `{username,password,tenant_id?}`; default tenant `school-demo`; sets cookie |
| POST `/api/auth/logout` | Revoke current session and clear cookie |
| GET `/api/auth/me` | Public authenticated identity; no password or source private IDs |
| POST `/api/auth/change-password` | `{current_password,new_password}`; 12–200 character new password; revokes sessions |
| POST `/api/auth/reset-password` | `{token,password}`; consume one-time recovery token; rate limited |
| GET `/api/chat/bootstrap` | Role-aware welcome, capabilities, verified profile and prompts |
| POST `/api/chat/stream` | `{question,provider?,model?,conversation_id?}`; SSE response |
| GET `/api/settings` | Configured provider/model allowlists; no keys |
| GET `/api/overview` | Live identity-scoped metrics and chart rows |
| GET `/api/sources` | Current tenant source metadata |
| GET `/api/schema` | Admin catalogue or redacted reporting-view catalogue |
| GET `/api/conversations` | Current account's saved conversation list |
| GET `/api/conversations/{id}` | Owned conversation messages |
| DELETE `/api/conversations/{id}` | Delete owned conversation and its dependent records |
| GET `/api/history` | Current account's query history |
| GET `/api/analytics` | Current account's query usage analytics |
| POST `/api/feedback` | `{message_id,rating}`; owned assistant message, rating -1/0/1 |
| GET `/api/documents` | Tenant documents and ingestion state |
| POST `/api/documents` | Admin multipart `file` PDF upload, max 15 MB; queues ingestion |
| POST `/api/documents/{id}/retry` | Admin retry for tenant's failed document |
| GET `/api/documents/{id}/file` | Open tenant's original PDF; page navigation handled by browser fragment |
| GET `/api/team` | Admin list of app accounts in own tenant |
| GET `/api/team/source-users` | Admin verified redacted source directory |
| POST `/api/team/provision` | Admin `{source_user_id}`; returns account ID and one-time setup path |
| PATCH `/api/team/{id}` | Admin `{active}`; cannot disable own access |
| POST `/api/team/{id}/reset` | Admin one-time recovery path for same-tenant account |
| GET `/api/operations` | Admin process counters and same-tenant audit events |

## Stream protocol

Each event is `event: <type>`, followed by JSON in `data:` and a blank line. Clients must check for both HTTP failures and SSE `error` events after an HTTP 200.

```text
event: conversation
data: {"id":"conversation-uuid"}

event: stage
data: {"node":"intent_classification"}

event: answer_delta
data: {"target":"answer","text":"New generated text"}

event: report
data: {"sql":"...","columns":["total"],"rows":[{"total":4}],"truncated":false,"limit":200,"cached":false}

event: result
data: {"kind":"sql","answer":"...","report":{},"documentation":null,"message_id":"...","conversation_id":"..."}
```

Event order depends on route; SQL/RAG/hybrid do not necessarily produce every event. `answer_delta.target` is `answer` or `documentation`; hybrid manual text uses `documentation`. `result` is the authoritative final response, including source SQL/RAG/HYBRID/SUMMARY/ASSISTANT, provider/model, access scope, elapsed time and visualization metadata. Citations include document ID/name, page, section and exact supporting excerpt. SSE errors contain a safe detail and conversation ID. The workflow has a 120-second overall timeout. Cancel by aborting the fetch; the UI does not treat a cancelled response as a completed answer.

Common failures: 401 expired session, 403 role/origin restriction, 404 unowned resource, 409 provider switch within an existing conversation or incompatible lifecycle state, 413 large body/PDF, 415 unsupported upload, 422 invalid request/model, 429 rate limit, 503 unavailable dependency. SQL validation failures never grant broader access. Rate-limit/provider exceptions are mapped to safe messages instead of exposing raw SDK or database exceptions.
