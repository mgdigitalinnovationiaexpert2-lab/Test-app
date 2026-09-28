# ADR 0001: MG boundary with private LiteLLM Proxy

Accepted for the initial foundation, reviewed 2026-09-06.

Use official LiteLLM stable container v1.99.1 pinned by digest, with a typed FastAPI facade
for MG client/free/privacy/quality/ambiguity rules. No proxy admin endpoints reach consumers.
No Postgres/Redis needed: MG credentials, quotas and journal use the facade and SQLite.
One deployment per alias; all proxy retries zero and fallback lists empty. No OmniRoute chain.

The [tagged license](https://raw.githubusercontent.com/BerriAI/litellm/v1.99.1/LICENSE)
places the core under MIT, enterprise code separately licensed. Internal commercial core use
is permitted subject to notices/license conditions; no enterprise-only feature is required.

Official [deployment](https://docs.litellm.ai/docs/proxy/deploy),
[config](https://docs.litellm.ai/docs/proxy/config_settings),
[authentication](https://docs.litellm.ai/docs/proxy/virtual_keys),
[budgets/rate limits](https://docs.litellm.ai/docs/proxy/users) and
[fallback](https://docs.litellm.ai/docs/proxy/reliability) documentation confirms Docker,
authentication, aliases, optional quotas and API support. MG-specific policy remains independent
of proxy database/enterprise features; native protocol translation stays upstream.

The [v1.99.1 release](https://github.com/BerriAI/litellm/releases/tag/v1.99.1) is Docker-only;
tag `v1.99.1` exists, `main-v1.99.1` does not, and no 1.99.1 PyPI package exists. A newer normal
release exists; the reviewed stable image is this baseline. Release notes document cosign
verification using a commit-pinned public key.

Tradeoffs: useful extra internal hop, independent upgrades, single-host journal, documented
API subset, buffered SSE. Paid execution and multi-host state need explicit migrations.
No blocking incompatibility was found requiring another core or a custom provider proxy.
