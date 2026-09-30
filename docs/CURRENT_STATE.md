# Current state

## Frozen AI infrastructure — 2026-09-16

The Windows repository at `C:\Projects\MaghsoudGroup\MG_Ai_Infrastructure` is the source/master
working tree. Ubuntu at `/srv/MaghsoudGroup/MG_Ai_Infrastructure` is the current AI runtime.
Deep Codex is certified for PUBLIC text-only execution and two-turn continuity, and is now idle
(`enabled=false`, `session_ready=false`). Programmer `dev-code` is fully certified through
OpenCode → MG Gateway → private OmniRoute → Codex, including authentication, tool calls,
tool-result follow-up, buffered SSE and multi-turn behavior. OpenCode `dev-light` is explicitly
visible as the Groq Qwen FREE/light model; it never selects Codex, OmniRoute or an automatic
GPT-OSS fallback. Existing FREE and Portal routes remain on MG Gateway/LiteLLM.

Do not repeat completed certification tests: Deep two-turn certification; Gateway and FREE/Portal
regression checks; OpenCode authentication; `dev-code` routing; small Codex request; tool-call
generation and tool-result follow-up; buffered SSE; multi-turn behavior; deployment, build, sync
and network validation. No destructive Git/Docker operation was used, and no Server 3 deployment
has occurred.

Next phases: (1) securely remove the owner browser ChatGPT session from the Windows Server;
(2) prototype Deep Chat as a separate Regular ChatGPT backend; (3) define the Server 3 production
deployment and backup/restore workflow. Deep Chat remains planned and separate from Deep Codex.

## MG-owned DEEP continuity — 2026-09-12 (latest)

MG now owns canonical task continuity. Its private SQLite journal persists an ordered PUBLIC-only
transcript containing caller-owned task/conversation/execution/attempt identity, user text and
assistant final text. Each successful answer is committed with the completed execution before the
conversation becomes ready for its next turn. Hidden reasoning, credentials and provider state
are excluded. Public responses still contain only MG IDs, status, answer and timestamps.

The authorized real two-turn check did not certify live continuity. Turn 1 completed with exact
`TURN1_OK`; turn 2 was initially classified `EXECUTION_AMBIGUOUS` and was not retried. Existing
MG and OmniRoute evidence proves that OmniRoute returned deterministic HTTP 400
`previous_response_not_found` before provider dispatch. MG had sent the exact persisted Turn 1
response ID, but its adapter did not recognize that error code and misclassified the response.

MG treats that code as a deterministic pre-provider optimization miss. Canonical correctness no
longer uses that optimization: the default sends the fixed developer context, all prior completed
user/assistant turns and the current user turn. Optional previous-response optimization is off;
if explicitly enabled, only its proven pre-provider miss may recover once with the canonical full
transcript. Ambiguous dispatch never replays. A 120,000-character context guard fails explicitly
without truncating turns.

The affected attempt-2 execution was reconciled as `CONFIRMED_FAILED` from the existing HTTP 400
and pre-provider evidence. Its audit row is present and the global claim is released. The same
conversation retains Turn 1 as its last confirmed continuity point; the failed execution ID can
never be reused. No new inference was made during diagnosis or reconciliation.

A fresh authorized two-turn live check used a new task/conversation. Turn 1 returned `TURN1_OK`
and its user/final assistant content was persisted. Turn 2 used full transcript replay and returned
exact `MG-DEEP-CONTEXT-8426`. OmniRoute recorded exactly two successful Codex provider dispatches.
No previous response ID, retry, fallback or paid API was used. Targeted validation: 28 tests,
Ruff and strict mypy passed. Portal, FREE routes and production were untouched.

## Groq INTERNAL FREE qualification — 2026-09-12 (latest)

The owner confirmed a dedicated Groq FREE project with Global Zero Data Retention enabled.
Authenticated catalog checks returned active `qwen/qwen3.8-27b` and `openai/gpt-oss-120b`
deployments. Both passed the existing synthetic dev-code and Portal benchmark fixtures at every
threshold with no fallback or ambiguous execution. Qwen had lower measured latency and is the
pinned Champion for `dev-code` and `portal-normal`; GPT-OSS is an approved, disabled Challenger.

Exactly one final Gateway smoke per route returned `MG_DEV_CODE_OK` and
`MG_PORTAL_NORMAL_OK`. Both routes preserve INTERNAL privacy, use the direct LiteLLM/Groq FREE
path and cannot select their Champion from unrelated routes. Paid API remains OFF. DEEP and its
OmniRoute/Codex OAuth path were not changed.
Final validation passed: 124 tests, Ruff, strict mypy, secret scan and configuration render.

## OpenRouter PUBLIC FREE qualification — 2026-09-12

Authenticated OpenRouter discovery found 20 pinned zero-price candidates. Nex N2.5 Pro passed
both current PUBLIC synthetic `life-study` fixtures with every threshold at 1.0, no fallback,
and successful free capacity. It is the pinned `life-study` Champion until its evidence expires
at 2026-09-13 08:26 UTC. One final Gateway smoke returned exact `MG_LIFE_STUDY_OK`.
Developer and Portal NORMAL remain INTERNAL by explicit owner decision and have no
privacy-qualified free model; neither route was benchmarked or called live.
Final validation passed: 122 tests, Ruff, strict mypy, secret scan and configuration render.

Private DEEP text-only adapter, typed contract, durable singleton claim, owner controls and
pinned OmniRoute/browser Compose overlay are implemented. Defaults disabled/session unavailable.
Live DEEP remains LIVE_DEEP_BLOCKED_BY_OWNER_SESSION_SETUP. Text-only continuation is explicitly
unavailable and rejected. FREE routes cannot select DEEP; old portal-deep FREE alias removed.
Paid API remains OFF. FREE routing still uses Gateway and LiteLLM; OmniRoute remains exclusive
to DEEP. No consuming repository, production, commit or push was touched.
See [finalization evidence](PRE_SERVER_FINALIZATION.md), [DEEP contract](DEEP_BACKEND.md)
and [server runbook](SERVER_RUNBOOK.md) for current readiness, validation and remaining gates.

Everything below is historical milestone evidence; it does not override this latest state.

Latest live certification (2026-09-10): authenticated FREE account and pinned North Mini Code
gateway smoke PASS. Nex N2.5 Pro passed all five synthetic route probes and the two-request
developer endpoint contract. Gemma candidates failed configuration checks; Super stopped on
an ambiguous tool response. Nex is a provisional recommendation only; no fallback is qualified,
no model was promoted, and interactive Cline was not driven. See LIVE_CERTIFICATION_20260910.md.
The following 2026-09-09 notes describe the earlier milestone, not the latest certification.

Initial architecture implemented on 2026-09-06; local integration verified on 2026-09-07.
Portal now has the MG adapter and independent NORMAL recovery worker. Website received a
bounded documentation correction. Life_OS source and all production systems are untouched.

OpenRouter authentication now passes with a locally configured free-tier key. One pinned
`nex-agi/nex-n2.5-pro:free` smoke request reached OpenRouter through the MG Gateway and private
LiteLLM, but the gateway rejected the returned payload as `INVALID_UPSTREAM_RESPONSE` and
reported `EXECUTION_AMBIGUOUS`. The request was not replayed. Live route benchmarks and the
Cline contract check were therefore not run. The 2026-09-09 resume added Provider Capacity V1, Model Intelligence snapshot comparisons,
privacy evidence fields and the isolated live FREE MG Benchmark runner. See LIVE_BENCHMARK.md.
Portal DEEP is outside the resumed task. See RELEASE_GATES.md for unresolved vulnerabilities.

## Implemented

Typed MG API facade with private LiteLLM Proxy, three isolated client policies, logical
routes, validated registry, free review expiry, measured-quality gating, health cooldown,
safe fallback classification, durable SQLite quotas and execution journal, buffered SSE,
function/schema validation, privacy-conscious audit metadata, controlled discovery proposals,
Scope Guard, synthetic benchmark foundation and Server 3 deployment/backup procedures.

Paid inference is OFF and cannot be enabled by configuration in this release. Nonzero paid
budget settings fail closed until an audited monetary ledger is implemented. All five
provider-family examples and four named catalog proposals remain disabled. Native provider translation belongs to LiteLLM;
OmniRoute is reserved and not executable.

## Configuration required

Generated local MG tokens and an OpenRouter key exist in ignored `.env`; the key is never
stored in reports or logs. An owner
must select a model, verify zero-cost billing/commercial/privacy conditions, obtain capability
and category benchmark evidence, set review expiry and enable an approved registry entry,
then add its key and regenerate/recreate. No provider winner or live inference success is claimed.

## Validation

Final resumed milestone: 88 deterministic tests passed; Ruff, strict mypy (16 modules), config/schema
validation, wheel/sdist build, repository secret check and git diff whitespace check passed.
Starlette was subsequently pinned to 1.3.1 to fix three scanner-reported HIGH advisories;
33 gateway regression tests passed after the patch, with two upstream deprecation warnings.
Package and Docker rebuilds and the real LiteLLM/mock-provider contract passed afterward.
Runtime dependencies have no broken requirements. Production runtime lock includes hashes.

Docker gateway build passed. Default gateway and actual LiteLLM v1.99.1 containers are healthy
with non-root/read-only settings. Local authenticated smoke confirms 401 without a token and
503 NO_ELIGIBLE_FREE_MODEL with no approved providers. Default service remains running only
at http://127.0.0.1:8090; proxy has no published host port.

An isolated real-LiteLLM/local-fake-provider contract test passed: exactly one mock-error 500,
one mock-limit 429 and one mock-ok success. The 500 produced reconciliation without internal
retry; the 429 allowed a safe fallback. Test containers/network were removed; test volume and
ignored backup were retained. Online SQLite backup integrity was ok with two execution rows.
A full disaster-restore exercise and load testing remain future deployment work.

The offline benchmark CLI ran all 11 categories. Official OpenRouter catalog discovery ran
successfully on 2026-09-09: 19 free entries, two new Nex AGI entries, and MiniMax M2.7/M3
removed from the current free list. It wrote disabled recommendations; no registry model was
auto-enabled. Seven pinned candidates are queued for evaluation, while openrouter/free is
explicitly rejected as a Champion. Live benchmark preflight for North Mini Code produced a
BLOCKED report without inference because OPENROUTER_API_KEY is absent.
One isolated public-synthetic free smoke request ran against Nex N2.5 Pro; it did not produce
an MG-valid completion. No model has reviewed approval.
Cosign verified LiteLLM's signature with the upstream commit-pinned key. Trivy scanned both
images and found unresolved findings documented in RELEASE_GATES.md. Python's official base
is digest-pinned; an independent signature is not claimed. pip-audit stalled; no passing
result is claimed. Portal and Website npm dependency audits completed with findings.
The repository's deterministic secret check passed; a complete Gitleaks history scan is not claimed.

## Known limits

Single-host, one-worker SQLite; no HA or paid monetary ledger. Buffered SSE, no Responses
API/file upload/remote image fetching. Free discovery produces review proposals, not automatic
runtime promotion. Public catalog does not reveal account quota changes. No provider privacy
or quality claim without review. Starter fixtures are not a certification benchmark. No
authenticated browser/Cline/Plus/Life_OS validation, production load test or complete supply-chain
audit. Idempotency blocks duplicates but cannot replay answers or guarantee exactly-once.

No commit, push, merge or production deployment is authorized/performed in this task.
