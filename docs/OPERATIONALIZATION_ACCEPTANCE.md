# Operationalization acceptance — 2026-09-09

Historical milestone. The subsequent live certification, successful smoke, benchmark results,
and developer contract are recorded in [LIVE_CERTIFICATION_20260910.md](LIVE_CERTIFICATION_20260910.md).

This report resumes the interrupted MG-only operationalization work. It does not reopen the
approved gateway architecture and does not cover Portal DEEP. Evidence and command output are
kept in ignored `.runtime/resume-20260909/`.

## Result

OpenRouter authentication passes with the locally configured key and reports a free-tier,
healthy account. One pinned free smoke request used
`nex-agi/nex-n2.5-pro:free` through Gateway :8090, policy/router, private LiteLLM and
OpenRouter. The response failed MG validation as `INVALID_UPSTREAM_RESPONSE`, so the gateway
returned `502 EXECUTION_AMBIGUOUS`. It was not replayed, no benchmark was started and no paid
request was made. Gateway and private LiteLLM were restored to the default disabled-provider
configuration after the test.

## What existed before resume

The dirty working tree already contained the MG-owned FastAPI gateway, private digest-pinned
LiteLLM, free-only client policies, logical routes, registry, health and quota hints, persistent
execution journal, ambiguity handling, metadata logging, Scope Guard, offline synthetic evals,
controlled OpenRouter discovery, Docker operation and prior integration/release documentation.
The prior work also contained disabled examples and disabled proposals for North Mini Code,
MiniMax M3, Nemotron Nano Omni and Gemma 4 31B. All existing work was preserved.

## Work completed during resume

- Provider Capacity V1 persists sanitized, expiring, credential-fingerprinted observations.
  OpenRouter uses the official current-key endpoint; unknown request/token quota stays null.
  Groq response-header parsing preserves request/token remaining values and separate reset times,
  but affects routing only when identified as a verified direct response.
- Runtime routing excludes candidates only on fresh reliable capacity evidence. Stale data,
  rotated-key data and zero credit balance do not invent free-model exhaustion.
- Model Intelligence detects new, removed, free-to-paid and catalog metadata changes; creates
  route suggestions; accepts schema-validated manual external evidence; never edits the registry.
- Candidate/privacy schema now records retention, training-use and confidential eligibility.
  Unknown evidence cannot authorize confidential workloads. Random `openrouter/free` cannot be
  configured as Champion.
- The live MG runner uses a fixed synthetic dataset for life-study, dev-code and
  portal-workhorse, one pinned explicit `:free` model, a separate private LiteLLM project,
  stable run identity and a persistent pre-dispatch journal. Reports exclude prompt/response
  content and cannot promote a model.
- The runtime error after safe free-pool exhaustion is consistently
  `NO_ELIGIBLE_FREE_MODEL`. Paid candidates remain statically invalid for all clients.

## Provider and discovery results

OpenRouter authenticated connectivity: PASS. The official current-key endpoint returned HTTP
200, `is_free_tier=true`, and a healthy reliable observation. Request/token limits and credit
remaining were not supplied, so those values remain UNKNOWN rather than being treated as
unlimited. The
public official catalog refresh succeeded with 19 current zero-price `:free` entries. It found
new Nex N2.5 Mini/Pro entries and detected that MiniMax M2.7/M3 disappeared from the free list.
GLM 5.2 was not present. Catalog absence is not interpreted as a permanent provider statement.

Seven relevant pinned candidates are queued, disabled and unapproved: North Mini Code,
Nemotron 3 Ultra, Nemotron 3 Nano Omni, Nemotron 3 Super, Gemma 4 26B, Gemma 4 31B and Nex N2.5
Pro. They are discovered candidates, not qualified models. Verified capability sets remain
empty or minimal historical TEXT metadata until live probes and human review pass.

Rejected/removed: Nex N2.5 Pro is rejected for this certification attempt because its only
smoke response was not valid under the MG OpenAI-compatible response contract. The ambiguous
dispatch is not eligible for retry. `openrouter/free` is rejected as Champion because selection is
nondeterministic. MiniMax M2.7/M3 are not current targets because the refreshed catalog removed
them. No model was rejected for quality because no live model responses exist.

Groq: NOT_CONFIGURED. The capacity parser follows official remaining-request/token headers,
but no legitimate account/key or direct response was available. Direct NVIDIA onboarding was
not implemented as directed; NVIDIA models may be evaluated through pinned OpenRouter entries.

## Benchmarks and recommendations

North Mini Code preflight successfully prepared an isolated configuration. A later pinned
Nex N2.5 Pro smoke sent exactly one free request and failed MG response validation. Because
the live benchmark was conditional on a successful smoke, no route benchmark was run:

| Route | Live result | Champion | Fallback | Privacy |
|---|---|---|---|---|
| life-study | NOT RUN | none | none | public synthetic probes only |
| dev-code | NOT RUN | none | none | public synthetic probes only |
| portal-workhorse | NOT RUN | none | none | public synthetic probes only; confidential use denied |

Deterministic harness tests prove schema scoring, source faithfulness failure, scoped code/tool
checks, malformed output classification, no replay after run identity, and stop-after-ambiguous
behavior. These verify runner mechanics; their synthetic answers are not model quality results.
Qualitative Persian, reasoning and code review remain mandatory after exact thresholds pass.

## Failure, cost and endpoint evidence

The real LiteLLM/local synthetic provider contract produced exactly one mock 500, one safe 429
and one success. The 500 did not fall back and required reconciliation; the known-safe 429
fell back once. Unit coverage also confirms disabled Champion fallback, malformed structured
output containment and paid candidate exclusion. When only a qualifying paid candidate exists,
the gateway returns `NO_ELIGIBLE_FREE_MODEL`; provider call count and paid spend are both zero.

The final gateway image built and both gateway and LiteLLM are healthy. The prior local mock
contract passed, but the live pinned smoke failed response validation. A dev-code Champion was
not qualified, so the conditional Cline endpoint check was not run. No Cline extension session
was driven and no interactive Cline E2E claim is made.

## Validation

- Full repository validation once: 88 tests passed; Ruff passed; strict mypy passed for 16
  source modules; configuration/schema generation, wheel/sdist build and secret scan passed.
- Final Docker gateway build passed; gateway and private LiteLLM health passed.
- Real LiteLLM/mock-provider contract passed with counts `mock-error=1`, `mock-limit=1`,
  `mock-ok=1`; isolated containers/network were removed.
- Git whitespace check passed. Two upstream TestClient/AnyIO deprecation warnings remain.
- Existing release-gate vulnerability findings in RELEASE_GATES.md remain unresolved and must
  be dispositioned before production. No production deployment was attempted.

## Acceptance matrix

| Item | Status | Evidence/limit |
|---|---|---|
| A. Gateway :8090 | PASS | Healthy loopback endpoint and authenticated smoke |
| B. OpenRouter authenticated connectivity | PASS | HTTP 200; healthy free-tier account |
| C. Groq provider | NOT_CONFIGURED | `GROQ_API_KEY` absent; capacity header parser tested |
| D. Real FREE inference | FAIL | One Nex N2.5 Pro response failed MG validation; no replay |
| E. Provider Capacity | PASS | Live reliable observation; quotas remain UNKNOWN because absent upstream |
| F. Model Intelligence | PASS | Live catalog delta/recommendations; no auto-promotion |
| G. Controlled candidate discovery | PASS | 19 free entries; all disabled |
| H. Live MG Benchmark runner | NOT RUN | Required smoke did not succeed |
| I. life-study benchmark | NOT RUN | Required smoke did not succeed |
| J. dev-code benchmark | NOT RUN | Required smoke did not succeed |
| K. portal-workhorse benchmark | NOT RUN | Required smoke did not succeed |
| L. Champion/Fallback recommendations | BLOCKED | No qualifying MG results |
| M. Safe 429 fallback | PASS | Real LiteLLM/mock contract and unit tests |
| N. Ambiguity containment | PASS | One call, no fallback, reconciliation |
| O. Paid kill switch | PASS | Zero provider calls and zero spend in paid-only condition |
| P. Cline-compatible endpoint | NOT RUN | No dev-code Champion qualified |
| Q. Real Cline interactive smoke | BLOCKED | No qualified Champion and no Cline session driven |

## Resume change set

Changed during this resume: `.env.example`, `README.md`; architecture/current-state/free
candidate/live-benchmark/operations/provider/routing documentation; live benchmark fixtures,
thresholds and Compose; gateway Dockerfile; capacity/config/discovery/gateway/live-benchmark/
model-intelligence/observability/proxy/routing/state modules; generated config schema and model
registry; gateway and operationalization tests. The exact baseline comparison is stored in
`.runtime/resume-20260909/baseline.json`.

No Portal, Life_OS, Website or Employee Import source was changed during this resumed task.
The Infrastructure working tree remains intentionally uncommitted on `main`; the foundation is
mostly untracked, matching the pre-existing state. No files are staged.

Paid inference: OFF. Hidden paid fallback: OFF. OpenRouter random router as Champion: NO.
Pinned free smoke model: Nex N2.5 Pro; qualification failed. Automatic model promotion: OFF.
Owner approval for promotion: REQUIRED. Commit: NO. Push: NO. Production: UNTOUCHED.
