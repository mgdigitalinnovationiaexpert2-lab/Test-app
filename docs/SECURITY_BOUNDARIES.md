# Security boundaries

Pre-server update: Life_OS is PUBLIC-only; Developer/Portal minimum remains INTERNAL by owner
decision. Separate DEEP accepts PUBLIC text only with a dedicated executor token. It has no
FREE credentials/network route; Omni API/CDP remain private, admin loopback-only. Secrets are
file-mounted, session state protected in separate volumes. No tools or private company data
are authorized. See [DEEP contract](DEEP_BACKEND.md) and [server runbook](SERVER_RUNBOOK.md).

Derived from [Gateway](../mg_ai/gateway.py), [adapter](../mg_ai/providers.py),
[request validation](../mg_ai/requests.py), [configuration](../mg_ai/config.py),
[proxy renderer](../mg_ai/proxy_config.py) and [Compose](../compose.yaml).

## External data and keys

Gateway's `LiteLLMAdapter.execute` sends messages, tool declarations and structured-output
instructions to the private proxy. LiteLLM sends them to the configured provider. The same
adapter is used by the live benchmark. Capacity sends an Authorization header to OpenRouter's
current-key endpoint, but no prompt. Discovery sends a public catalog GET. Model Intelligence,
offline evaluation and Scope Guard do not make external HTTP calls.

Provider keys originate in ignored `.env` and are injected into containers. Current Compose
injects the whole env file into both Gateway and proxy (and benchmark containers): Gateway
also has provider keys, not just LiteLLM. Generated YAML contains `os.environ/KEY_NAME`
references, not values. Gateway holds MG token digests for authentication; raw values still
exist in its process environment. Provider Capacity stores a credential fingerprint in SQLite
and omits it from CLI output. Neither Docker nor an ignored file is a secret vault.

Clients receive their own MG token only. `/v1/models` lists allowed logical routes, even when
no model is eligible. Responses include normalized content/tool calls, logical route name,
usage counts and MG request ID; error responses exclude raw provider errors. MG removes its
`mg` controls before dispatch and does not forward incoming client headers as provider headers.
Tool proposals are returned, never executed by MG. Clients remain responsible for tool access.

## Logging and persistence

`observability.emit` allows request ID, client, route, provider/model identifiers, candidate
sequence, attempts/fallback count, outcome/category, latency, token usage, cost class/estimate
and timestamp. Prompts, answers, tool arguments and credentials are not logged there.
Gateway access logging is disabled in the image entrypoint; HTTPX logging is reduced.
Proxy logging driver is `none`; message/spend logging, callbacks, telemetry and cache are
disabled by generated settings/Compose. These controls do not assert that upstream providers
retain nothing; provider privacy must be reviewed separately.

SQLite stores usage counters, key/body hashes, execution state and IDs, model health and
capacity metadata. It does not store answers for replay. Benchmark reports contain fixture
IDs, outcomes, scores, token counts and timings, not prompt/response content; fixed synthetic
prompts are in the repository fixture file. Backups retain metadata and must be protected.
There is no implemented journal retention/expiry or storage encryption layer.

## PAID KILL SWITCH — exact enforcement

| Layer | Code/config enforcement |
|---|---|
| Client policy | `config.Client.paid_allowed: Literal[False]`, `monthly_budget_usd: Literal[0]`; all three entries in policies/clients.json agree |
| Incoming request | `requests.RoutingInput.max_cost_class: Literal['FREE']` rejects paid requests |
| Model validation | `Candidate.safety` rejects enabled cost_class other than FREE; requires free evidence/expiry, approval and privacy review; OpenRouter enabled model must be explicit :free or labeled random router |
| Runtime selection | `Candidate.available` and `routing.select` require FREE, live expiry, approval, key and eligibility; empty → NO_ELIGIBLE_FREE_MODEL |
| Proxy | `proxy_config.render`: no retries/fallback lists; OpenRouter `allow_fallbacks=False`, `require_parameters=True`, `max_price.prompt=0`, `max_price.completion=0` |
| Benchmark | `live_benchmark.eligible`: fresh official zero-price pinned :free, no custom api_base, no random router; render's benchmark gate also requires pinned free |

There is no operational command to enable paid inference. Changing policy JSON to true/nonzero
fails validation. Payment support would require separately approved engineering and a billing
ledger. Zero-cost metadata is not provider invoice reconciliation. For other provider families,
MG depends on manually reviewed free status; the OpenRouter max-price guard is not a generic
provider price cap. Those examples remain disabled. Direct proxy access bypasses Gateway
policy; its master key and private network must stay server-side. The bridge permits outbound
traffic; it is not an egress allowlist or air gap.

## Privacy boundary

`chat` treats `Client.default_privacy` as both default and minimum, ordered PUBLIC < INTERNAL
< CONFIDENTIAL. An explicitly lower request returns 403 PRIVACY_DOWNGRADE_FORBIDDEN before
selection/admission; it is never lowered to obtain an eligible model. A higher request still
requires a client grant. Portal's current minimum is INTERNAL. Without an eligible INTERNAL
model its normal request returns NO_ELIGIBLE_FREE_MODEL. A developer/test policy explicitly
configured PUBLIC can still use PUBLIC. `chat` checks privacy against client grants; `routing.select` checks it
against model eligibility. Defaults in current client JSON are INTERNAL; all current models
are disabled and default to PUBLIC. A model cannot receive INTERNAL data merely because it
passed public synthetic tests. CONFIDENTIAL is absent from client grants; enabling a model
for CONFIDENTIAL additionally requires `confidential_allowed`, `retention_known` and
`training_use_known` in `Candidate.safety`. Enabled models require `data_policy_reviewed`.

These are owner-maintained assertions, not automatic validation of a contract, consent,
retention period or training exclusion. A data_policy_url is not itself verified. There is
no content classification/DLP: a client configured PUBLIC can still supply inappropriate
content, but an INTERNAL-minimum client cannot request PUBLIC. The benchmark does not apply
Gateway privacy checks. `approved_dataset` verifies `evals/dataset-approval.json` against the
fixed dataset path and SHA-256 before parsing any fixtures, and dispatch uses those captured
bytes (not a second unverified read). The manifest requires PUBLIC_SYNTHETIC, approval identity
and reason. CLI run additionally requires --live, --approved-by and a unique run ID. Altered
fixtures fail closed; updating both fixture and manifest is a reviewed owner action, not DLP.
Protect manifest/source write access; approval text is attribution, not authentication.

## Reviewed 429 semantics and provider stop

`Candidate.retry_429_review` is absent for every real provider/model in the main registry.
It must bind LiteLLMAdapter, provider and upstream model, REJECTED_BEFORE_EXECUTION semantics,
evidence, reviewer and timezone-aware expiry. Only a matching unexpired review allows
RATE_LIMITED_SAFE. Missing, mismatched or expired evidence yields EXECUTION_AMBIGUOUS /
UNREVIEWED_429_ACCEPTANCE: no fallback. OpenRouter, NVIDIA, direct/openai-compatible and
reserved OmniRoute are UNKNOWN, not reviewed-safe. Only the local mock-limit test contract
has synthetic evidence. Existing OpenRouter documentation in this repository did not supply
sufficient nonacceptance evidence. LiteLLM retries/fallbacks remain disabled.

`State.provider_enabled` filters selection and is rechecked immediately before each Gateway
dispatch. `State.set_provider_enabled` atomically persists the flag and actor/reason audit
event. A missing row defaults enabled (model qualification still required); a disabled row
persists across restart with no automatic re-enable. CLI requires local database access;
MG clients have no mutation endpoint. Benchmark checks the shared provider control store
before starting and before each fixture, while retaining its separate execution journal.
The stop is not a cancellation mechanism: in-flight work and the narrow interval after the
last check cannot be recalled. Direct use of the proxy master key bypasses this MG control.

Never commit `.env`, provider keys, MG client tokens, LiteLLM master key, secret-containing
overrides, shell transcripts with secrets or unreviewed backups. Do not print `docker inspect`
environment arrays or fully interpolated `docker compose config`. Use the narrow safe commands
in [OPERATIONS_RUNBOOK](OPERATIONS_RUNBOOK.md). `.gitignore` is prevention of accidental staging,
not encryption or revocation.
