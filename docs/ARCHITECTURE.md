# Architecture

**System of Engagement:** Portal and Life_OS own users, application permissions, UI,
attachments, domain actions and durable business execution identities.
**System of Intelligence:** MG authenticates clients, enforces eligibility and spending
rules, selects candidates, tracks outcomes and measures quality.
**Providers:** replaceable execution dependencies behind LiteLLM protocol support.

FastAPI is an MG policy facade, not a provider protocol reimplementation. It speaks one
chat protocol to a private LiteLLM Proxy, which translates OpenRouter, NVIDIA NIM,
OpenAI-compatible and native provider APIs. The additional internal hop preserves stable
MG policy when the core changes. OmniRoute is a reserved disabled adapter kind only.

## Request flow

1. Read at most 1 MiB with a bounded deadline; authenticate the MG token.
2. Validate an explicit request allowlist. Token determines client, never request body.
3. Resolve logical route; infer tool/image/JSON requirements and enforce client privacy.
4. Filter free expiry, credentials, approval, measured quality, tier, context/output,
   model allowlist, health cooldown and fresh reliable capacity; sort qualified candidates.
5. Atomically reserve request quota and journal execution identity in SQLite.
6. Durably mark DISPATCHED before sending to one registered LiteLLM alias.
7. Retry only definite safe rejection, at most three qualified free candidates.
8. Validate success and strip provider metadata. Stop on ambiguity; require reconciliation.

The journal stores metadata and hashes, never messages, documents or generated answers.
Repeated idempotency keys are blocked rather than replaying private content. No exactly-once
guarantee is claimed. Without a caller key, MG records execution but cannot recognize a
client retry as the same application operation.

## State and concurrency

SQLite WAL and BEGIN IMMEDIATE serialize local admission; quota and identity checks share
one transaction. DISPATCHED rows and health cooldowns survive crashes/restarts. Cooldowns
expire on UTC wall-clock time; the next real request may probe, without background inference
calls consuming quota. Run one MG worker on one host, using local durable storage (not NFS).
Keep clocks synchronized. A future shared journal must preserve these invariants before scaling.

Paid policy fields are locked to false/zero. Paid execution requires a future migration for
atomic worst-case reservations, pricing provenance, settlement and ambiguity accounting.
A configuration typo cannot enable paid usage. JSON Schema and function arguments are
validated locally. SSE delivers buffered validated output; native token streaming is deferred.
Capabilities are extensible strings. Applications see logical routes only.

Provider Capacity and Model Intelligence are control-plane modules. Capacity stores sanitized,
expiring observations keyed by provider and credential fingerprint; UNKNOWN never becomes a
fabricated limit. Discovery compares official catalog snapshots and emits recommendations.
External rankings are manually ingested evidence only. Runtime routing reads local state and
does no web discovery.

The live benchmark deploys one pinned `:free` candidate in a separate private LiteLLM project.
It uses fixed public/synthetic probes, journals dispatch, stores no prompt/answer, performs no
fallback and never changes the runtime registry. Its result can support route-specific
Champion/Challenger review, but cannot perform promotion.

No database server, Redis, vector store, broker, management UI, training infrastructure,
GPU dependency, production action agent or gateway chain is introduced. Configuration,
tests and operator procedures are the control plane.

Programmer routing has two explicit OpenCode models under `mg-ai`: certified `dev-code` uses+MG Gateway and private OmniRoute Codex; `dev-light` uses only the qualified Groq Qwen FREE/light+route through LiteLLM. Neither route exposes owner credentials, and `dev-light` has no Codex,+OmniRoute, or automatic GPT-OSS fallback.
