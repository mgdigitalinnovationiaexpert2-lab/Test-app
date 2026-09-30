# Execution adapter contract

`mg_ai/providers.py` executes through LiteLLM; `mg_ai/proxy_config.py` maps provider families.
One registered deployment per alias. No client-controlled provider passthrough exists.

Outcomes: SUCCESS, SAFE_TO_RETRY, RATE_LIMITED_SAFE, FAILED_TERMINAL, EXECUTION_AMBIGUOUS.
Proxy connect/pool timeout is safe before dispatch. Read/write/transport failure after
connection is ambiguous. HTTP 401/403/404 and 429 are treated as pre-execution rejections;
408/409/5xx and malformed success are ambiguous. Other 4xx responses are terminal.
Providers with unusual HTTP semantics require additional contract tests. Invalid generated
JSON/tool output is never silently regenerated.

No upstream currently has an approved idempotency guarantee; configuration rejects such
claims. MG keys are not forwarded as an unsupported promise. Adding a guaranteed provider
requires explicit adapter support and contract tests. See docs/PROVIDERS.md for activation.
