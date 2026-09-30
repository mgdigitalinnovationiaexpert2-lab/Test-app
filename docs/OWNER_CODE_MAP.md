# Owner code map

Current source symbols, checked by `scripts/owner_inventory.py --check-docs`. The inventory
uses Python AST without importing application code; complete output is ignored at
`.runtime/owner-handover/inventory.json`. Only consequential functions are explained here.
Nested names such as `create_app.chat` are exact lexical names, not public import paths.

For every row: inputs are under **Reads/input**, outputs/failures under **Result**, mutations
under **Writes/side effects**. Unless marked **NETWORK**, the function makes no HTTP call and
cannot directly consume provider quota or spend money. NETWORK metadata calls do not infer;
NETWORK inference can consume quota, with paid inference prohibited by surrounding guards.

## Gateway and request validation

[gateway.py](../mg_ai/gateway.py) owns the client boundary and execution coordination.
Owner consequence: this is where a permitted request becomes an irreversible external dispatch.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `Boundary.__call__` | ASGI body chunks | Bounded body + request ID; 413 too large / 408 read timeout | Buffers body in memory, response request-ID header |
| `create_app` | Config root, tokens, proxy URL, state path | FastAPI app; startup fails for weak/shared credentials or invalid config | Opens SQLite and HTTP client; registers handlers; no inference |
| `create_app.authenticate` | Bearer header, prehashed client tokens | Client name or UNAUTHENTICATED | None; constant-time digest comparisons |
| `create_app.chat` | Validated request, client minimum/default privacy, route, candidates | Rejects privacy downgrade before admission; completion or MG error | Admission, journal, model health, audit; provider control rechecked before NETWORK via adapter |
| `create_app.ready` | Client profile, SQLite, model eligibility | Ready/empty-pool summary; not provider probe | SQL SELECT and local filters only |
| `sse` | Validated full response, usage flag | Completion chunks and DONE | Yields buffered output; never executes tools |

<!-- symbol: mg_ai/gateway.py::Boundary.__call__ -->
<!-- symbol: mg_ai/gateway.py::create_app -->
<!-- symbol: mg_ai/gateway.py::create_app.authenticate -->
<!-- symbol: mg_ai/gateway.py::create_app.chat -->
<!-- symbol: mg_ai/gateway.py::create_app.ready -->
<!-- symbol: mg_ai/gateway.py::sse -->

[requests.py](../mg_ai/requests.py) defines `Message`, `ChatRequest` and `RoutingInput`.
Owner consequence: accepting an API field is not permission to send arbitrary data or tools.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `Message.content_safety` | Message content/image parts | Validated message; rejects remote image URLs/unsupported parts | None |
| `ChatRequest.supported_options` | Tool declarations, choice, response schema, stream options | Valid options or validation error | None |
| `ChatRequest.capabilities` | Request content/options and explicit MG capabilities | Required capability set used by policy/router | None |

<!-- symbol: mg_ai/requests.py::Message.content_safety -->
<!-- symbol: mg_ai/requests.py::ChatRequest.supported_options -->
<!-- symbol: mg_ai/requests.py::ChatRequest.capabilities -->

## Registry, selection and dispatch

[config.py](../mg_ai/config.py): `Candidate` is the model record; `Client` and `Route` are
policy records. `Client.paid_allowed` is Literal[False], budget Literal[0]. They are not
admin toggles for enabling payment. [routing.py](../mg_ai/routing.py) applies the records.
Owner consequence: wrong approval metadata can authorize data transmission; maintain evidence.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `load_config` | Three JSON files | Validated Configuration or file/schema error | None |
| `Candidate.safety` | Model enablement, free evidence, privacy flags | Rejects paid enabled models, missing review, unsafe confidential flags, random-router mislabeling | None; cannot verify evidence truth |
| `Candidate.available` | Enable/approval, environment key, expiry, configured health/quota | Boolean eligibility prerequisite | None; no provider verification |
| `Configuration.references` | IDs, clients, routes, allowlists, Champions | Rejects bad references, duplicates, random Champion | None |
| `select` | Config/policy/route, required capabilities, privacy, context/output, provider control and health state | Ordered eligible list excluding disabled providers; empty list, not an exception | Reads state; no HTTP. `chat` converts empty to NO_ELIGIBLE_FREE_MODEL |

<!-- symbol: mg_ai/config.py::load_config -->
<!-- symbol: mg_ai/config.py::Candidate.safety -->
<!-- symbol: mg_ai/config.py::Candidate.available -->
<!-- symbol: mg_ai/config.py::Configuration.references -->
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

[state.py](../mg_ai/state.py) contains `State`; its constructor creates WAL tables and
directories. SQLite is a single-host journal and counter, not a billing ledger or answer cache.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `State.admit` | Client, limits, key, canonical body, request ID | Digest or 429 quota / 409 duplicate/conflict | BEGIN IMMEDIATE transaction increments usage and inserts ADMITTED; rolls back on failure |
| `State.check_duplicate` | Client/key/body hashes | No result or 409; marks reconciliation for DISPATCHED/AMBIGUOUS | Read only |
| `State.execution` | Client/digest/status | No return; SQLite errors possible | Updates status and time; no transition validation or reconciliation engine |
| `State.record` | Model/outcome/latency/retry-after | No return | Upserts health, failures, timestamps and cooldown |
| `State.save_capacity` | Capacity record | No return | Upserts JSON observation with credential fingerprint |
| `State.capacity` | Provider/account | Capacity or None; corrupt observation can fail validation | Read only |
| `State.provider_enabled` | Provider name | Persisted control flag; absent row defaults enabled | Read only; no model enablement |
| `State.set_provider_enabled` | Provider, flag, actor and reason | Rejects missing attribution | Atomic control upsert and append-only application audit insert |

<!-- symbol: mg_ai/state.py::State.admit -->
<!-- symbol: mg_ai/state.py::State.check_duplicate -->
<!-- symbol: mg_ai/state.py::State.execution -->
<!-- symbol: mg_ai/state.py::State.record -->
<!-- symbol: mg_ai/state.py::State.save_capacity -->
<!-- symbol: mg_ai/state.py::State.capacity -->
<!-- symbol: mg_ai/state.py::State.provider_enabled -->
<!-- symbol: mg_ai/state.py::State.set_provider_enabled -->

[capacity.py](../mg_ai/capacity.py) holds `Capacity`. Owner consequence: UNKNOWN does not
mean unlimited, and an observation in the wrong SQLite file cannot influence the Gateway.

| Exact function | Reads/input | Result / failure | Writes/side effects |
|---|---|---|---|
| `Capacity.blocks` | Credential fingerprint, freshness, reliability, remaining/reset values | True only for fresh matching blocking evidence; stale/unknown does not block | None |
| `refresh_openrouter` | Key, HTTP client | Capacity; missing key/network failure → UNKNOWN; 401/403 → AUTH_REJECTED | NETWORK authenticated GET current-key metadata; no prompt |
| `openrouter_capacity` | Whitelisted API data | Healthy expiring Capacity; unavailable fields remain null | None |
| `groq_capacity` | Response headers and verified-direct flag | Remaining request/token/reset observation | None; parser only, no Groq execution adapter |
| `main` | Process environment, --state | Prints sanitized capacity excluding fingerprint | NETWORK via refresh; saves SQLite. Does not load .env itself |

<!-- symbol: mg_ai/capacity.py::Capacity.blocks -->
<!-- symbol: mg_ai/capacity.py::refresh_openrouter -->
<!-- symbol: mg_ai/capacity.py::openrouter_capacity -->
<!-- symbol: mg_ai/capacity.py::groq_capacity -->
<!-- symbol: mg_ai/capacity.py::main -->

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

[deep.py](../mg_ai/deep.py) defines `DeepRequest`, `DeepResponse`, `DeepAdapter` and
`create_deep_app`: authenticates a dedicated executor token, pins native HIGH Responses,
sanitizes output and classifies ambiguity. [deep_state.py](../mg_ai/deep_state.py) reuses
State with a durable singleton claim and hashed request identities; no prompt/answer store.
[deep_control.py](../mg_ai/deep_control.py) provides local audited enable/disable and session
attestation. No external login or reconciliation is automatic. See [contract](DEEP_BACKEND.md).
<!-- symbol: mg_ai/deep.py::DeepRequest -->
<!-- symbol: mg_ai/deep.py::DeepResponse -->
<!-- symbol: mg_ai/deep.py::DeepAdapter -->
<!-- symbol: mg_ai/deep.py::create_deep_app -->
<!-- symbol: mg_ai/deep_state.py::DeepState -->
<!-- symbol: mg_ai/deep_control.py::main -->
