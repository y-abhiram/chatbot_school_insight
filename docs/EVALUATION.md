# Evaluation

The original 17-question dataset is defined in `product/evaluation.py`. The saved, independently revalidated coverage report is **`docs/evaluation/acceptance-matrix.json`**: **17/17 passing cases across OpenAI and Gemini**. This is provider coverage, not a claim that every model passes every question or that all cases succeeded in one uninterrupted run. Per-case provider, model, raw response, checks, independent expected rows and source report are recorded.

OpenAI `gpt-5.4-mini` supplied the passing SQL and manual cases in `acceptance-results.json`; Gemini `gemini-2.5-flash` supplied the final lowest-attendance, progress-report and hybrid validations in `gemini-acceptance-results.json`. OpenAI daily request limits prevented further calls during the final run. Individual reports retain failures instead of rewriting them as successful calls. The combined report re-executes reference SQL and checks saved live outputs again.

## Method

For each SQL question, the evaluator executes a separately authored reference query against the supplied `school` source using a local operator connection. The assistant independently generates SQL against permission-scoped `insight` views. Requested projection names are appended to benchmark prompts for an inspectable comparison; result order and count-column aliases do not affect equality. Required projected values and row counts must match; extra presentation columns are ignored. No database answer is mocked.

RAG checks require nonempty answers, relevant cited pages, exact citation IDs/page/excerpt matches against the actual indexed chunks, and essential documented concepts. Hybrid checks validate SQL and document evidence separately; explanatory concepts can appear across the deterministic data summary and manual explanation. These are automated provenance/relevance/content checks, not proof that a probabilistic model can never misinterpret text. Original page excerpts remain inspectable.

Fixes discovered by evaluation include exact Pass/Fail result literals, avoiding unnecessary count clarification, preserving lowest/highest constraints in rewritten SQL requests, retrieval of procedural sections rather than general introductions, and including documented progress-report calculation/publishing steps.

## Reproduce

```bash
python -m pytest tests_product -q
python scripts/evaluate_acceptance.py --provider openai --model gpt-5.4-mini
python scripts/evaluate_acceptance.py --provider gemini --model gemini-2.5-flash --ids 5,15,17 --output docs/evaluation/gemini-acceptance-results.json
python scripts/combine_evaluations.py docs/evaluation/acceptance-results.json docs/evaluation/gemini-acceptance-results.json
```

`--resume` reuses passing cases only for the same provider/model, then retries missing/failed cases. Live runs use real account quota and can fail due to limits. Transient evaluation retries are bounded. Run the full dataset with any configured provider/model to measure that model independently; an API key alone is not an accuracy guarantee. Never substitute benchmark answers for real chatbot execution.

## Functional and operational checks

The automated suite covers SQL injection and prohibited functions/casts/schemas, real row scope for each role, source-user deactivation, role changes, cross-account conversations/feedback, cross-tenant sources/documents, a second actual PostgreSQL business database, verified role provisioning, one-time/expired recovery tokens, session revocation, secure cookies, streamed partial objects and SSE, request limits, bounded SQL repair, fabricated citation rejection, LangSmith publication contracts and safe provider errors.

The latest handover details are in `docs/verification.json`. Browser and operational proof is captured locally without publishing credentials:

| Check | Evidence |
|---|---|
| Role-aware chat and mobile interactions | `.runtime/chat-browser/results.json` — 26 checks |
| Overview, management and password UI | `.runtime/completion-browser/results.json` — 22 checks |
| Actual streaming before final result | `.runtime/stream-verification.json` — live Gemini deltas |
| Verified backup/restore | `.runtime/backups/*/manifest.json` |
| Current readiness | `python scripts/check_operations.py` |

The API is run with the frontend production build, not a static visual prototype. The local HTTPS endpoint is checked with certificate hostname verification and the Caddy local CA; secure-cookie handling is tested independently. A queued Celery backup was consumed by the real worker and restored successfully. Public DNS/TLS activation is a deployment step requiring your domain, not a locally completed hosted deployment.

## LangSmith

Local reports work without LangSmith. Publication and tracing are optional and disabled by default. The publisher creates an evaluation dataset, reference-linked runs and boolean feedback for every check plus overall acceptance. Adapter contracts are tested with a mock client; **remote publication has not been performed because no LangSmith API key is configured**.

To explicitly publish sample questions, expected rows and model outputs into your own workspace:

1. Set `LANGSMITH_API_KEY` and optionally `LANGSMITH_PROJECT` in local `.env`.
2. Review the report for content you intend to share.
3. Run `python scripts/publish_evaluation.py --report docs/evaluation/acceptance-matrix.json`.

`LANGSMITH_TRACING=true` separately enables SDK tracing for subsequent workflows; leave it false when you do not intend to share workflow data. The app never sends evaluation data to a remote account merely because local tests ran.
