# Chat-first assistant and access boundaries

After login, `/chat` is the default. The assistant’s welcome is assembled from the authenticated name, role and verified student section, with capabilities from the supplied manual. It does not invent a student’s marks or attendance at sign-in; those facts are fetched when asked.

## Student

The student guide (manual pages 15–18, sections 8.1–8.7) covers the student’s profile, course/teacher details, timetable, attendance, homework and assignments, exam schedules and marks, published progress reports, leave and notifications.

The current chatbot supports reading these permitted records, explaining documented procedures, and preparing drafts. It does **not** submit leave, homework or messages; change records; approve requests; manage users; or reveal other students’ private records. This distinction is displayed in the access panel and enforced by database views and the SQL validator.

Student prompts are personal (“my attendance”, “my marks”, “my timetable”). The server derives identity from the authenticated cookie and source profile. Supplying someone else’s name, user ID or an administrator role in chat does not change the identity used by the database.

## Faculty and Admin

Faculty reports remain restricted to assigned subjects/sections and their own staff records (manual pages 12–15). Administrators can read school-wide reports and use separate management screens; chat itself remains read-only (manual pages 8–12). School-management tools are collapsed in the administrator sidebar and absent from the student sidebar.

## Conversation quality and evidence

- New facts use SQL or cited manual retrieval; permission/capability explanations use the verified role policy.
- Report answers describe actual returned values in readable language. Missing rows do not become zero marks, failure or absence.
- “Summarize that” uses the last verified report belonging to the authenticated account and role. It does not call the model or database again or create a duplicate query audit event.
- Incomplete requests should receive one focused clarification; the assistant already knows the signed-in identity.
- Records, charts, SQL and supporting manual excerpts stay expandable so the main experience is a conversation.
- The Stop button cancels the current browser request. Provider/network failures surface as recoverable errors.
- Generated manual answers can still be inaccurate. Source IDs are validated against retrieved excerpts; users can inspect the original pages. No claim of zero model hallucinations is made.

## Verification

```bash
/home/jony/miniconda3/bin/python -m pytest tests_product -q
/home/jony/miniconda3/bin/python scripts/evaluate_chat_focus.py
node scripts/browser_chat_focus.mjs
```

The first command tests real PostgreSQL permissions plus mocked workflow cases. The live evaluation uses the configured OpenAI model and independently known sample records. The browser check uses real login credentials from the ignored `.runtime/demo-accounts.json` file and writes screenshots under `.runtime/chat-browser/`. It never prints passwords or API keys.

## Faculty access clarification and blank-answer fix

The manual’s role summary (page 1), faculty guide (pages 12–15), built-in reports (page 19), and security recommendations (page 22) support faculty working with assigned courses/sections and their logged-in identity. They do not explicitly grant unrestricted private access to every student or student leave approval. The implementation therefore preserves assigned-section rosters and assigned-subject academic reports, with own staff leave status. Administrator-only leave review is not broadened.

In this sample, Vijay Reddy teaches Science in both Grade 9-A and Grade 10-A. His permitted roster therefore happens to include all four sample students. That does not grant unrestricted school access: his exam marks view contains only the two Science results, and attendance contains only recorded Science periods. Missing subject attendance is not fabricated for the remaining students.

The screenshot’s empty bubbles were confirmed as stored `clarification` results with empty answer strings. The classifier now recovers clear faculty reporting requests to validated SQL, gives a useful role-aware question for genuinely ambiguous requests, and enforces nonempty text at response generation. Empty historical assistant messages are skipped in model context and shown with an explanatory fallback in the frontend.

Regression commands:

```bash
/home/jony/miniconda3/bin/python -m pytest tests_product -q
/home/jony/miniconda3/bin/python scripts/evaluate_faculty_chat.py
```
