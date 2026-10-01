# Private DEEP backend contract

Status: MG-owned task continuity is verified locally and with a fresh real two-turn check.
Continuity uses MG's canonical transcript and does not require OmniRoute/provider response state.
This is an optional backend, separate from the FREE gateway. No Portal workflow or database
is changed. Portal remains responsible for approval, authorization, task ownership and
persisting the final answer. Private Task attachments use the authenticated INTERNAL staging
contract below; no file is exposed by a public URL.

## Contract

Local base `http://127.0.0.1:8091`. POST `/internal/deep/execute` with
`Authorization: Bearer <MG_DEEP_TOKEN>`. The dedicated token belongs to the trusted
Portal Deep Executor only; it is different from FREE client tokens and OmniRoute's API key.
There is no browser session material in this API. Additional request fields are forbidden.

```json
{
  "execution_id": "80000000-0000-4000-8000-000000000001",
  "task_id": "70000000-0000-4000-8000-000000000001",
  "conversation_id": "90000000-0000-4000-8000-000000000001",
  "attempt": 1,
  "privacy_class": "PUBLIC",
  "input": "Explain why 2 + 2 equals 4 in one sentence."
}
```

All six fields are required. IDs are UUIDs. `attempt` starts at 1 and increments for each
accepted execution in the same task/conversation. `input` is 1–32000 characters. No continuity
token, model, route, tools or cookie is accepted. `INTERNAL` is accepted only for the private
attachment contract below. The read deadline is 10 seconds.

Illustrative successful HTTP 200 (not a live result):

```json
{
  "execution_id": "80000000-0000-4000-8000-000000000001",
  "task_id": "70000000-0000-4000-8000-000000000001",
  "conversation_id": "90000000-0000-4000-8000-000000000001",
  "request_id": "a0000000-0000-4000-8000-000000000001",
  "attempt": 1,
  "status": "COMPLETED",
  "answer": "Adding two items to two items gives four items.",
  "created_at": "2026-09-12T10:00:00Z",
  "completed_at": "2026-09-12T10:00:03Z",
  "continuity": "TASK_SCOPED"
}
```

`X-Request-ID` matches body `request_id`. Internal thread and upstream response IDs remain in MG
state and are never returned. Only assistant output text is returned; reasoning, credentials and
provider error details are discarded.
No usage/cost estimate is fabricated for Plus. JSON schemas: [deep.schema.json](../gateway/deep.schema.json).

Errors use the MG envelope; e.g. HTTP 502:

```json
{
  "error": {
    "type": "mg_gateway_error",
    "code": "EXECUTION_AMBIGUOUS",
    "message": "execution ambiguous",
    "request_id": "a0000000-0000-4000-8000-000000000001",
    "retryable": false,
    "execution_state": "RECONCILIATION_REQUIRED"
  },
  "execution": {
    "execution_id": "80000000-0000-4000-8000-000000000001",
    "task_id": "70000000-0000-4000-8000-000000000001",
    "conversation_id": "90000000-0000-4000-8000-000000000001",
    "attempt": 1,
    "status": "EXECUTION_AMBIGUOUS"
  }
}
```

`execution` is included for an authenticated validated request that reached the handler;
unvalidated/auth errors may omit it. Attempt is 0 before a journal claim and 1 once recorded.
Known failures: 401 UNAUTHENTICATED, 400 INVALID_REQUEST, 503 DEEP_DISABLED,
DEEP_SESSION_UNAVAILABLE, DEEP_UPSTREAM_UNAVAILABLE, DEEP_HIGH_UNAVAILABLE;
409 DEEP_BUSY, IDEMPOTENCY_CONFLICT, EXECUTION_ALREADY_RECORDED,
CONVERSATION_TASK_CONFLICT, ATTEMPT_CONFLICT, DEEP_CONTRACT_UNAVAILABLE,
DEEP_CONTINUITY_UNAVAILABLE, DEEP_RECONCILIATION_REQUIRED,
DEEP_TRANSCRIPT_INCOMPLETE; 413 DEEP_CONTEXT_LIMIT_EXCEEDED.
Check `error.execution_state`, not HTTP status alone. A session error after POST is conservative
reconciliation; a session/preflight error before POST is NOT_COMPLETED/NOT_DISPATCHED.

## Execution and continuity

SQLite `deep_runs`, `deep_conversations` and `deep_turns` store execution metadata plus the
PUBLIC-only canonical user/final-assistant transcript. Hidden reasoning, OAuth/API credentials
and provider state are never transcript fields. Protect and back up this database as conversation
content. `deep_claim`
is a transactional singleton shared with the existing MG state volume. Only one execution
can hold it, even with multiple connections/processes. No time expiry permits another call.
The explicit states are NOT_DISPATCHED, DISPATCHED, COMPLETED, FAILED_DETERMINISTIC and
EXECUTION_AMBIGUOUS.
Crash after claiming keeps the claim. Crash near dispatch is never retried automatically.
Ambiguous HTTP/transport/invalid output and unknown 429 keep the claim for owner investigation.
Connect/pool failure before transmission can release it. No transport retries or fallback exist.
Every execution ID is single-use; duplicate IDs never call upstream, including known failures.
After a definite pre-dispatch failure, the caller may explicitly create a new execution ID.
After ambiguity, owner reconciliation is mandatory; there is no automatic or public claim-release
endpoint. The owner-only CLI accepts evidence-based `CONFIRMED_NOT_EXECUTED`, `CONFIRMED_FAILED`,
`CONFIRMED_COMPLETED` or `UNRESOLVED` outcomes and records the action, actor, evidence and time.
It refuses `CONFIRMED_COMPLETED` unless a response ID is already present in MG state. An
`UNRESOLVED` action is refused until the existing 240-second HTTP timeout/settlement bound has
elapsed; it leaves the execution non-retryable and blocks that conversation while releasing the
global slot for unrelated work. Do not delete the journal or claim merely to resume service.
The successful assistant final answer and execution completion are committed in one SQLite
transaction before the claim is released. MG does not claim exactly-once provider delivery and
does not replay ambiguous dispatches.

For each subsequent attempt, MG deterministically orders completed turns by attempt and rebuilds
the request as fixed developer context, prior user/final-assistant pairs and the current user turn.
A different task receives no history and cannot reuse another task's conversation ID. Context over
120,000 characters fails with `DEEP_CONTEXT_LIMIT_EXCEEDED`; no arbitrary turn is truncated.
Legacy conversations lacking a complete MG transcript fail closed with
`DEEP_TRANSCRIPT_INCOMPLETE`.

Private `previous_response_id` remains optional metadata. It is disabled by default and is never
required for correctness. If the owner explicitly enables that optimization, only deterministic
OmniRoute `previous_response_not_found` before provider dispatch permits one full-transcript
recovery under the same logical execution. Both internal attempts are audited. Any ambiguous
post-dispatch outcome keeps the execution non-retryable and never triggers replay.

The fresh real check returned exact `TURN1_OK`, persisted it, then returned exact
`MG-DEEP-CONTEXT-8426` from full transcript replay. OmniRoute logged two successful provider
dispatches. No optimization attempt, fallback or paid API was used.

## Current upstream boundary

The MG adapter uses the owner's active OmniRoute OpenAI Codex OAuth connection. It sends
`/v1/responses` with exact client route `cx/gpt-5.6-sol-high`; OmniRoute resolved it to
provider `codex`, requested model `codex/gpt-5.6-sol-high`, and upstream model
`gpt-5.6-sol-high`. The dedicated `MG-AI-DEEP` inference key is restricted to that model and
the single OAuth connection, with no-log enabled. The OAuth connection has no provider API key.
The MG client accepts only the exact route and its known canonical response model names.
There is no combo, alternate provider, FREE route, paid API key, or lower-effort fallback.
Concurrency remains one through the durable MG claim.

One authorized PUBLIC synthetic smoke completed on 2026-09-12 through this path and returned
exactly `MG_DEEP_CODEX_OK`. It was one inference request with no retry. This verifies the
first-turn text-only route; it does not expand privacy approval or continuity support.

## Historical browser-backed boundary

Reviewed 2026-09-10 source `5a777a243b389355891bc3aa917139d7cef5d866`,
branch `release/v3.8.51`; public latest release was v3.8.50. The Compose build pins this
source commit, not a moving tag or a claim of released stable v3.8.51.

The earlier adapter target sent `/v1/responses`, exact `chatgpt-web-codex/high`, reasoning high,
`tools: []`, `tool_choice: none`, stream false. It supplies native compatibility identity
`originator: codex-mg-deep` and `User-Agent: codex-mg-deep/0.1`, thread/turn metadata
and one current-turn input_text message. This is a compatibility adapter, not a real Codex
or Cline interactive test. OmniRoute derives its native passthrough internally.
No Pro, lower-effort route, combo or fallback is configured. Owner must scope the OmniRoute
API key to this exact route and configure only the intended owner connection.
GET `/v1/models` checks exact route presence before each POST; it does not prove a live session.
Local session-ready is owner attestation, not automatic authentication certification.

The retired exact IDs `chatgpt-web` and `cgpt-web` appear only in historical/retirement
documentation and upstream names, never as executable MG routes. The current provider is
`chatgpt-web-codex`. Text-only validation permits tunnel ID/runtime key to be omitted together.
Do not create a connector for this phase. Tool-capable work would require a separately approved
new connector named exactly `OmniRoute Codex v2`; it is outside this implementation.

Primary reviewed sources:

- [Provider setup, retirement and private browser](https://github.com/diegosouzapw/OmniRoute/blob/5a777a243b389355891bc3aa917139d7cef5d866/docs/providers/CHATGPT_WEB.md)
- [Responses executor](https://github.com/diegosouzapw/OmniRoute/blob/5a777a243b389355891bc3aa917139d7cef5d866/open-sse/executors/chatgpt-web-codex.ts)
- [Native identity validation](https://github.com/diegosouzapw/OmniRoute/blob/5a777a243b389355891bc3aa917139d7cef5d866/open-sse/config/codexIdentity.ts)
- [Text-only versus retained browser launcher](https://github.com/diegosouzapw/OmniRoute/blob/5a777a243b389355891bc3aa917139d7cef5d866/open-sse/vendor/codex-chatgpt-web/adapters/chatgpt-web/index.ts)
- [Connection validation](https://github.com/diegosouzapw/OmniRoute/blob/5a777a243b389355891bc3aa917139d7cef5d866/src/lib/providers/validation/chatgptWebCodex.ts)

See [server runbook](SERVER_RUNBOOK.md) for private setup, stop and recovery.

## Authenticated private attachments

The Portal may stage up to 10 private attachments for one execution before calling
`POST /internal/deep/execute`. Each file is sent to
`PUT /internal/deep/executions/{execution_id}/attachments/{index}` with the same Deep bearer
token, a raw request body, and `X-MG-Filename`, `X-MG-Size`, and `X-MG-Sha256` integrity
metadata. Staging is idempotent for identical bytes and metadata. Files are stored privately,
verified again at execution, and removed after terminal processing. The Portal can also call
`DELETE /internal/deep/executions/{execution_id}/attachments` for idempotent cleanup.

An attachment execution uses `privacy_class: "INTERNAL"` and includes only the staged
metadata in its JSON body. Supported types are UTF-8 text/JSON/XML/source formats, PNG,
JPEG, WebP, and PDF. Each file is limited to 10 MiB; combined inline text is limited to
200,000 bytes. Unsupported or invalid content is rejected before provider dispatch with a
specific `DEEP_ATTACHMENT_*` error. Files are never exposed through public URLs.
