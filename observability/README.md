# Audit metadata

`mg_ai.observability.emit` permits request_id, client, route, provider, model (registry alias),
attempt, result, error_category, latency_ms, usage, cost_estimate_usd, cost_class and generated
UTC timestamp. Dispatched attempts record fallback sequence. Missing usage is unknown.
Free cost estimates are zero based on approved entitlement, not a provider invoice.
Prompts, source code, documents, answers, tokens, headers and exception strings are not
accepted fields. Per-client `log_metadata=false` opts out; `log_content=true` is invalid.

SQLite stores counts, key/payload hashes, request IDs/status and health. Restrict access:
low-entropy payload hashes can be guessed. Never export journal contents to AI context.
Journal retention is indefinite to preserve duplicate suppression; review consumer identity
retention before introducing deletion. MG stdout logs rotate on Server 3 (5 x 10 MiB).
This is operational logging, not tamper-proof auditing. Pre-dispatch failures may have no
attempt record. `scripts/status.py` exposes detailed health only to a server operator.
Client readiness shows only its own route eligibility. No SaaS logging integration exists.
