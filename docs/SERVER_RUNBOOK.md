# Owner server runbook

Local preparation only. Production migration remains a separate owner decision.
Run from the MG Infrastructure root. Never run `down -v`; preserve existing volumes.

## A–C. Gateway, LiteLLM and FREE registry

Protect ignored `.env`; clients receive their own MG token only. Run
`python scripts/prepare.py`, `docker compose build gateway`, then
`docker compose up -d gateway proxy`. Gateway binds loopback 8090; proxy has no host port.
The image contains policies/registry: rebuild/recreate after approved changes.
Never run `scripts/init_local.py` as a routine restart or overwrite existing credentials.

Nex N2.5 Pro is the reviewed PUBLIC `life-study` Champion after two successful qualification
fixtures and one exact-response Gateway smoke on 2026-09-12. Its current zero-cost evidence
expires 2026-09-13 08:26 UTC. Expired evidence blocks use automatically. Review current catalog,
capacity and privacy evidence before extending it; discovery never promotes models.
Life_OS uses `life-study` with PUBLIC educational text. Developer `dev-code` and Portal
`portal-normal` (aliases `portal-workhorse`, `portal-light`) retain INTERNAL minimum and
remain blocked until an INTERNAL-reviewed free candidate qualifies. Never lower these floors
or add Plus fallback to clear a health indicator. All paid budgets stay zero.

Groq is enabled only for INTERNAL `portal-normal` and `dev-code`. The owner confirmed the
dedicated FREE project and Global ZDR. Pinned `qwen/qwen3.8-27b` is Champion; pinned
`openai/gpt-oss-120b` is an approved, disabled Challenger. The key remains only in ignored
`.env` as `GROQ_API_KEY`. Recheck catalog activity, FREE account status and Global ZDR before
extending evidence expiry. Never route Groq through OmniRoute.

## D–E. Optional OmniRoute and private headed browser

Current DEEP inference backend (2026-09-12): active OpenAI Codex OAuth, logical route
`cx/gpt-5.6-sol-high`. The dedicated OmniRoute key is mounted from ignored host file
`.runtime/deep/omni-api-token` as `/run/secrets/omni_api`; never put it in `.env`, docs or chat.
The MG executor token is independently mounted as `/run/secrets/deep_client`.
Authenticated catalog and one exact-response synthetic smoke passed. No OpenAI API key is used.
The browser-backed ChatGPT Web Codex route below is retained as historical setup information;
it is not the selected DEEP inference backend.

Verified closeout checkpoint: OmniRoute **3.8.50-web**, official Docker Hub image, installed
and healthy. Browser sidecar healthy; headed Chromium and Xvfb processes verified; private
CDP HTTP 200 and Playwright WebSocket connection passed. No Plus login or inference performed.
Dashboard redirects to `/login` and returns 200 on loopback. Private API `/v1/models` rejects
an invalid credential with 401; `/v1/responses` OPTIONS returns 204 and an empty invalid POST
returns 400. These are transport/validation probes, not successful inference certification.

Use the reviewed pinned [deep overlay](../deploy/deep.compose.yaml):

```text
docker compose -f compose.yaml -f deploy/deep.compose.yaml --profile deep config --quiet
docker compose -f compose.yaml -f deploy/deep.compose.yaml --profile deep pull omniroute chatgpt-web-codex-browser
docker compose -f compose.yaml -f deploy/deep.compose.yaml --profile deep up -d omniroute chatgpt-web-codex-browser
```

Both services use the official image without source build:
`diegosouzapw/omniroute:3.8.50-web@sha256:ee6168e2a48fd2482c0416e6a53a27dc2f3609e169cc5f873ff7b1e5a520cf53`
(linux/amd64 manifest; multi-platform index digest
`sha256:0511348f97db9af067b90edfcd9508793c5ed74f56da7abc475624fb02a977df`).
The running package reports 3.8.50 and contains the Codex provider, native Responses executor
and HIGH route. Do not substitute floating latest/main/next or the earlier source-build overlay.
The browser reuses this image's Playwright Chromium, with the small MIT-licensed v3.8.50
CDP proxy in `deploy/cdp-proxy.mjs`. `deploy/start-browser.sh` starts Xvfb directly because the
stable image lacks xauth; X11 TCP is disabled, its Unix socket is container-private, and `/tmp`
is ephemeral. Browser processes run as node after ownership of the dedicated profile is set.
Only admin 20128 is loopback-published. API 20129 stays private. The browser runs headed
Chromium in Xvfb without a physical display; CDP proxy 9223 is container-private and Chromium
9222 loopback inside its container. No VNC/noVNC port is published. Do not mount Docker socket.
`deep_boundary` is internal and disconnected from FREE; `browser_private` allows required
Internet egress. FREE Gateway has no network attachment to OmniRoute/browser.
OmniRoute and browser logs are disabled to avoid credential/session leakage.

## F. Owner session setup and recovery

Current gate: `OWNER PLUS SESSION: MANUAL_ACTION_REQUIRED`. Never paste secrets into chat.
Open loopback dashboard `http://127.0.0.1:20128`; on a remote server use an authenticated
SSH tunnel: `ssh -L 20128:127.0.0.1:20128 <owner>@<server>`.
The local page currently opens at `/login`. Use the owner's local dashboard admin credential.
If it must be reset, run the installed `node bin/reset-password.mjs` interactively in the
OmniRoute container from an owner-only terminal, then restart OmniRoute. Do not supply passwords
as command arguments or through Codex. No password reset has been performed by this task.

1. Open **Providers**, select **ChatGPT Web (Codex)** (`chatgpt-web-codex`), and add/edit the
   owner's connection. Stable 3.8.50 also lists the old **ChatGPT Web (Plus/Pro)** provider;
   do not select it. Its presence in the release does not authorize its use by MG.
2. In that private dashboard only, provide the full Cookie header from the owner's signed-in
   ChatGPT Plus browser. For text-only leave tunnel ID and runtime key both blank; retain the
   connector name field if supplied. Stable 3.8.50 validation requires a nonempty connector-name
   field even for text-only; use `OmniRoute Codex v2` as the label, not as a claim that an external
   connector was installed. Runtime tools remain empty/disabled and no connector is created.
3. Run **Test Connection** / connection check; confirm browser, sign-in and Temporary Chat.
   Verify the owner's signed-in account has the intended Plus/Sol capability and that the
   connection's models include `chatgpt-web-codex/high`. Stable 3.8.50 validation reports browser,
   login and Pro availability, not a separate explicit High-detected flag; model presence alone
   is not live High certification. If High is absent, stop; never select Pro or a lower route.
   Save the verified connection. A later one-request MG test is still required to certify High.
4. Historical browser route only: create a dedicated OmniRoute API key with only `chatgpt-web-codex/high` allowed. Keep a
   single intended owner connection. No combos, other providers, account rotation pool or
   fallback for this key. Confirm runtime routing behavior before declaring live readiness.
5. Store this key privately in ignored `.runtime/deep/omni-api-token`; generate a distinct
   random MG executor token (at least 32 characters) into `.runtime/deep/client-token` using a
   local secret manager. Neither file belongs in Git or `.env.example`. Restrict filesystem
   permissions to the owner/runtime; Compose mounts them read-only. Do not reuse FREE tokens.
6. Both token files are currently absent; the MG `deep` service has not been started. After
   privately configuring those files, start `deep` with the same overlay/profile. Controls
   were verified disabled/session-unavailable, concurrency 1 and no active claim.
   Only after the private check, run inside the service:

```text
docker compose -f compose.yaml -f deploy/deep.compose.yaml --profile deep exec -T deep python -m mg_ai.deep_control session-ready --actor owner --reason "Private owner session checked"
docker compose -f compose.yaml -f deploy/deep.compose.yaml --profile deep exec -T deep python -m mg_ai.deep_control enable --actor owner --reason "PUBLIC text-only pilot approved"
```

These are manual attestations, not inference checks. Then at most one synthetic first-turn
request may certify the live boundary. Never automatically repeat an ambiguous result.
When expired, disable DEEP, edit the connection, provide a fresh Cookie privately, check and
save again. Use the dashboard doctor to distinguish browser/session/capability failures.
If an interactive challenge cannot be cleared with refreshed private session setup, keep DEEP
blocked. Any temporary browser recovery UI must be authenticated and loopback/SSH-only;
this overlay deliberately does not deploy VNC infrastructure. Do not expose CDP to recover it.

## G–H. Emergency controls

FREE provider-wide stop:
`docker compose exec -T gateway python -m mg_ai.provider_control disable openrouter --actor owner --reason "Emergency stop"`.
Use `list` to inspect; enable only after review with actor/reason. Config enable flags cannot
override the persistent stop. It prevents new dispatches, not an already transmitted request.

DEEP stop (shared volume, works even when DEEP is stopped):
`docker compose exec -T gateway python -m mg_ai.deep_control disable --actor owner --reason "Emergency stop"`.
Also mark `session-unavailable` after session expiry. Provider control can independently disable
`omniroute`. Neither command deletes executions, cancels an already dispatched browser turn,
or clears an ambiguous claim. Never use repeated restarts as a retry mechanism.

## I–J. Persistence, backup and health

Preserve `mg-state`, `omni-data`, `omni-browser`; `mg-state` now contains approved PUBLIC DEEP
conversation transcripts and must be protected as content. Protect encrypted data and associated
key material together in owner-controlled backups. Existing SQLite backup script uses the backup
API; do not copy only a live WAL main file. Stop private Omni/browser services for consistent
volume backup, without deleting volumes. Restore into an isolated environment first.
Do not run two stacks against the same Plus session. Concurrency is one per shared MG state;
separate copied state cannot coordinate and must not be run simultaneously.

`docker compose ps` and `/health/live` establish process health only. Gateway authenticated
`/health/ready` shows route readiness; check each client's privacy eligibility separately.
Private DEEP authenticated `/health/ready` shows local flags, concurrency and
`upstream_checked: false`; it does not prove Plus login. `deep_control status` shows claim state.
For ambiguity keep the singleton claim and inspect sanitized `deep_runs` IDs/status plus existing
upstream evidence. Reconcile only after establishing one of the evidence-based outcomes:

```powershell
docker compose -f compose.yaml -f deploy/deep.compose.yaml --profile deep exec -T deep python -m mg_ai.deep_control reconcile --execution-id <UUID> --outcome <CONFIRMED_NOT_EXECUTED|CONFIRMED_FAILED|CONFIRMED_COMPLETED|UNRESOLVED> --actor <OWNER_ID> --reason "<SANITIZED_EVIDENCE>"
```

The action is audited. `CONFIRMED_COMPLETED` requires an already persisted MG response ID.
`UNRESOLVED` is allowed only after the 240-second transport settlement bound; it permanently
blocks that conversation, keeps the execution ID non-retryable and releases the global slot for
unrelated tasks. The journal contains approved PUBLIC DEEP user/final-assistant transcript text;
do not expose it in routine status output.

The Portal executor integration is documented in [DEEP_BACKEND.md](DEEP_BACKEND.md).
Do not send Portal production data until a separate privacy decision and live certification.

For rollback, keep the previous image digest and protected volume backups. Disable DEEP before
changing images. Recreate only the affected optional services with an explicitly reviewed digest;
do not downgrade a migrated database in place or delete volumes. Restore a compatible backup in
isolation when schema compatibility is uncertain. The FREE stack is unaffected by this overlay.

## Developer client contract (previously checked, no client machine configured)

OpenAI-compatible base URL: `http://127.0.0.1:8090/v1` on the MG host; remote developers need
an authorized private tunnel/reverse proxy, not their own localhost. Use
`Authorization: Bearer <MG_DEV_TOKEN>` and logical model `dev-code` with POST
`/v1/chat/completions`. `/v1/models` returns authorized logical aliases, not eligibility.
`messages` is required; standard function tools/tool_choice and buffered SSE are supported.
SSE is emitted after upstream completion, with tool-call deltas and `[DONE]`, not live token
forwarding. Unknown request fields are rejected. No provider credentials belong in OpenCode/Cline.
The 63 targeted checks passed earlier; no interactive OpenCode/Cline E2E is claimed. Live coding
remains blocked because no reviewed INTERNAL-qualified FREE model exists.
