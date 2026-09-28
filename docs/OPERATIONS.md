# Operations

## Startup, configuration, health

Follow README. `scripts/init_local.py` creates ignored secrets without overwriting them.
`prepare.py` validates all policy and derives secret-reference-only LiteLLM configuration.
The application image contains the same JSON. Regenerate/rebuild/recreate both after changes.
Do not edit `.runtime/litellm.yaml` by hand or add fallback/retry settings to the proxy.

`docker compose ps` shows container liveness. `scripts/docker_smoke.py` verifies the default
no-provider state with locally generated MG credentials, without printing tokens or calling
upstream. Do not run the default smoke after enabling providers. `/health/ready` requires
client authentication and returns its route eligibility. Detailed model health is available
server-side via `docker compose exec gateway python scripts/status.py`.

## Failure contract

| Condition | MG response / action |
|---|---|
| Missing/invalid MG token | 401 UNAUTHENTICATED; fix client secret |
| Wrong client route | 403 ROUTE_FORBIDDEN |
| Disallowed privacy/capabilities | 403 CAPABILITY_OR_PRIVACY_FORBIDDEN |
| Invalid/tool-incompatible request format | 400 INVALID_REQUEST |
| Body over 1 MiB or slow body | 413 REQUEST_TOO_LARGE / 408 REQUEST_READ_TIMEOUT |
| No approved/credentialed/qualified free route | 503 NO_ELIGIBLE_FREE_MODEL; configure or retry later |
| All safe free attempts rejected | 503 NO_ELIGIBLE_FREE_MODEL; inspect operator health |
| Client minute quota | 429 CLIENT_RATE_LIMITED |
| Monthly request budget | 429 REQUEST_BUDGET_EXHAUSTED; owner reviews policy |
| Provider 429 | Cool down and try next qualified free candidate |
| Provider auth failure/model removed (401/403/404) | Cool down 300s; safe free fallback |
| Proxy connection failure before dispatch | Safe free fallback |
| Provider 4xx other than classified rejection | 422 UPSTREAM_REJECTED; correct request, no blind retry |
| Read/write timeout, 408/409/5xx | 502 EXECUTION_AMBIGUOUS; reconcile |
| Malformed/oversized output, invalid generated JSON/tool args | 502 EXECUTION_AMBIGUOUS; reconcile |
| Same key previously recorded | 409 EXECUTION_ALREADY_RECORDED; inspect journal |
| Same key with changed payload | 409 IDEMPOTENCY_CONFLICT |
| Unhandled infrastructure/journal failure | 503 GATEWAY_UNAVAILABLE; conservative reconciliation |
| Paid configuration requested | Startup validation failure; paid execution unavailable |

Reconciliation errors have `execution_state=RECONCILIATION_REQUIRED`, retryable false.
Retryable indicates capacity may recover, not permission to mint a fresh execution identity.
Generic error bodies contain no raw upstream message. Check MG request ID and metadata logs.

## Restart and recovery

Use `docker compose restart` for a routine restart. Keep the named state volume. In-flight
DISPATCHED entries stay unresolved and block duplicate keys. Health cooldowns expire using
UTC time; restored old health may temporarily probe after expiry. Keep host NTP synchronized.
Stale free reviews become ineligible even if a key exists. No startup inference probes run.

Do not delete state to clear errors or quotas. Restore config and journal together where
possible. A stale backup cannot prove absence of executions after its snapshot: reconcile
consumer identities from that interval before reopening traffic. Default journal retention
is indefinite; no automated cleanup erases duplicate suppression. Request counters grow by
minute/month; plan reviewed archival as operational volume grows.

## Backup and restore

Create a consistent SQLite backup inside gateway, then export it into an access-restricted
ignored directory. The backup command refuses overwrites; use a unique date suffix:

```powershell
docker compose exec gateway python scripts/backup_state.py /state/backup-YYYYMMDD.sqlite
docker compose cp gateway:/state/backup-YYYYMMDD.sqlite .runtime/backup-YYYYMMDD.sqlite
```

Encrypt the exported backup and `.env` using company-approved backup tooling. Store approved
registry/policies/routes, Compose, image digests and dependency lock beside the backup (no
plain-text secrets in Git). Verify `PRAGMA integrity_check` and restore into a separate test
volume first. To recover: stop this stack, place the backup in a new local volume with UID/GID
10001 ownership, restore matching config/secrets, start isolated, reconcile post-backup
executions, then reopen client access. Keep the old volume until recovery is verified.

## Server 3

The `deploy/server3.compose.yaml` overlay adds bounded log retention; base Compose keeps
loopback-only MG ingress. A private TLS reverse proxy forwards from VPN/private IP to 8090.
Do not publish 4000. Give Server 1 Portal, Life_OS and developer machines distinct MG tokens.
No physical per-client deployment is needed. Resource limits are conservative starting points,
not load-test results. Single host/worker only; no HA promise. Arrange disk/clock monitoring,
secret rotation, restore exercise, reviewed free provider and application integration before
production. No deployment is performed by this repository task.

## Validation and upgrades

`python scripts/validate.py` runs the complete local milestone. Docker build, default health
smoke and isolated contract tests are separate. For contract tests:

```powershell
python scripts/prepare_contract.py
docker compose -p mg-ai-contract -f compose.yaml -f tests/compose.contract.yaml up -d
python scripts/docker_smoke.py --contract
docker compose -p mg-ai-contract -f compose.yaml -f tests/compose.contract.yaml down
```

Use the contract project only; it exposes localhost:18088 and a local synthetic provider.
After an existing contract run, recreate its mock and clear test cooldown state only by using
a new isolated test volume/project; never clear production state. Check mock call counts from
inside gateway to verify one request per model (500 no retry, 429 fallback, success).

Upgrade pins intentionally. Verify official signatures, licenses and advisories, refresh
hash lock, and run the contract suite. Do not follow uncontrolled latest tags. Do not enable
paid fallback to mask provider outages. Scope Guard is an advisory Git boundary, not a shell
sandbox; run it before review and leave commit/push owner-controlled.
