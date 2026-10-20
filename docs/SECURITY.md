# Security

Inference, model listing and readiness require MG authentication. Only constant liveness
is public. Client tokens must be strong/distinct; missing/short/duplicate values fail startup.
Token digests use constant-time comparison. The proxy master key is separate. Request body
cannot override identity, provider, endpoint, credential, model deployment, retries or fallback.

Provider keys remain in server environment storage. `.env.example` has empty names only.
Secrets, state, reports and caches are ignored/excluded from Docker build context. Never put
secrets in JSON config, command arguments, logs or issue text. Windows `.env` inherits NTFS
ACLs; restrict to owner/admin using Windows security settings. On Server 3 use restricted
secret storage and encrypted backups. Host/container admins can read environment secrets
and are part of the trust boundary.

Defaults: paid off, unknown models disabled, raw logging off, no callbacks, no remote image/
schema fetches, no redirects, bounded input/output bodies and deadlines, persistent client
quotas and allowlists. Provider error text is discarded. Generated output remains untrusted;
business permissions and approval stay with consumers even when JSON/tool validation passes.

Both containers are non-root, read-only except designated volume/tmpfs, have no capabilities,
no-new-privileges, and resource limits. LiteLLM is private with master authentication; its
Docker log driver is disabled because upstream exception logs can include content. Use MG
allowlisted metadata and never enable debug logging on real prompts. Docker permits outbound
inference; it is not an egress allowlist. Add approved-endpoint firewall controls on Server 3.

Future ingress: WireGuard/Tailscale/private network, TLS reverse proxy, source restrictions
and concurrency limits. Preserve loopback binding and never publish the proxy. Local HTTP
is for local development. Rotate one client by changing its token and recreating gateway;
rotate provider keys server-side. Preserve journal history across rotations.

Scope Guard includes staged, unstaged and untracked non-ignored paths; no-renames captures
both rename sides. Sensitive path and schema policy is enforced, symlink/path escapes denied.
Ignored files and actual IDE actions lie outside Git diff visibility. Use OS permissions,
IDE approvals and secret checks. No automatic Codex review is configured.

Before production: review model terms/privacy, image signatures/vulnerabilities, private
ingress, restore, load limits and client behavior. No penetration test, production certification,
or complete supply-chain audit is claimed.

Developer credentials may include explicitly allowlisted additional token environment variables. Each credential can be rotated or revoked independently while mapping to the same developer policy; quotas and audit identity remain scoped to the logical developer client.
