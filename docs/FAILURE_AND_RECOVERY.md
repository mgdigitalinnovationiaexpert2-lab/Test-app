# Failure and recovery

Pre-server live PUBLIC smoke hit UNREVIEWED_429_ACCEPTANCE, returned EXECUTION_AMBIGUOUS,
and was not retried. Nex was disabled again. DEEP defaults session-unavailable/disabled;
ambiguous or crashed claims survive restart and hold concurrency one. No automatic claim
release or continuation exists. See [DEEP failure contract](DEEP_BACKEND.md) and
[private owner recovery](SERVER_RUNBOOK.md).

Read the MG error code and journal before retrying. `RECONCILIATION_REQUIRED` means the system
cannot establish nonexecution. It does not mean automatic recovery is running. See
[request flows](REQUEST_FLOWS.md) and [journal commands](OPERATIONS_RUNBOOK.md).

| Symptom | Actual system behavior | Safe owner action | Unsafe action | Verify recovery |
|---|---|---|---|---|
| Provider unavailable | Connect failure to proxy safe; upstream >=500 ambiguous; configured unavailable model excluded | Identify category; disable affected model, inspect health and provider metadata | Treat every unavailable response as safe to repeat | Local health/config checks; later separately approved new synthetic probe if needed |
| Upstream 429 | Only matching unexpired provider/model/adapter review permits RATE_LIMITED_SAFE; otherwise AMBIGUOUS / UNREVIEWED_429_ACCEPTANCE with no fallback | Preserve journal for unknown semantics; for reviewed-safe rejection respect cooldown | Infer nonacceptance from 429 alone or invent evidence to force retry | Check review identity/expiry and execution record; no real provider currently has approved 429 semantics |
| Gateway 429 | Admission limits reject before provider dispatch | Wait minute window or review monthly client budget | Raise limits to bypass policy without review | Journal shows no new dispatch for rejected call; budget window has room |
| Timeout reading client body | Boundary returns REQUEST_READ_TIMEOUT before handler dispatch | Correct caller connectivity/body size | Diagnose as provider failure and rotate provider | Local small request validation with providers disabled |
| Connect/pool timeout before proxy reached | PROXY_NOT_REACHED → SAFE_TO_RETRY; may try next candidate | Restore proxy/network; inspect logs/cooldown | Assume all timeout classes are pre-dispatch | Proxy local liveliness responds, Gateway ready read succeeds |
| Timeout after possible dispatch | HTTP errors other than connect/pool → DISPATCH_UNCERTAIN; AMBIGUOUS | Preserve key, ID and journal; inspect provider activity privately if available | Resubmit with a new key; clear journal to force a retry | Reconcile actual execution externally; no automated replay facility exists |
| Ambiguous execution / process crash | 502 reconciliation, or DISPATCHED left after crash; duplicate key rejected | Keep volume; correlate request ID, timestamp, audit and provider evidence | Delete DISPATCHED/AMBIGUOUS rows or assume no answer means no execution | Document known outcome; retain record. Any new task must be explicitly distinct, not a disguised retry |
| Malformed provider response/schema/tool call | INVALID_UPSTREAM_RESPONSE → AMBIGUOUS; no fallback | Inspect adapter compatibility and synthetic reproduction offline; retain evidence | Relax validation or rerun original request blindly | Offline adapter regression, then separately authorized distinct test after diagnosis |
| No free candidate | 503 NO_ELIGIBLE_FREE_MODEL; empty selection dispatches nothing | Check enablement, key presence, expiry, privacy, capabilities, score and cooldown | Enable random/paid/unreviewed candidate just to make readiness green | Readiness/profile checks after reviewed changes; no paid path available |
| Stale capacity | Ignored for blocking; other model guards still apply | Refresh explicitly in the same state store, if metadata access is authorized | Interpret UNKNOWN as unlimited or assume host SQLite updates Docker | Inspect checked_at/valid_until and runtime DB; fresh matching observation present |
| Invalid/expired credential | Auth refresh records AUTH_REJECTED; adapter 401/403/404 is safe config rejection; missing key excludes model | Replace key privately, recreate env-consuming containers, refresh capacity in runtime | Print key, paste it into a report, or keep retrying rejected credentials | Authorized current-key metadata check; HTTP health alone cannot certify auth |
| LiteLLM unhealthy | Compose startup waits on its health; running Gateway may still report local alive | Inspect local proxy liveliness; restart proxy after config validation | Probe inference health endpoints indiscriminately or enable retries | `/health/liveliness` inside proxy responds; no provider call required |
| Gateway unhealthy | Client cannot connect or gets GATEWAY_UNAVAILABLE; startup may reject config/tokens/SQLite | Preserve state; check local Docker status and sanitized logs; repair configuration | Delete the state volume or expose port publicly as a workaround | `/health/live`, authenticated ready and disabled-pool smoke |
| Provider explicitly disabled | Zero eligible candidates from provider; pre-dispatch gate skips it; benchmark stops without further dispatch | Inspect provider_control CLI/audit; enable only after owner recovery approval | Delete control row/volume or remove credentials to simulate recovery | Flag persists across restart; enable alone never enables disabled models |
| Privacy downgrade request | 403 PRIVACY_DOWNGRADE_FORBIDDEN before admission | Use at least configured default privacy and an eligible model | Change client minimum just to make a PUBLIC model work | INTERNAL request either succeeds on eligible INTERNAL model or returns NO_ELIGIBLE_FREE_MODEL |
| Benchmark dataset/approval mismatch | Rejected before inference | Review dataset provenance and approval manifest offline | Automatically recompute/approve arbitrary data hashes | Dataset/hash/class/reviewer valid and campaign explicitly approved; do not infer for verification |

## Safe recovery rules

- Ordinary service restart preserves the named state volume. `docker compose down -v` destroys
  journal protection and is not a recovery step. Read-only filesystem protections do not protect
  against an administrator deleting that volume.
- `State.check_duplicate` rejects all recorded duplicate keys; SUCCESS is not replayable either.
  A new key bypasses correlation, not uncertainty. No global exactly-once guarantee exists.
- Gateway emits Retry-After 60 for retryable MG errors, while model cooldown can differ.
  The response's retryable flag does not override a recorded idempotency key.
- Capacity fresh AUTH_REJECTED blocks only while reliable/fresh and fingerprint-matched.
  Stale rejection is ignored; this is not proof the credential was fixed.
- Stop Gateway first in emergencies to stop new admissions. Stopping containers cannot retract
  an already accepted provider request; in-flight rows may require reconciliation afterward.
- Use `scripts/backup_state.py`'s SQLite backup API for live backups; copying only a `.sqlite`
  file while WAL is active can omit recent admissions. Restoration is an owner-controlled
  maintenance procedure, not a journal reset shortcut. No automated recovery CLI exists.
