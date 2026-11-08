# Onboard another organisation

A tenant can use a separate PostgreSQL database and its own PDFs without editing the graph or query engine. This is an operator workflow: access policies require a reviewed business decision and cannot safely be inferred from arbitrary tables.

1. Prepare redacted reporting views in a dedicated schema. Set `security_barrier=true`. Apply row restrictions using transaction-local `insight.tenant`, `insight.role` and `insight.user_id`. An absent/unknown identity must return no rows. SQL messages never choose these values; the API supplies the authenticated identity.
2. Create a restricted query login with SELECT on those views and schema USAGE only. It must not own/create objects, have superuser/role/database-creation privileges, or have raw business-table/write access. Avoid privileged or side-effecting view functions. Review every view for personal data and secret columns.
3. Expose a redacted `users` view with `user_id`, `username`, `first_name`, `last_name`, `role_name`, `is_active`. The source directory is authoritative. This release supports Admin/Faculty/Student role keys; another business may map reviewed roles onto those capability levels through its manifest.
4. Create a manifest based on `deploy/source.example.json`. Supply explicit `scope`, `can`, `cannot` and suggested `questions` for each supported role. `adapter: generic` disables school-specific profile queries and SQL shortcuts. Choose a new tenant ID, never `school-demo`.
5. Set a server-side environment variable containing the restricted connection URL. Register it without putting the secret URL in command arguments:

```bash
python scripts/onboard_source.py --manifest /private/path/organisation.json --query-url-env ORGANISATION_QUERY_URL
```

The script verifies the role/view contract, refuses an existing tenant ID and never imports or resets source data. Metadata is stored in `insight_app.sources`; the URL is atomically written to owner-only `.runtime/tenants.json`, never returned in public APIs. Treat this file like `.env`.

6. Bootstrap the first verified source administrator locally:

```bash
python scripts/provision_account.py --tenant your-organisation --source-user-id 101
```

This prompts for a password without echoing it and derives the username/role/name from the verified source identity. It does not insert users into the source database. The administrator can then provision remaining source users through Team management and issue one-time setup links.

7. On the sign-in screen, enter the organisation ID, source username and app password. Every authenticated request rechecks active status and role against the tenant's source directory. A revoked or changed role fails closed. Queries use this tenant's own engine and catalogue; the generic overview counts only permitted views. Upload PDFs after logging in as that organisation's administrator; retrieval and original PDF access are tenant-scoped.

8. Test at least two identities and a forbidden record before accepting the source. `tests_product/test_onboarding.py` creates a separate temporary business database, registers it, proves customer isolation, checks login/welcome/dashboard/document isolation, and tests immediate source deactivation. It removes only its own test objects.

## Limits

Manifest descriptions do not enforce row permissions: reviewed PostgreSQL views do. The application validates SELECT SQL and enforces a read-only transaction, but safe view definitions and grants remain a source-owner responsibility. Source changes require refreshing the application catalogue/restarting the API after review. Do not register a raw database with broad privileges and assume the chatbot can invent safe policies. The source registry is intended for trusted local administrators; arbitrary browser-supplied database URLs are not accepted.

The school UI branding and the three role keys remain part of this MVP. New business-specific experiences or a different identity-role model can extend the adapter interface. External source backups are the organisation's responsibility; see OPERATIONS.md.
