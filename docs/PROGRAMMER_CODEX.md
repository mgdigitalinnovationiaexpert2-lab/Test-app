# Programmer Codex integration

OpenCode keeps `mg-ai/dev-code`, `@ai-sdk/openai-compatible`, the programmer MG token,
and `http://127.0.0.1:18090/v1`. Gateway authenticates and authorizes the developer client,
applies its quota and execution journal, then translates Chat Completions to private
OmniRoute `/v1/responses` with pinned `cx/gpt-5.6-sol-high` and high reasoning.
The owner authorized programmer workloads on this subscription route. PUBLIC and INTERNAL
are allowed; CONFIDENTIAL, vision, and structured-output requests fail closed.
Subscription usage is not classified as a zero-price FREE model or metered paid API usage.
Explicit `mg.max_cost_class=FREE` rejects dev-code. Paid API inference remains disabled.

System instructions, messages, function definitions, function calls and tool outputs are
translated without truncation. Each turn sends caller-owned history; no Deep journal,
previous-response optimization, OAuth material, or hidden reasoning enters this API.
Programmers execute tools locally. MG validates returned tool names and argument schemas.
The existing SSE contract buffers and validates the entire upstream answer before sending
Chat Completions chunks, tool-call indices, optional usage, and `[DONE]`. It is compatible
streaming framing, not incremental token delivery. The upstream read timeout is 240 seconds.

`max_tokens` is accepted (up to 32768) and translated to `max_output_tokens`. The installed
OmniRoute Codex executor removes this field because its subscription backend rejects it.
Therefore this is **not a hard output-token cap**. Responses include
`X-MG-Output-Limit: upstream-best-effort`; do not use this route where a hard cap is required.
Sampling controls and stop sequences are rejected instead of silently discarded.
Input plus requested output is conservatively bounded at 400000 (UTF-8 input bytes plus
requested tokens); the outer 1 MiB HTTP request limit and 256-message/64-tool limits remain.

One worker permits one in-flight programmer Codex request. There is no retry, fallback,
or account rotation in the MG adapter. Ambiguous outcomes retain the execution journal and
return nonretryable HTTP 422 to prevent common coding SDK 429/5xx retry loops. Clients must
not replay an uncertain request. Reused idempotency keys are blocked before dispatch.
OmniRoute's existing pinned single-connection/model policy remains an upstream dependency.

`dev-light` explicitly selects the qualified Groq Qwen Champion through LiteLLM and has no
automatic fallback. GPT-OSS is not a programmer fallback. Existing Portal and other FREE
routes retain their registry, privacy floors and provider path. Select `mg-ai/dev-light`
explicitly for small requests after adding that logical model to the local OpenCode UI.

## Deployment

Apply `deploy/programmer.compose.yaml` with the main compose file. Only Gateway joins the
existing internal OmniRoute bridge (as `programmer_upstream`), retains its FREE proxy network,
and mounts the existing model-scoped OmniRoute inference key read-only. OAuth/session state
stays in OmniRoute. The Deep client credential is not mounted. Neither upstream port nor
provider credentials are exposed to programmers. Deep remains separately authenticated and idle.
Gateway's image uses a separate `programmer-v1` tag so rebuilding does not replace Deep's tag.

From the Ubuntu runtime repository, after syncing only reviewed files:

```sh
docker build -f gateway/Dockerfile -t maghsoud-ai-infrastructure-gateway:programmer-v1 .
sudo docker compose -f compose.yaml -f deploy/programmer.compose.yaml config --quiet
sudo docker compose -f compose.yaml -f deploy/programmer.compose.yaml up -d --no-deps --no-build gateway
```

Sudo is needed for Compose to read the intentionally protected `.env`. Do not change its
permissions, echo credentials, or export container environment arrays. Do not recreate Deep,
LiteLLM, OmniRoute or other services. Future Gateway deployments must include this overlay.

Validate unit tests, schema and secret checks before deployment. Afterwards check programmer
readiness and existing FREE eligibility without inference, make one small dev-code request,
then one isolated synthetic OpenCode coding exercise with a tool-result follow-up. Stop on
ambiguity; do not rerun successful checks or infer live certification from offline tests.

Translation reference: [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling).
