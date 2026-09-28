# Consumer contract

Base URL ends in `/v1`; `Authorization: Bearer <MG client token>` is mandatory.
`model` is a logical route. Keep service tokens in the application backend/local developer
secret store, never in browser/mobile bundles.

```json
{
  "model": "portal-normal",
  "messages": [{"role": "user", "content": "Summarize this synthetic process note."}],
  "max_tokens": 1024,
  "mg": {
    "required_capabilities": ["PERSIAN"],
    "privacy_class": "INTERNAL",
    "context_tokens": 500,
    "latency_preference": "quality",
    "max_cost_class": "FREE"
  }
}
```

Supported: messages, model, max_tokens, temperature, top_p, stop, tools, tool_choice,
response_format, stream, stream_options.include_usage, mg. Unknown fields fail explicitly.
Function tools and inline JSON Schemas are supported; external schema references are not.
Images must be PNG/JPEG/WebP data URLs within the 1 MiB request bound. Extract documents
locally into text. No remote attachment retrieval/file API exists. Consumers approve and
execute returned tool calls; the gateway has no business-action tools.

`GET /v1/models` lists only the caller's routes. Success contains MG identity, logical model,
choices and available token usage; upstream extensions/headers are stripped. SSE sends a
buffered content/tool chunk, finish chunk, optional usage and `[DONE]`, not token streaming.

## Errors and identity

Send stable `Idempotency-Key` (1..128 ASCII letters/digits/underscore/dot/colon/hyphen)
from durable application execution identity. MG scopes it by authenticated client.

```json
{"error":{"type":"mg_gateway_error","code":"EXECUTION_AMBIGUOUS",
"message":"execution ambiguous","request_id":"MG-generated-UUID",
"retryable":false,"execution_state":"RECONCILIATION_REQUIRED"}}
```

Responses carry `X-Request-ID`. Identical keys return EXECUTION_ALREADY_RECORDED (409),
changed payloads return IDEMPOTENCY_CONFLICT. No private response caching/replay exists.
If a successful response was lost, 409 is not permission to submit with a new key. Reconcile
before issuing a new application identity. Journal records persist without automatic expiry.
This is duplicate suppression, not exactly-once delivery. See OPERATIONS for error meanings.

## Portal

Use `PORTAL_AI_PROVIDER=mg`, `MG_AI_URL` and Portal's `MG_AI_TOKEN`.
For the local Docker Portal use `http://host.docker.internal:8090/v1`;
for a host process use `http://127.0.0.1:8090/v1`. NORMAL LIGHT maps to
portal-light and WORKHORSE to portal-workhorse; the flagship NORMAL intent maps to
portal-deep. These are logical quality routes, not the approved DEEP subscription workflow.
Map assistant profile to trusted system instructions, context to messages, capabilities to
mg requirements, and attachments to bounded extracted text/images. Portal owns end-user
authorization and sensitive-data review. On RECONCILIATION_REQUIRED preserve its existing
execution identity/reconciliation state; never blindly resubmit or repeat business actions.
The MG adapter always requests FREE and rejects paid intent before dispatch. Set
`PORTAL_AI_GATEWAY_SUPPORTS_IDEMPOTENCY=false`: MG suppresses duplicates but cannot replay.
The local Portal integration and `ai-request-worker` now recover persisted NORMAL work
without browser polling. The worker uses existing requester permissions, attachment barriers,
leases and reconciliation rules; no schema or migration change was added by this integration.

Approved DEEP uses the existing authenticated ChatGPT Plus/plugin adapter, outside MG runtime
API routing. A Task's opaque `openai/session` and connection identity must match on later
claims; another Task must use a different upstream session. No paid API fallback, manual
answer or summary-based substitute is acceptable. Live continuity remains unverified until
the real adapter supplies a trustworthy session and completes the two-request challenge.

## Life_OS

Use `MG_AI_URL` and its independent `MG_AI_TOKEN`. life-study supports notes, flashcards,
quizzes, Persian education and transcript reasoning; life-document supports extracted
content. Add STRUCTURED_OUTPUT when structured flashcards/quizzes are required. FFmpeg,
Whisper, extraction and chunking remain application/local responsibilities. Paid is prohibited;
free exhaustion means retry later. No Life_OS source changes are included.
The same future contracts are also exposed as study-generation and document-analysis.

## VS Code / Cline

Choose Cline's OpenAI-compatible provider. Base URL is `MG_DEV_AI_URL`, locally
`http://127.0.0.1:8090/v1`; API key is `MG_DEV_TOKEN`. Model IDs: dev-code for tools/coding,
dev-light for short text, dev-reasoning, dev-vision for inline images, dev-strong for qualified
FRONTIER work. Cline versions vary in optional request fields; unknown extensions fail
explicitly. Configure context/output limits matching reviewed registry entries. The wire
contract is tested; no interactive Cline session is claimed verified.

Disable auto-approval for shell, commit, push, production data and deployment. Run
`python -m mg_ai.scope_guard scope-guard/task.example.yaml --root <task-repo>` before review.
The guard inspects diffs, not process execution, and is not an OS sandbox. Do not give the
IDE production credentials or mounts. No automatic Codex review is integrated.

Set Cline's Model ID to a logical route, API key to the MG developer token (not the Portal
token), and disable remote image URLs and unsupported request extensions. Start with a
synthetic prompt. A 503 NO_ELIGIBLE_FREE_MODEL is expected until qualification is complete.
See the [official Cline setup](https://docs.cline.bot/provider-config/openai-compatible).
This host has no detected Cline extension in the default VS Code profile; live IDE wire
compatibility and free coding inference are BLOCKED, not validated by curl or mock tests.

The reusable YAML contract and completed bounded documentation exercises are described in
[DEVELOPER_ACCEPTANCE.md](DEVELOPER_ACCEPTANCE.md).

Give each developer workstation its own approved MG developer credential; never copy another developer's token. Additional credentials still share the logical developer policy and quota namespace.
