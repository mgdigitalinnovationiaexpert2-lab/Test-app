# Live OpenRouter certification — 2026-09-10

Authentication PASS; live Provider Capacity reports FREE, HEALTHY, reliable. The current-key
endpoint supplies no remaining request/token/credit values: these remain UNKNOWN. No key is
printed or included in artifacts. Capacity observations expire after five minutes.

## Real gateway smoke

Exactly one new public synthetic request traversed Gateway :8090 → policy/router → private
LiteLLM → `cohere/north-mini-code:free`. HTTP 200, exact `MG_OK`, 64 tokens, 3.526 seconds,
one attempt, zero fallback. The prior Nex ambiguous request was not replayed.
The temporary public-only dev-light route used minimum quality zero with empty benchmark
scores, rather than inventing quality evidence. Main registry and route champions were unchanged.

## Limited benchmark results

| Candidate | Benchmark requests | life-study | dev-code | portal-workhorse |
|---|---:|---|---|---|
| google/gemma-4-26b-a4b-it:free | 1 | No valid response | Not reached | Not reached |
| google/gemma-4-31b-it:free | 1 | No valid response | Not reached | Not reached |
| nex-agi/nex-n2.5-pro:free | 5 | All thresholds 1.00 (2/2) | All thresholds 1.00 (2/2) | All thresholds 1.00 (1/1) |
| nvidia/nemotron-3-super-120b-a12b:free | 4 | All thresholds 1.00 (2/2) | Code 1.00; tool/reliability 0 (1/2) | Not reached |

Gemma candidates were rejected with UPSTREAM_CONFIG_REJECTED on their first structured
request. The safe category combines authentication/configuration/not-found rejection;
the exact provider reason was not retained and is not inferred. Their harness zero scores
represent an unsuccessful request, not a measurement of language quality.

Super replaced unavailable candidates to obtain a second useful comparison, staying below
the planned 15 benchmark requests. Its tool request returned UPSTREAM_EXECUTION_UNCERTAIN;
the run requires reconciliation and was not retried. Its successful study probes are
partial evidence; the conservative recommendation generator excludes the incomplete run.
The intended 2–3 completed candidates per route could not be achieved: early termination
prevented Gemma from reaching dev/portal and Super from reaching portal. No broad model sweep ran.

Nex mean latency: study 13.136 s, code 3.562 s, portal 10.150 s. Scores refer only to five fixed
synthetic fixtures, not general model quality, Persian fluency or production reliability.

## Recommendations and developer contract

For each of dev-code, life-study and portal-workhorse: recommend Nex N2.5 Pro as a
PROVISIONAL Champion, pending qualitative/privacy/capacity/free-expiry and owner review.
No qualified Fallback. Super is an optional study Challenger for later review only;
its ambiguous run prevents certification. No model or Champion was promoted.

After Nex passed the measured dev-code thresholds, a temporary public-only configuration
tested its MG endpoint contract: unauthenticated /v1/models returns 401, authenticated
listing exposes the logical dev-code route, structured code response is correct, and
SSE returns a synthetic tool call, logical model identity and [DONE]. PASS, two new
requests. No tool was executed and no Cline session was driven. Interactive Cline E2E
is NOT TESTED.

This phase dispatched 14 inference requests: North 1 smoke, Gemma 26B 1, Gemma 31B 1,
Nex 5 benchmark + 2 developer contract, Super 4. Paid requests 0; fallback 0.
All pinned deployments enforce zero prompt/completion max price, no provider fallback,
no LiteLLM retries and free-only MG policies. Provider internals are not independently counted.

## Artifacts and final state

Ignored artifacts: `.runtime/cert-20260910/` (smoke, contract, temporary configuration,
recommendations), `.runtime/benchmark/cert-20260910-*.json`, refreshed `reports/discovery.json`,
local capacity SQLite and Docker certification execution journal. Prompt/response content is
excluded from result reports. The fixed synthetic fixture file is unchanged.

Temporary benchmark containers are removed and default Gateway/proxy configuration restored.
Main models remain disabled, route champions unset; absent an eligible free candidate the
default endpoint returns NO_ELIGIBLE_FREE_MODEL. Paid inference stays OFF.
Production code unchanged. Targeted operationalization tests: 20 passed, two upstream warnings;
the full 88-test suite was not rerun. Git remains main, unstaged, with pre-existing README
modification and untracked foundation directories. This phase updates documentation only
outside ignored runtime artifacts. No consuming repository was touched.

OPENROUTER KEY EXPOSED: NO; REAL FREE INFERENCE: PASS; PAID INFERENCE: OFF;
PAID REQUESTS: 0; AUTO PROMOTION: OFF; COMMIT: NO; PUSH: NO; PRODUCTION: UNTOUCHED.
