# Pre-server finalization evidence — 2026-09-10

## MG-owned DEEP task continuity — 2026-09-12 (latest)

MG now persists caller-owned task, conversation, execution and attempt identity, while keeping
the upstream thread and response binding private. Targeted tests pass for two-turn continuity,
cross-task isolation, duplicate/conflict protection, singleton concurrency, deterministic and
ambiguous failure handling, exact route pinning, no fallback and response sanitization.

MG now persists the ordered PUBLIC user/final-assistant transcript and reconstructs every
subsequent request from MG-owned history. Previous provider response state is optional and off by
default. The earlier failed execution remains single-use and was audited as `CONFIRMED_FAILED`.

A new maximum two-dispatch real check passed: Turn 1 returned and persisted exact `TURN1_OK`; Turn
2 full-transcript replay returned exact `MG-DEEP-CONTEXT-8426`. OmniRoute logged exactly two HTTP
200 Codex provider dispatches. There was no retry, previous-response optimization, fallback or
paid API use. Targeted tests: 28 passed; Ruff and strict mypy passed. Portal, FREE routing,
model/provider and production were untouched.

## Groq INTERNAL FREE certification — 2026-09-12 (latest)

Owner evidence confirms the dedicated Groq FREE project and Global ZDR. Authenticated Groq
catalog metadata showed active `qwen/qwen3.8-27b` and `openai/gpt-oss-120b` deployments with
approximately 131k context. Both candidates passed the approved PUBLIC-synthetic Portal and
dev-code fixtures with every threshold at 1.0, successful capacity, fallback count zero and no
ambiguous execution. Six qualification requests were made in total.

Measured latency selected Qwen as Champion for `portal-normal` and `dev-code`; GPT-OSS remains
an approved but disabled Challenger. One final request per route returned exact
`MG_PORTAL_NORMAL_OK` and `MG_DEV_CODE_OK`. Total live inference requests for this phase: eight;
retries: zero; paid requests: zero. Route-scoped Champion selection prevents these models from
becoming eligible on unrelated routes. FREE continues through Gateway and LiteLLM directly to
Groq. OmniRoute and DEEP were untouched.
Final validation passed: 124 tests, Ruff, strict mypy, repository secret scan and config render.

## OpenRouter PUBLIC FREE qualification — 2026-09-12

Authenticated OpenRouter catalog discovery returned 20 concrete zero-price candidates.
Privacy was gated before inference: Portal NORMAL and dev-code retain INTERNAL minimum and
remain blocked because no reviewed INTERNAL-qualified free candidate exists. They received
zero qualification and smoke requests.

For PUBLIC `life-study`, pinned `nex-agi/nex-n2.5-pro:free` passed both approved synthetic
fixtures with all route thresholds at 1.0, fallback count zero and successful current serving
capacity. Existing earlier route evidence and owner approval for PUBLIC educational data were
reused. The candidate is enabled as the route Champion with zero-cost evidence expiring
2026-09-13 08:26 UTC. One final request through MG Gateway and LiteLLM returned exact
`MG_LIFE_STUDY_OK`. Current task inference count: three (two qualification, one smoke), retries
zero, ambiguous executions zero, paid requests zero. No Challenger was qualified.

Champion preference now precedes raw benchmark score in deterministic selection, with a focused
regression test. DEEP configuration, services and routing were not changed. FREE remains on the
existing LiteLLM/OpenRouter path; no provider was added to OmniRoute.
Final validation passed with 122 tests, Ruff, strict mypy, repository secret scan and config render.

## Codex OAuth DEEP certification — 2026-09-12 (latest)

The selected DEEP backend is now the owner's active OmniRoute OpenAI Codex OAuth connection,
not the previous browser-cookie route. Authenticated `GET /v1/models` returned 200 and included
exact `cx/gpt-5.6-sol-high`. OmniRoute's `MG-AI-DEEP` key is active, no-log, restricted to the
single OAuth connection and `codex/gpt-5.6-sol-high`; no credential value was printed. The
OAuth connection has no OpenAI API key.

MG `DEEP_ROUTE` is `cx/gpt-5.6-sol-high`. One PUBLIC synthetic request through the private MG
boundary → OmniRoute `/v1/responses` → provider `codex` completed with HTTP 200 and returned
exactly `MG_DEEP_CODEX_OK`. OmniRoute recorded requested model `codex/gpt-5.6-sol-high` and
resolved model `gpt-5.6-sol-high`. Live inference count: 1; retries: 0; FREE calls: 0; paid API
calls: 0. MG journal status SUCCESS and the singleton claim was released.

Targeted DEEP tests: 16 passed; Ruff and strict mypy passed. Full suite was not rerun.
Paid inference remains OFF, all free models remain disabled, and FREE/NORMAL routing was not
changed. Concurrency 1, conservative ambiguity and explicit continuity failure remain intact.

## Latest bounded closeout checkpoint (supersedes runtime status below)

Official `diegosouzapw/omniroute:3.8.50-web` installed without source build. Running services
pin linux/amd64 digest `sha256:ee6168e2a48fd2482c0416e6a53a27dc2f3609e169cc5f873ff7b1e5a520cf53`.
OmniRoute and headed Chromium/Xvfb sidecar are healthy. Stable image lacks xauth; direct private
Xvfb startup fixes the failed xvfb-run launch without altering the image or Python behavior.
CDP HTTP and Playwright WebSocket checks pass; no browser port is published. Dashboard login
is HTTP 200 on loopback 20128. API remains private: invalid-token models GET 401, Responses
OPTIONS 204 and empty invalid POST 400. No valid inference payload was sent.

Installed source confirms provider `chatgpt-web-codex`, `/v1/responses` and `high`. Stable
3.8.50 still contains the old provider too; MG never selects it. This supersedes earlier
unreleased-branch retirement assumptions. The DEEP adapter remains pinned to HIGH, concurrency
1, no tools/fallback and conservative durable ambiguity. Continuity remains explicitly blocked.

**OWNER PLUS SESSION: MANUAL_ACTION_REQUIRED.** No login, session check, connector or real
DEEP inference was performed. Both private DEEP token files are absent; `deep` is not started.
Shared controls: enabled=false, session_ready=false, claimed=false. Owner must configure the
private connection and dedicated key/token files before enabling and doing the permitted live test.
Exact UI and recovery steps: [SERVER_RUNBOOK.md](SERVER_RUNBOOK.md). HIGH is not live-certified.

FREE eligibility is unchanged: Nex disabled, usable capacity UNKNOWN, no old execution retried;
Developer and Portal minimum INTERNAL, no reviewed INTERNAL-qualified candidate. No further
qualification or FREE calls were attempted during runtime completion. New closeout inference
count: **0** for every route. Earlier one failed smoke belongs to the prior task below.

Validation: 63 targeted Python tests passed before this checkpoint and were not repeated.
Only changed runtime shell/JS syntax, Compose and actual private browser/API health were checked.
Full 121 suite was not rerun. Existing dirty worktree preserved; untracked files have no tracked
Git baseline, so added-file diffs and current contents were reviewed without staging/discarding.
Closeout files: `deploy/deep.compose.yaml`, `deploy/start-browser.sh`, `deploy/cdp-proxy.mjs`,
`deploy/OMNIROUTE-LICENSE.txt`, this document and `docs/SERVER_RUNBOOK.md`; ignored
`.runtime/closeout/check_gateway.py` and review/evidence files are preserved. No Owner Pack
regeneration. No commit/push/production action. Paid API OFF.

The remaining sections are the **previous task's historical report**, not current runtime status.

Outcome: hardening and deterministic DEEP implementation pass; live service readiness is
BLOCKED. No server migration, consuming repository modification, commit or push occurred.
This report supersedes historical readiness statements in earlier handover documents.

| # | Requested result | Evidence / current result |
|---|---|---|
| 1 | Branch/status | `main`, HEAD `191932f Initial commit`. Existing README modification and untracked infrastructure foundation retained. |
| 2 | Files changed | Exact phase list below; no other repository touched. |
| 3 | Four hardening items | PASS: enforced client privacy floor; evidence-bound 429 retry review; persistent provider-wide stop; approved dataset manifest/hash. Targeted regression passed. |
| 4 | life-study eligibility | PUBLIC pilot qualified provisionally from existing synthetic evidence and fresh zero-cost catalog; currently BLOCKED because live smoke failed and candidate is disabled again. |
| 5 | life-study selected model | Exactly `nex-agi/nex-n2.5-pro:free` (`proposal-nex-pro`) during smoke. No random router, pool or Champion. No active model now. |
| 6 | life-study real smoke | FAIL: one POST through MG :8090 → policy → LiteLLM → pinned OpenRouter candidate; HTTP 502 EXECUTION_AMBIGUOUS caused by UNREVIEWED_429_ACCEPTANCE. No replay/fallback. |
| 7 | dev-code eligibility | BLOCKED / NO_ELIGIBLE_FREE_MODEL. Owner explicitly kept INTERNAL; available reviewed evidence is PUBLIC only. |
| 8 | dev-code selected model | NONE. Previously passed coding probes do not grant INTERNAL privacy approval. |
| 9 | dev-code smoke | NOT RUN, 0 requests. No Cline driven; not ready for a live Cline E2E on current policy. |
| 10 | Portal NORMAL eligibility | BLOCKED / NO_ELIGIBLE_FREE_MODEL. INTERNAL preserved. |
| 11 | Portal logical route | `portal-normal`; existing aliases `portal-workhorse`, `portal-light` remain FREE. No provider/model in client requests. Old `portal-deep` FREE alias removed. |
| 12 | Portal smoke | NOT RUN, 0 requests; no Portal code/database operation. |
| 13 | OmniRoute version/contract | Reviewed source commit `5a777a243b389355891bc3aa917139d7cef5d866` on release/v3.8.51; latest published release observed v3.8.50. Source build pinned, not a released v3.8.51 claim. |
| 14 | Retired provider | Exact retired chatgpt-web/cgpt-web IDs not used by executable MG routing. Historical/retirement references remain; current provider is chatgpt-web-codex. |
| 15 | chatgpt-web-codex readiness | Deterministic adapter PASS; LIVE BLOCKED. No authenticated connection configured by this phase. |
| 16 | Responses endpoint | Adapter pins `/v1/responses`, verified by mock HTTP assertions. Live endpoint NOT CERTIFIED. |
| 17 | HIGH route | Exact `chatgpt-web-codex/high`, high effort, no tools, no downgrade/Pro/combo. Preflight exact model presence plus output route validation. Owner runtime key scope still required. |
| 18 | Plus owner session | LIVE_DEEP_BLOCKED_BY_OWNER_SESSION_SETUP. Local shared controls inspected: enabled=false, session_ready=false, claimed=false. No cookie, login, connector or external session created. |
| 19 | DEEP concurrency | 1 via SQLite singleton claim. Cross-connection and restart safety tested. Separate copied state/another stack is not supported. |
| 20 | Continuity | MG persists a provider-neutral ordered PUBLIC transcript and replays prior user/final-assistant turns. Provider response state is optional and off by default. A fresh two-turn live check passed with exactly two provider dispatches. |
| 21 | Ambiguity/retry | No automatic retry. Possible dispatch retains singleton; duplicate execution ID never redispatches. Definite pre-dispatch failure recorded separately; explicit new execution ID may be used after review. No exactly-once claim or response replay cache. |
| 22 | Privacy | Life_OS PUBLIC-only. Developer/Portal NORMAL minimum INTERNAL. DEEP accepts PUBLIC text only; HR/ERP/employee/confidential access not approved. |
| 23 | Paid API | OFF, all FREE client paid_allowed=false and monthly budgets=0. No paid credentials or fallback added. Plus is separate owner subscription capability, not an OpenAI paid API. |
| 24 | External request budget | Exactly 1 inference attempt: life-study 1; dev-code 0; Portal 0; DEEP 0; benchmark 0; retries 0; paid requests 0. Separately: one public OpenRouter catalog refresh and one authenticated current-key metadata request. Public GitHub/documentation/source-build fetches also occurred; these are not inference and their internal HTTP attempt count is not instrumented. |
| 25 | Full tests | 121 passed; full suite run ONCE after 88 targeted tests passed. Two upstream TestClient deprecation warnings. Ruff PASS; strict mypy PASS (20 source files); wheel/sdist build PASS. |
| 26 | Secret scan | PASS. Scanner checks Git-visible files against local .env values, known token patterns and optional ignored DEEP token files; no values printed. It is a deterministic scan, not a guarantee over external volumes. |
| 27 | Docker/server readiness | Default MG image built, Gateway and actual LiteLLM locally healthy. Combined DEEP Compose config PASS, private ports/networks configured. OmniRoute/browser image build stalled fetching pinned Git source; stopped that build only. No successful Omni/browser image build, runtime startup or live session certification claimed. Server-final remains BLOCKED. |
| 28 | Owner action | Resolve source-build connectivity and complete private dashboard/session/HIGH key setup per SERVER_RUNBOOK.md. Separately review free capacity/429 outcome before re-enabling Nex; do not replay the ambiguous request. Obtain INTERNAL-approved free-model evidence to unblock Developer/Portal. |
| 29 | Portal integration remaining | Trusted executor calls dedicated POST `/internal/deep/execute` with separate bearer token and UUID execution/conversation IDs, PUBLIC input. Persist response and IDs; honor explicit reconciliation/session/continuity failures. Portal owns approval/task ownership. No multi-turn continuity or production-private-data readiness. Exact schema/examples in DEEP_BACKEND.md. |
| 30 | Final git status | Same broad preexisting dirty foundation layout: README modified; infrastructure files untracked. No staged changes, commits or pushes. Final status checked locally. |

## Live evidence and selection decision

Smoke request ID `daae3a62-5fdd-46f3-9295-99b248254bda`, UTC 2026-09-10 11:54:06;
candidate sequence `[proposal-nex-pro]`, attempt 1, fallback_count 0, latency about 2878 ms.
Gateway audit recorded cost_class FREE and cost_estimate_usd 0. No successful token usage was
returned; zero paid requests is a routing guarantee here, not a fabricated provider billing receipt.
Ignored sanitized evidence: `.runtime/pre-server/life-smoke.json`. Stable idempotency identity
is retained in the existing MG execution journal. No provider/raw error body or prompt log was read.

Current-key metadata authenticated successfully with FREE account/HEALTHY classification;
remaining provider quotas were unknown/null. That metadata did not guarantee serving capacity,
as the later actual request's 429 demonstrates. Catalog prompt/completion rates for the pinned
candidate were zero. Existing certification `.runtime/benchmark/cert-20260910-nex.json` had
two study, two coding and one Portal probe with reported dimensions 1.0, plus separate earlier
developer contract evidence. These remain tiny PUBLIC synthetic observations, not broad quality
or internal-data approval. No new benchmark or Champion/Fallback promotion was performed.

Zero-cost evidence review expires 2026-09-11 08:00 UTC. Candidate stays approved only for PUBLIC
pilot evidence, **enabled=false** after the failed live gate. No alternative was enabled.
Privacy review is scoped to public educational data and does not certify provider handling of
private organizational material. [OpenRouter privacy documentation](https://openrouter.ai/docs/guides/privacy/data-collection)
distinguishes OpenRouter processing from provider policies. Owner retained INTERNAL for other clients.

## Phase files

New implementation: `mg_ai/deep.py`, `mg_ai/deep_state.py`, `mg_ai/deep_control.py`,
`tests/test_deep.py`, `deploy/deep.compose.yaml`, `gateway/deep.schema.json`.

Updated configuration/tool: `policies/clients.json`, `routing/routes.json`,
`model-registry/models.json`, `scripts/check_secrets.py`. Config schema and ignored LiteLLM
render regenerated using `scripts/prepare.py` (schema may be byte-identical).

Documentation: `docs/DEEP_BACKEND.md`, `docs/SERVER_RUNBOOK.md`, this report,
`docs/CURRENT_STATE.md`, `docs/OWNER_SYSTEM_MAP.md`, `docs/OWNER_CODE_MAP.md`,
`docs/REQUEST_FLOWS.md`, `docs/SECURITY_BOUNDARIES.md`, `docs/FAILURE_AND_RECOVERY.md`,
`docs/OPERATIONS_RUNBOOK.md`, `docs/OWNER_APPROVAL_POINTS.md`.

Ignored local artifacts: public source review files, build output, one sanitized smoke report,
rendered proxy config, discovery report, generated package artifacts and owner symbol inventory.
Existing SQLite volume contains the single attempted smoke and default DEEP control tables.
No secrets were added to tracked files, and no owner session secrets were collected.

## Explicit release flags

```text
MG AI HARDENING: PASS
LIFE-STUDY: BLOCKED
DEV-CODE: BLOCKED
PORTAL NORMAL BACKEND: BLOCKED
OMNIROUTE: BLOCKED
CHATGPT-WEB-CODEX: BLOCKED
DEEP PLUS BACKEND: LIVE_DEEP_BLOCKED_BY_OWNER_SESSION_SETUP
OMNIROUTE PROVIDER: chatgpt-web-codex
DEEP ROUTE: chatgpt-web-codex/high
DEEP CONCURRENCY: 1
RETIRED chatgpt-web USED: NO
FREE → DEEP FALLBACK: NO
DEEP → FREE FALLBACK: NO
PAID API: OFF
PAID REQUESTS: 0
NVIDIA DIRECT REQUIRED: NO
ANTHROPIC API REQUIRED: NO
DIRECT_API_KEY REQUIRED: NO
OPENROUTER KEY EXPOSED: NO
AUTO PROMOTION: OFF
COMMIT: NO
PUSH: NO
PRODUCTION: UNTOUCHED
```
