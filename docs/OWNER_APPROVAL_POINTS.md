# Owner-controlled decisions and external cost map

Pre-server decision: owner explicitly retained INTERNAL for Developer/Portal; PUBLIC-only
Nex evidence cannot authorize those clients. The authorized one-request Life_OS pilot returned
ambiguous 429, so Nex is disabled again. DEEP code/topology is prepared but owner-only session
setup, exact HIGH key scope and PUBLIC pilot enablement remain required. No external connector,
tools, privacy upgrade or production activation is implicit. See [server runbook](SERVER_RUNBOOK.md).

Approval here is an operating requirement, not a claim that the application implements an
approval UI, signatures or role-based administration. File access is the actual control plane.
This pack authorizes no model activation, benchmark or production deployment.

| Owner/admin decision | Required review / actual control |
|---|---|
| Enable model or provider's models | Model qualification still requires registry review/render/rebuild. Provider-wide SQLite enable/disable is a separate owner action with actor/reason audit; enabling a provider never enables models |
| Approve 429 retry semantics | Review provider+model+LiteLLM acceptance contract, record evidence/reviewer/expiry; unknown stays ambiguous. No real provider currently approved |
| Change client privacy minimum | Client.default_privacy is the minimum as well as default; reducing it changes the organizational security boundary and requires explicit owner approval |
| Promote candidate | Review completed MG evidence and qualitative suitability; `approved` and `enabled` are manually maintained booleans, not proof of owner identity |
| Change Champion | Review route-specific evidence and edit route.champion; score ranking precedes Champion preference |
| Set fallback expectations | No fixed fallback field; inspect entire eligible ordered pool, score thresholds and allowlists |
| Paid inference | Unsupported; JSON toggle fails validation. Requires separate explicit approval and new engineering, not this runbook |
| Privacy approval | Client/model privacy grants and model review assertions; public benchmark success cannot approve INTERNAL/CONFIDENTIAL data |
| Export data / benchmark dataset changes | Review actual data before updating dataset-approval.json hash, PUBLIC_SYNTHETIC class, reviewer and reason; do not auto-approve regenerated hashes |
| New live benchmark/certification campaign | Approve bounded candidate/route/request scope; commands send synthetic data and consume quota |
| Credential/token change | Store privately; recreate affected containers; never expose values in review or logs |
| Production deployment / commit / push | Explicit owner approval under AGENTS.md; not authorized by healthy local services or benchmark scores |
| Reconciliation or state restore | Owner/admin correlates execution evidence; preserve journal; no automatic replay/reset |

**Automatic decisions already implemented:** request validation, client admission limits,
eligibility filtering, deterministic ranking, safe fallback up to three candidates, response
validation, cooldown, duplicate blocking, and report scoring. None automatically approves a
model, changes Champion, enables payment or deploys production.

## External data / cost map

“Money: no” below means no paid model call is permitted by current guards, not a provider
billing audit or a claim that running servers/network is free. Approval can be standing scope;
normal authorized client requests do not need a separate human approval for each call.

| Action | Sends data externally? | Can consume quota? | Can cost inference money? | Currently allowed? | Owner approval? |
|---|---|---|---|---|---|
| Gateway live/ready; proxy liveliness | No, local only | No provider quota | No | Yes | Routine operation |
| Disabled-pool smoke | No provider prompt; local POST | No provider quota; empty pool not admitted | No | Only after script's empty-pool assertion | Routine verification |
| Capacity refresh | Yes, key to official metadata API | Metadata API rate limits; no model tokens | No model charge | Explicit CLI | Authorized metadata operation |
| Model discovery | Yes, public catalog GET | Metadata API rate limits; no model tokens | No model charge | Explicit CLI | Authorized metadata operation |
| Normal inference | Yes, prompt/tools to provider via proxy | Yes, model request/token quota + MG budgets | Paid blocked | Eligible approved FREE models only; current pool empty | Standing client/data/model approval |
| Live benchmark | Yes, approved synthetic prompts | Yes; bypasses Gateway client budgets | Paid blocked for pinned zero-price :free | --live, --approved-by, unique run ID, approved dataset hash, fresh catalog and enabled provider | Bounded campaign approval |
| Offline evaluation / recommendations / AST inventory | No | No | No | Yes | Local workflow |
| Paid inference | Would export prompts, but rejected | No dispatch through supported Gateway configuration | Prohibited | No | Approval alone cannot enable unsupported code |
| Docker build/pull | Registry/package download when needed, no prompts | Not provider model quota | Infrastructure costs outside inference policy | Local maintenance | Approved maintenance scope |

## Remaining owner-control limitations

No admin dashboard/API, no persistent fallback slot, no automated
reconciliation, no billing ledger, no quota refresh scheduler, no hot config reload and no
automatic promotion. Provider kill state is shared by the default Gateway and benchmark via
the existing Docker state volume; a nondefault deployment must explicitly share the same
control store. CLI inspection spans host files, image-baked config and separate SQLite
stores. Documentation commands distinguish them; they do not add these missing features.
Provider privacy and free eligibility remain manual evidence. Benchmark results are small
exact checks, and incomplete reports are excluded even where some route probes passed.
