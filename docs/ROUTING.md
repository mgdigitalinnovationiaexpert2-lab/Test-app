# Routing and registry

`model-registry/models.json`, `routing/routes.json`, `policies/clients.json` are validated
at startup. `config.schema.json` describes their combined typed schema. `scripts/prepare.py`
validates and derives `.runtime/litellm.yaml`. Never edit generated proxy config; rebuild
and recreate after approved changes so MG and proxy use the same registry.

## Model fields

Provider/native identifier, enabled/approved, free/paid and cost tier, quality tier,
capabilities, context/output limits, credential environment name, endpoint, privacy classes,
data-policy URL/review, dated free evidence/expiry, promotional/random-router flags, health,
latency/failure metrics, capacity evidence, benchmark scores, coding/reasoning/Persian suitability and
champion/challenger role. Tool/structured/vision support is represented in capabilities,
avoiding duplicate booleans that could disagree.

Initial capabilities: TEXT, CODING, REASONING, TOOL_CALLING, STRUCTURED_OUTPUT, VISION,
LONG_CONTEXT, PERSIAN, DOCUMENT_ANALYSIS. Add strings with coordinated model/client/route
review. Metadata is evidence, not an independent guarantee of provider behavior.

## Eligibility and ranking

Require enabled, approved, credential present, FREE, unexpired free review, nonzero reliable
quota, reviewed privacy, capability superset, allowed model, sufficient context/output,
LIGHT/WORKHORSE/FRONTIER tier, category quality threshold and no active cooldown.
Runtime excludes challengers; random free routers require explicit route permission.

Rank by measured category quality, configured champion tie-breaker, health, known quota,
failure/latency preference, latency and deterministic ID. Missing score is ineligible at
default thresholds. A champion cannot bypass eligibility. Strong routes require FRONTIER
and higher measured quality; vendor marketing never assigns tiers.

`mg` request metadata can add requirements and increase context estimates. Actual tools,
JSON output and images infer capabilities automatically. UTF-8 serialized bytes are a
conservative text token bound; output reservation is added. Inline images are conservatively
counted too. This can reject feasible long/image inputs. A reviewed tokenizer adapter may
improve utilization later.

## Free-first and budgets

Best qualified free model → safe fallback → next qualified free model; at most three attempts.
Free exhaustion returns an MG error. No paid route, hidden LiteLLM fallback or random paid
model selection exists. OpenRouter also receives zero prompt/completion price ceilings and
provider fallback disabled. NVIDIA development access needs reviewed zero-cost entitlement
and expiry; it is not assumed permanently free for production.

`paid_allowed=true`, nonzero monetary budgets and enabled PAID models fail validation.
Per-client optional monthly request limits and model allowlists work now. Monthly budgets
use UTC calendar months; rate limits use fixed minute windows (boundary bursts are possible).
An admitted execution consumes one request even if inference fails. Invalid/no-provider
requests do not reserve quota.

## Health and provider capacity

States: HEALTHY, DEGRADED, RATE_LIMITED, UNAVAILABLE, DISABLED. Runtime records last
success/failure, latency, consecutive failures and cooldown. Numeric Retry-After is clamped
to 1..3600 seconds; missing/date/invalid values use 60 seconds. Auth/not-found rejections
cool down 300 seconds. Three failures mark UNAVAILABLE until expiry permits a new probe.
Success restores HEALTHY. Unknown runtime health starts DEGRADED. Configured DISABLED,
UNAVAILABLE or RATE_LIMITED requires operator change; runtime states expire automatically.
`python -m mg_ai.capacity` stores a credential-fingerprinted, expiring OpenRouter observation
from the official current-key endpoint. Missing fields remain null/UNKNOWN. Credit balance is
reported but does not by itself block free-model routing. Only fresh, reliable zero request or
token capacity, explicit unavailability, or authentication rejection can remove candidates.
Stale observations and observations for a rotated key are ignored.

Groq response-header parsing supports remaining requests/tokens and independent reset times,
but it is not marked reliable unless it came directly from an authenticated Groq response.
No Groq credential or execution adapter is configured in this release. Capacity refresh is a
manual/scheduled control-plane task; runtime never searches the web or calls provider account APIs.

OpenRouter `openrouter/free` is always identified as random and cannot be a Champion. Exhausted
or absent free capacity returns `NO_ELIGIBLE_FREE_MODEL`; paid candidates remain unselectable.
