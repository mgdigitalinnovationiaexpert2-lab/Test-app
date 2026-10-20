# Providers and activation

All supplied models are disabled examples, not recommendations. Put provider credentials
only in server secret storage. Clients receive separate MG credentials.

| Family | LiteLLM mapping | Boundary |
|---|---|---|
| OpenRouter | openrouter/<native-id> | Explicit :free pins; openrouter/free only for approved low-risk use |
| Groq | groq/<native-id> | Dedicated FREE project; Global ZDR and pinned-model review required |
| NVIDIA hosted / NIM | nvidia_nim/<native-id> | Operator endpoint and free-entitlement review |
| OpenAI-compatible | openai/<native-id> | Server-configured api_base |
| Native direct | e.g. anthropic/<native-id> | LiteLLM translation; paid candidates stay disabled |
| OmniRoute | reserved | Enabling rejected; no dependency or gateway chain |

## Activation

1. Run `python -m mg_ai.discovery`; review disabled proposals, pricing/metadata changes and removals in
   `reports/discovery.json`. This uses official model metadata and performs no inference.
2. Choose a pinned model. Verify every billing dimension, account limits, commercial terms
   and model/provider data policy. Free credits that roll into paid billing are unacceptable.
   Apply provider-side spending limits too.
3. Add evidence URL, dated approval, timezone-aware `free_verified_until` (normally at most
   24 hours for promotions), privacy/capability evidence. Keep the candidate disabled.
4. Evaluate synthetic fixtures in an explicitly approved isolated test configuration.
   Record normalized task scores, reviewed tier and capabilities; then approve/enable.
5. Add its server credential, run `scripts/prepare.py`, rebuild/recreate and check readiness.
   Perform one non-sensitive zero-cost smoke before real traffic.

Discovery never modifies runtime registry or promotes candidates. It checks all catalog
pricing fields conservatively; missing/invalid/nonzero prices are not free. Reports are
atomic. An external scheduler can run the CLI; none is installed. Disable removed/repriced
models promptly and recreate. Review expiry independently fails closed if refresh is missed.
A failed refresh leaves the previous report and runtime registry intact. Account quota changes
Run `python -m mg_ai.capacity` for a sanitized OpenRouter account observation. The official
current-key response exposes key-limit credits and free-tier metadata; it does not expose
remaining free-model requests/tokens, so those stay UNKNOWN. Account quota changes also use
observed 429 signals; public catalog metadata is not an account meter.

Groq uses the dedicated server-side `GROQ_API_KEY` through LiteLLM. The owner-confirmed FREE
project and Global ZDR are required evidence; expiry fails closed. Official response headers can
provide remaining daily requests, remaining minute tokens and reset intervals, which the capacity
parser preserves without inventing credits. Groq is never routed through OmniRoute.

NVIDIA promotional terms require account review. No GPU purchase or NIM production license
is assumed. Future self-hosting uses the same boundary but needs separate hardware/licensing
cost review; zero marginal inference is not zero total operating cost.

Official references reviewed 2026-09-06:
[OpenRouter catalog](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties),
[free variants](https://openrouter.ai/docs/guides/routing/model-variants/free),
[privacy](https://openrouter.ai/docs/guides/privacy/data-collection),
[NVIDIA adapter](https://docs.litellm.ai/docs/providers/nvidia_nim),
[compatible endpoints](https://docs.litellm.ai/docs/providers/openai_compatible).
