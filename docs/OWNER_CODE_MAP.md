# Owner code map

Current source symbols, checked by `scripts/owner_inventory.py --check-docs`. The inventory
uses Python AST without importing application code; complete output is ignored at
`.runtime/owner-handover/inventory.json`. Only consequential functions are explained here.
Nested names such as `create_app.chat` are exact lexical names, not public import paths.

For every row: inputs are under **Reads/input**, outputs/failures under **Result**, mutations
under **Writes/side effects**. Unless marked **NETWORK**, the function makes no HTTP call and
cannot directly consume provider quota or spend money. NETWORK metadata calls do not infer;
NETWORK inference can consume quota, with paid inference prohibited by surrounding guards.

## Gateway composition root and chat feature module

[gateway.py](../mg_ai/gateway.py) is the composition root only: it builds configuration,
state, adapters and services, then registers routers, middleware and exception handlers.
Owner consequence: this is where a permitted request becomes an irreversible external dispatch.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `create_app` | Config root, tokens, proxy URL, state path | FastAPI app; startup fails for weak/shared credentials or invalid config | Opens SQLite and HTTP client; registers handlers; wires module controllers; no inference |

<!-- symbol: mg_ai/gateway.py::create_app -->

[common/middleware.py](../mg_ai/common/middleware.py) owns the client body boundary.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `Boundary.__call__` | ASGI body chunks | Bounded body + request ID; 413 too large / 408 read timeout | Buffers body in memory, response request-ID header |

<!-- symbol: mg_ai/common/middleware.py::Boundary.__call__ -->

[modules/chat/controller.py](../mg_ai/modules/chat/controller.py) exposes the HTTP surface
(`/v1/chat/completions`, `/v1/models`) and delegates everything else to the service.
[modules/chat/service.py](../mg_ai/modules/chat/service.py) owns authentication, admission,
routing/fallback, provider dispatch and streaming.
Owner consequence: the chat pipeline is where validated intent reaches a provider.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `ChatService.authenticate` | Bearer header, prehashed client tokens | Client name or UNAUTHENTICATED | None; constant-time digest comparisons |
| `ChatService.completions` | Validated request, client minimum/default privacy, route, candidates | Rejects privacy downgrade before admission; completion or MG error | Admission, journal, model health, audit; provider control rechecked before NETWORK via adapter |
| `AdminService.ready` | Client profile, SQLite, model eligibility | Ready/empty-pool summary; not provider probe | SQL SELECT and local filters only |
| `sse` | Validated full response, usage flag | Completion chunks and DONE | Yields buffered output; never executes tools |

<!-- symbol: mg_ai/modules/chat/service.py::ChatService.authenticate -->
<!-- symbol: mg_ai/modules/chat/service.py::ChatService.completions -->
<!-- symbol: mg_ai/modules/admin/service.py::AdminService.ready -->
<!-- symbol: mg_ai/modules/chat/service.py::sse -->

[modules/chat/dto/chat.py](../mg_ai/modules/chat/dto/chat.py) defines `Message`, `ChatRequest`
and `RoutingInput`; [requests.py](../mg_ai/requests.py) is a compatibility re-export of the
same DTOs. Owner consequence: accepting an API field is not permission to send arbitrary data
or tools.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `Message.content_safety` | Message content/image parts | Validated message; rejects remote image URLs/unsupported parts | None |
| `ChatRequest.supported_options` | Tool declarations, choice, response schema, stream options | Valid options or validation error | None |
| `ChatRequest.capabilities` | Request content/options and explicit MG capabilities | Required capability set used by policy/router | None |

<!-- symbol: mg_ai/modules/chat/dto/chat.py::Message.content_safety -->
<!-- symbol: mg_ai/modules/chat/dto/chat.py::ChatRequest.supported_options -->
<!-- symbol: mg_ai/modules/chat/dto/chat.py::ChatRequest.capabilities -->

[modules/executions/controller.py](../mg_ai/modules/executions/controller.py) serves
`/internal/executions/reconcile` (DTO `ReconciliationRequest`, thin controller,
`ExecutionsService.reconcile` reading the journal).
[modules/admin/controller.py](../mg_ai/modules/admin/controller.py) serves gateway
`/health/live` and `/health/ready` (GET-only, so no inbound DTO layer by design).
[modules/providers/__init__.py](../mg_ai/modules/providers/__init__.py) is a facade that
re-exports the upstream adapters (`LiteLLMAdapter`, `ProgrammerAdapter`, `Outcome`, `Result`);
it has no HTTP routes of its own because dispatch belongs to the chat service.

## Registry, selection and dispatch

[config/models.py](../mg_ai/config/models.py): `Candidate` is the model record; `Client` and
`Route` are policy records. `Client.paid_allowed` is Literal[False], budget Literal[0]. They
are not admin toggles for enabling payment. [routing.py](../mg_ai/routing.py) applies the
records. Owner consequence: wrong approval metadata can authorize data transmission; maintain
evidence.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `load_config` | Three JSON files | Validated Configuration or file/schema error | None |
| `Candidate.safety` | Model enablement, free evidence, privacy flags | Rejects paid enabled models, missing review, unsafe confidential flags, random-router mislabeling | None; cannot verify evidence truth |
| `Candidate.available` | Enable/approval, environment key, expiry, configured health/quota | Boolean eligibility prerequisite | None; no provider verification |
| `Configuration.references` | IDs, clients, routes, allowlists, Champions | Rejects bad references, duplicates, random Champion | None |
| `select` | Config/policy/route, required capabilities, privacy, context/output, provider control and health state | Ordered eligible list excluding disabled providers; empty list, not an exception | Reads state; no HTTP. `ChatService.completions` converts empty to NO_ELIGIBLE_FREE_MODEL |

<!-- symbol: mg_ai/config/models.py::load_config -->
<!-- symbol: mg_ai/config/models.py::Candidate.safety -->
<!-- symbol: mg_ai/config/models.py::Candidate.available -->
<!-- symbol: mg_ai/config/models.py::Configuration.references -->
<!-- symbol: mg_ai/routing.py::select -->

`select` sorts by descending task score, Champion preference, runtime healthy status, known
quota, latency/failure preference, configured latency, then ID. Candidate role `challenger`
is excluded. Configured health and SQLite health are distinct; SQLite cooldown gates requests.

[providers.py](../mg_ai/providers.py) defines `LiteLLMAdapter`, `Outcome` and `Result`.
[proxy_config.py](../mg_ai/proxy_config.py) generates the private deployments.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `LiteLLMAdapter.execute` | Candidate alias, payload and optional Retry429Review | Sanitized Result; 429 safe only for matching unexpired review, otherwise ambiguous | NETWORK POST to LiteLLM, which sends data to provider; quota possible; no internal retry |
| `render` | Configuration, optional benchmark IDs | LiteLLM dictionary; rejects non-pinned/free benchmark deployments | None itself; caller writes YAML. API keys remain environment references |
| `emit` in observability | Approved metadata keyword fields | JSON audit record; invalid nonfinite numeric data may fail serialization | Writes logger, never prompts/answers |

<!-- symbol: mg_ai/providers.py::LiteLLMAdapter.execute -->
<!-- symbol: mg_ai/proxy_config.py::render -->
<!-- symbol: mg_ai/observability.py::emit -->

Owner consequence: malformed provider output is treated as possible completed execution,
not a reason to retry. See [failure classification](FAILURE_AND_RECOVERY.md).

## Persistence and capacity

[state.py](../mg_ai/state.py) is a compatibility alias; `GatewayRepository` in
[database/gateway_repository.py](../mg_ai/database/gateway_repository.py) contains the journal
logic; its constructor creates WAL tables and directories. SQLite is a single-host journal and
counter, not a billing ledger or answer cache.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `GatewayRepository.admit` | Client, limits, key, canonical body, request ID | Digest or 429 quota / 409 duplicate/conflict | BEGIN IMMEDIATE transaction increments usage and inserts ADMITTED; rolls back on failure |
| `GatewayRepository.check_duplicate` | Client/key/body hashes | No result or 409; marks reconciliation for DISPATCHED/AMBIGUOUS | Read only |
| `GatewayRepository.execution` | Client/digest/status | No return; SQLite errors possible | Updates status and time; no transition validation or reconciliation engine |
| `GatewayRepository.record` | Model/outcome/latency/retry-after | No return | Upserts health, failures, timestamps and cooldown |
| `GatewayRepository.save_capacity` | Capacity record | No return | Upserts JSON observation with credential fingerprint |
| `GatewayRepository.capacity` | Provider/account | Capacity or None; corrupt observation can fail validation | Read only |
| `GatewayRepository.provider_enabled` | Provider name | Persisted control flag; absent row defaults enabled | Read only; no model enablement |
| `GatewayRepository.set_provider_enabled` | Provider, flag, actor and reason | Rejects missing attribution | Atomic control upsert and append-only application audit insert |

<!-- symbol: mg_ai/database/gateway_repository.py::GatewayRepository.admit -->
<!-- symbol: mg_ai/database/gateway_repository.py::GatewayRepository.check_duplicate -->
<!-- symbol: mg_ai/database/gateway_repository.py::GatewayRepository.execution -->
<!-- symbol: mg_ai/database/gateway_repository.py::GatewayRepository.record -->
<!-- symbol: mg_ai/database/gateway_repository.py::GatewayRepository.save_capacity -->
<!-- symbol: mg_ai/database/gateway_repository.py::GatewayRepository.capacity -->
<!-- symbol: mg_ai/database/gateway_repository.py::GatewayRepository.provider_enabled -->
<!-- symbol: mg_ai/database/gateway_repository.py::GatewayRepository.set_provider_enabled -->

[capacity.py](../mg_ai/capacity.py) is a compatibility re-export; `Capacity` lives in
[common/capacity.py](../mg_ai/common/capacity.py). Owner consequence: UNKNOWN does not
mean unlimited, and an observation in the wrong SQLite file cannot influence the Gateway.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `Capacity.blocks` | Credential fingerprint, freshness, reliability, remaining/reset values | True only for fresh matching blocking evidence; stale/unknown does not block | None |
| `refresh_openrouter` | Key, HTTP client | Capacity; missing key/network failure → UNKNOWN; 401/403 → AUTH_REJECTED | NETWORK authenticated GET current-key metadata; no prompt |
| `openrouter_capacity` | Whitelisted API data | Healthy expiring Capacity; unavailable fields remain null | None |
| `groq_capacity` | Response headers and verified-direct flag | Remaining request/token/reset observation | None; parser only, no Groq execution adapter |
| `main` | Process environment, --state | Prints sanitized capacity excluding fingerprint | NETWORK via refresh; saves SQLite. Does not load .env itself |

<!-- symbol: mg_ai/common/capacity.py::Capacity.blocks -->
<!-- symbol: mg_ai/common/capacity.py::refresh_openrouter -->
<!-- symbol: mg_ai/common/capacity.py::openrouter_capacity -->
<!-- symbol: mg_ai/common/capacity.py::groq_capacity -->
<!-- symbol: mg_ai/common/capacity.py::main -->

## Discovery, evaluation and recommendations

[discovery.py](../mg_ai/discovery.py) is offline-to-runtime separation: catalog entries remain
proposals. [live_benchmark.py](../mg_ai/live_benchmark.py) makes controlled real calls;
[model_intelligence.py](../mg_ai/model_intelligence.py) interprets saved results.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `discovery.free_model` | Model ID/pricing | Conservative explicit zero-price test | None |
| `discovery.proposal` | Current/previous catalog, optional config | Disabled candidates, deltas and recommendations | None; no registry edit |
| `discovery.main` | Official catalog URL, prior report, optional external evidence | Discovery report or HTTP/validation failure | NETWORK public GET; atomic report write |
| `live_benchmark.eligible` | Candidate, dated catalog | Fresh official pinned zero-price boolean | None; no quality/privacy/provider health certification |
| `live_benchmark.approved_dataset` | Fixed fixture bytes and approval manifest | Verified immutable-in-run byte snapshot; mismatch raises ValueError before inference | File reads only; no classifier |
| `live_benchmark.run` | Candidate/catalog, adapter, State, run ID, selected routes | BLOCKED/FAILED/COMPLETED/RECONCILIATION_REQUIRED | NETWORK via adapter; run journal and atomic report; stops first non-SUCCESS |
| `live_benchmark.score_case` | Synthetic fixture and Result | Per-dimension exact/schema/script scores | None; Persian script presence is not fluency |
| `live_benchmark.summarize` | Scored rows, thresholds | Per-route minima, pass flag and human-review status | None; never promotes |
| `live_benchmark.main` | CLI args/env/config/catalog | Prepare/run orchestration | Prepare writes isolated YAML; run sends inference; duplicates not replayed |
| `model_intelligence.recommendations` | Completed live reports, dataset hash, thresholds | Provisional ranked routes; absent pool → BLOCKED | None; excludes incomplete reports; no registry mutation |
| `model_intelligence.main` | Report files | Provisional recommendation JSON | Local report write only |
| `evals.run` | Synthetic fixtures and optional supplied responses | Offline checks, explicitly not model-quality claim | None; no inference |

<!-- symbol: mg_ai/discovery.py::free_model -->
<!-- symbol: mg_ai/discovery.py::proposal -->
<!-- symbol: mg_ai/discovery.py::main -->
<!-- symbol: mg_ai/live_benchmark.py::eligible -->
<!-- symbol: mg_ai/live_benchmark.py::approved_dataset -->
<!-- symbol: mg_ai/live_benchmark.py::run -->
<!-- symbol: mg_ai/live_benchmark.py::score_case -->
<!-- symbol: mg_ai/live_benchmark.py::summarize -->
<!-- symbol: mg_ai/live_benchmark.py::main -->
<!-- symbol: mg_ai/model_intelligence.py::recommendations -->
<!-- symbol: mg_ai/model_intelligence.py::main -->
<!-- symbol: mg_ai/evals.py::run -->

## Local owner tools and configuration files

[scope_guard.py](../mg_ai/scope_guard.py) is optional explicit workflow enforcement.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `check` | Changed paths, TaskPolicy, requested edit/commit/push action | Allowed/forbidden findings | None; does not intercept shell commands |
| `changed_since` | Root and owner baseline | Paths whose hashes differ; rejects root mismatch | Local git reads and file hashing; no remote calls |

<!-- symbol: mg_ai/scope_guard.py::check -->
<!-- symbol: mg_ai/scope_guard.py::changed_since -->

| File | Input → output and side effects | Failure / owner consequence |
|---|---|---|
| [scripts/prepare.py](../scripts/prepare.py) | Local JSON → generated schema and `.runtime/litellm.yaml` | Validation fails before usable render; does not reload services |
| [scripts/status.py](../scripts/status.py) | Config/env/SQLite → model availability/health | Opens/initializes state; not a full route eligibility check; host .env not automatically loaded |
| [scripts/backup_state.py](../scripts/backup_state.py) | Existing SQLite → new consistent backup via SQLite backup API | Refuses missing source/overwrite; protect backup; do not copy only a live WAL main file |
| [scripts/docker_smoke.py](../scripts/docker_smoke.py) | Local MG token → assertions, negative chat | No external inference in default disabled setup; refuses ready eligible stack |
| [scripts/init_local.py](../scripts/init_local.py) | Local initialization → ignored credentials/config | Generates secrets; not the routine restart command |
| [compose.yaml](../compose.yaml) | .env, proxy YAML, Gateway image → local containers/volume | Loopback 8090, private proxy; Docker restart policy unless-stopped |
| [gateway/Dockerfile](../gateway/Dockerfile) | Source/config → image, /state volume path | Config baked into image; single worker; non-root |
| [evals/compose.live.yaml](../evals/compose.live.yaml) | .env, benchmark YAML, image, catalog → isolated runner | Benchmark image's registry must match host; separate state `/results/benchmark.sqlite` |
| [policies/clients.json](../policies/clients.json) | Client grants and limits | Developer/Portal minimum INTERNAL; Life_OS PUBLIC-only pilot; all paid false |
| [routing/routes.json](../routing/routes.json) | Route constraints and optional Champion | No persistent Fallback field; no current Champion |
| [model-registry/models.json](../model-registry/models.json) | Owner-maintained model records | Currently all disabled; catalog proposals are not live configuration |

Approval booleans and evidence are validated for presence/shape, not signed owner approval.
Protect configuration write access. There is no admin UI or automatic reconciliation.
`mg_ai.provider_control.main` implements local list/disable/enable with actor/reason and
State transaction; no HTTP endpoint or provider call. Shared SQLite control is read by Gateway
and benchmark before dispatch. See [owner decisions](OWNER_APPROVAL_POINTS.md).
<!-- symbol: mg_ai/provider_control.py::main -->

## Optional private DEEP boundary

[deep.py](../mg_ai/deep.py) is the DEEP composition root: it builds `DeepService`, registers
the router from [modules/deep/controller.py](../mg_ai/modules/deep/controller.py), adds the
body-boundary middleware and exception handlers, and defines `create_deep_app`. The DTOs
`DeepRequest`, `DeepResponse` and `DeepAttachment` live in
[modules/deep/dto/deep.py](../mg_ai/modules/deep/dto/deep.py); `DeepAdapter` (provider plumbing)
and `DeepService` (claim/attachment/continuity orchestration) live in
[modules/deep/service.py](../mg_ai/modules/deep/service.py). The service authenticates a
dedicated executor token, pins native HIGH Responses, sanitizes output and classifies ambiguity.
[database/deep_repository.py](../mg_ai/database/deep_repository.py) reuses GatewayRepository
with a durable singleton claim and hashed request identities; no prompt/answer store
([deep_state.py](../mg_ai/deep_state.py) is a compatibility alias).
[deep_control.py](../mg_ai/deep_control.py) provides local audited enable/disable and session
attestation. No external login or reconciliation is automatic. See [contract](DEEP_BACKEND.md).
<!-- symbol: mg_ai/modules/deep/dto/deep.py::DeepRequest -->
<!-- symbol: mg_ai/modules/deep/dto/deep.py::DeepResponse -->
<!-- symbol: mg_ai/modules/deep/service.py::DeepAdapter -->
<!-- symbol: mg_ai/deep.py::create_deep_app -->
<!-- symbol: mg_ai/database/deep_repository.py::DeepRepository -->
<!-- symbol: mg_ai/deep_control.py::main -->
