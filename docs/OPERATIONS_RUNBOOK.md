# Local operations runbook

Latest optional DEEP startup, private session setup, emergency disable and volume recovery
are in [server runbook](SERVER_RUNBOOK.md). No DEEP session or live readiness is certified.
All FREE models remain disabled after the single failed smoke; do not rerun it automatically.

Run PowerShell in `F:\Projects\MaghsoudGroup_AI_Infrastructure`. These are instructions,
not a request to execute external operations. **LOCAL** means no provider API call.
**METADATA EXTERNAL** calls provider metadata APIs, possibly subject to API rate limits.
**INFERENCE EXTERNAL / QUOTA** exports synthetic prompts and consumes model quota.
Never run a whole document as a script. Use only the section needed.

Safety-hardening source changes require one reviewed local image rebuild/recreate before the
new CLI/guards exist in a previously built container. They were not deployed by the review task.
Run `scripts/prepare.py`, `docker compose build gateway`, then `docker compose up -d --force-recreate`
only in the approved maintenance scope, checking each command succeeds. Subsequent provider
flag changes require no rebuild/restart. The State constructor creates control/audit tables
without deleting existing journal entries.

## Start, stop and health — LOCAL

For an already initialized checkout with `.env`, image and rendered proxy config:

```powershell
Set-Location 'F:\Projects\MaghsoudGroup_AI_Infrastructure'
docker compose up -d
docker compose ps
Invoke-RestMethod 'http://127.0.0.1:8090/health/live'
docker compose exec -T proxy python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:4000/health/liveliness', timeout=5).status)"
```

If Docker is stopped, start Docker Desktop and wait for its Linux engine. Startup may need
image downloads if images are absent; these are registry traffic, not model inference.
Normal stop preserves containers and state:

```powershell
docker compose stop
```

Authenticated readiness without printing tokens (LOCAL, no inference):

```powershell
docker compose exec -T gateway python -c "import os,httpx; h={'Authorization':'Bearer '+os.environ['MG_DEV_TOKEN']}; r=httpx.get('http://127.0.0.1:8080/health/ready',headers=h,timeout=5,trust_env=False); print(r.status_code,r.json())"
```

`/health/live` tests process response, not provider authentication. `ready` reads SQLite and
filters with the client's default privacy; `configured_no_eligible_provider` is expected now.
Use proxy `/health/liveliness` only here, not a provider-probing health endpoint.

## Inspect registry, providers, enabled models and Champions — LOCAL

### Provider-wide emergency control — LOCAL owner mutation, persistent

After the updated image is installed, these commands target the running Gateway's exact state
store. Use actual owner/admin attribution and a reason that contains no secrets:

```powershell
docker compose exec -T gateway python -m mg_ai.provider_control list
docker compose exec -T gateway python -m mg_ai.provider_control disable openrouter --actor owner --reason 'Emergency provider stop'
docker compose exec -T gateway python -m mg_ai.provider_control enable openrouter --actor owner --reason 'Owner reviewed recovery'
```

These are separate operations, not a block to run together. Disable persists across restart
and filters every otherwise eligible model of that provider without changing model evidence
or credentials. Enable only removes the provider stop; disabled models remain disabled.
Only local filesystem/container administrators can mutate it; client MG tokens have no API
for this action. Each change atomically appends actor/reason/time to provider_control_audit.
To inspect audit, use the journal's read-only connection command with SQL
`SELECT provider,enabled,actor,reason,updated FROM provider_control_audit ORDER BY id DESC LIMIT 20`.

The benchmark Compose shares the default named Gateway volume for control only via
MG_PROVIDER_CONTROL_STATE_PATH=/control/state.sqlite. Its own run journal remains separate.
For a nondefault project/state filename, explicitly configure the same control volume/path;
never operate a detached benchmark with an unrelated control database. In-flight requests
and the narrow interval after the final check cannot be recalled; use emergency container
stop for immediate process shutdown. Direct proxy access is outside the Gateway kill guard.

Host registry is the next-build configuration:

```powershell
.venv\Scripts\python.exe -c "from mg_ai.config import load_config; c=load_config(); print([(m.id,m.provider,m.model,m.enabled,m.approved,m.cost_class,m.health) for m in c.models]); print('providers',sorted({m.provider for m in c.models})); print('enabled',[m.id for m in c.models if m.enabled]); print('champions',{k:v.champion for k,v in c.routes.items()}); print('paid_off',all(not p.paid_allowed and p.monthly_budget_usd==0 for p in c.clients.values()))"
```

Running image configuration and credential **presence only**:

```powershell
docker compose exec -T gateway python -c "import os; from pathlib import Path; from mg_ai.config import load_config; c=load_config(Path(os.getenv('MG_CONFIG_ROOT','.'))); print([(m.id,m.enabled,m.approved,m.cost_class,bool(os.getenv(m.credential_env))) for m in c.models]); print('champions',{k:v.champion for k,v in c.routes.items()}); print('paid_off',all(not p.paid_allowed and p.monthly_budget_usd==0 for p in c.clients.values()))"
```

Inspect current ordered dev-code pool (PUBLIC profile; change client/route/privacy together
for a different authorized profile). There is no named Fallback record:

```powershell
docker compose exec -T gateway python -c "import os; from pathlib import Path; from mg_ai.config import load_config; from mg_ai.state import State; from mg_ai.routing import select; c=load_config(Path(os.getenv('MG_CONFIG_ROOT','.'))); s=State(os.environ['MG_STATE_PATH']); r=c.routes['dev-code']; print([m.id for m in select(c,c.clients['developer'],r,r.capabilities,'PUBLIC',0,512,s)]); s.db.close()"
```

This uses `State`, which can create missing tables; it is not a database recovery command.
For pure journal reads use the read-only URI below. Ordering is score-first, then Champion
preference; effective fallback is subsequent candidates, capped at three attempts total.

## Inspect capacity and journal — LOCAL, read-only

Read the running default state store; omit credential fingerprints from output:

```powershell
docker compose exec -T gateway python -c "import os,sqlite3,json,time; c=sqlite3.connect('file:'+os.environ['MG_STATE_PATH']+'?mode=ro',uri=True); rows=[json.loads(r[0]) for r in c.execute('SELECT observation FROM provider_capacity')]; print([{k:v for k,v in r.items() if k!='credential_fingerprint'} | {'fresh_now':r['checked_at']<=time.time()<r['valid_until']} for r in rows]); c.close()"
docker compose exec -T gateway python -c "import os,sqlite3,json; c=sqlite3.connect('file:'+os.environ['MG_STATE_PATH']+'?mode=ro',uri=True); print(json.dumps(c.execute('SELECT client,status,request_id,updated FROM executions ORDER BY updated DESC LIMIT 20').fetchall())); print('counts',c.execute('SELECT status,COUNT(*) FROM executions GROUP BY status').fetchall()); c.close()"
```

Certification journals are separate: `/state/cert-20260910.sqlite` (latest Gateway),
`/state/live-cert.sqlite` (earlier ambiguous smoke), and host
`.runtime/benchmark/benchmark.sqlite` (benchmark container's `/results/benchmark.sqlite`).
To inspect one, replace the connection source explicitly with that known path; keep `mode=ro`.
Host `.runtime/state.sqlite` is not the Docker volume. Empty capacity rows do not mean zero quota.
Do not delete/alter an execution row to permit replay.

## Refresh capacity — METADATA EXTERNAL; no inference

Only when metadata access is authorized. This uses the running environment and writes the
same state path the Gateway reads, avoiding the host `.env` loading trap:

```powershell
docker compose exec -T gateway python -m mg_ai.capacity
```

With no key the CLI makes no HTTP call and reports UNKNOWN; otherwise it contacts the official
current-key endpoint. It omits raw key/fingerprint from output. A host `python -m mg_ai.capacity`
does not read `.env` automatically and usually writes a different database. Refresh is manual,
not scheduled by requests; OpenRouter observations expire after 300 seconds.

## Refresh discovery — METADATA EXTERNAL; no inference

```powershell
.venv\Scripts\python.exe -m mg_ai.discovery
```

Writes disabled proposals to ignored `reports/discovery.json`, not Model Registry. Existing
model IDs may disappear or lose zero pricing. Discovery itself is not a promotion decision.

## Safe disabled-pool smoke — LOCAL

```powershell
.venv\Scripts\python.exe scripts/docker_smoke.py
```

Checks Gateway health, missing-token 401 and a local chat returning NO_ELIGIBLE_FREE_MODEL.
The script asserts an empty readiness pool before its POST. Do not run during concurrent
model activation. Do not use `--contract` unless the separate fake-provider contract stack
was intentionally started. This is not a successful external inference test.

## Small live benchmark — INFERENCE EXTERNAL / QUOTA

**Reference procedure only; do not run for documentation work.** Requires approved campaign,
unchanged public synthetic fixtures, a recent discovery snapshot (<24 h), configured key,
and an existing disabled candidate in both host and runner image. The fixed fixture bytes
must match evals/dataset-approval.json (path, SHA-256, PUBLIC_SYNTHETIC, approver and reason).
Do not update the hash automatically to make a changed dataset pass: that requires owner
review of its actual public/synthetic provenance. Example uses Nex's existing
registry ID, two dev-code fixtures, max 512 output tokens each. If preflight fails, stop.
Do not run several preparations concurrently: they share one generated proxy YAML.

```powershell
.venv\Scripts\python.exe -m mg_ai.live_benchmark prepare --candidate proposal-nex-pro
if ($LASTEXITCODE -ne 0) { throw 'Benchmark preflight failed; stop.' }
docker compose -f evals/compose.live.yaml up -d --force-recreate benchmark-proxy
if ($LASTEXITCODE -ne 0) { throw 'Benchmark proxy failed; stop.' }
$benchmarkRunId = 'owner-dev-' + [guid]::NewGuid().ToString('N')
Write-Output ('Record this run ID before dispatch: ' + $benchmarkRunId)
docker compose -f evals/compose.live.yaml --profile manual run --rm benchmark-runner run --candidate proposal-nex-pro --catalog /catalog/discovery.json --live --approved-by owner --run-id $benchmarkRunId --routes dev-code --output "/results/$benchmarkRunId.json"
docker compose -f evals/compose.live.yaml down
```

Only generate a new run ID for a genuinely new approved run; do not rerun this block to
bypass an interrupted/ambiguous run. Inspect its existing report and journal. The runner's
console can return a FAILED report without a nonzero shell exit code: read JSON `status`.
Any non-SUCCESS execution stops remaining fixtures. The runner skips Gateway client policies
and capacity filters but honors the shared provider stop before every dispatch. Provider quota
and manual campaign scope are the owner's responsibility. --approved-by is attributable manual
authorization, not proof of identity; restrict shell/configuration access.
Reports remain in `.runtime/benchmark/`; no automatic promotion occurs.

## Disable an individual model and apply configuration — LOCAL mutation

Owner/admin action. For an emergency, stop Gateway first. Example disables Nex; it never
enables anything. The main configuration currently already has every model disabled.

```powershell
docker compose stop gateway
$registryPath = Join-Path (Get-Location) 'model-registry\models.json'
$registryBackup = Join-Path (Get-Location) ('.runtime\registry-' + [guid]::NewGuid().ToString('N') + '.json')
Copy-Item -LiteralPath $registryPath -Destination $registryBackup
$registryModels = @(Get-Content -LiteralPath $registryPath -Raw | ConvertFrom-Json)
$modelToDisable = 'proposal-nex-pro'
if (-not ($registryModels | Where-Object id -eq $modelToDisable)) { throw 'Unknown model; stop.' }
foreach ($registryModel in $registryModels) {
    if ($registryModel.id -eq $modelToDisable) {
        $registryModel | Add-Member -NotePropertyName enabled -NotePropertyValue $false -Force
        $registryModel | Add-Member -NotePropertyName health -NotePropertyValue 'DISABLED' -Force
    }
}
[IO.File]::WriteAllText($registryPath, (ConvertTo-Json -InputObject $registryModels -Depth 20), [Text.UTF8Encoding]::new($false))
.venv\Scripts\python.exe scripts/prepare.py
if ($LASTEXITCODE -ne 0) { throw 'Configuration invalid; keep Gateway stopped.' }
docker compose build gateway
if ($LASTEXITCODE -ne 0) { throw 'Build failed; keep Gateway stopped.' }
docker compose up -d --force-recreate
```

For a whole provider use the persistent CLI above; do not edit every model or remove credentials.
An individual model change still requires the reviewed rebuild. Rebuild can access package/image registries but performs
no model inference. `prepare.py` writes generated schema/YAML and does not reload Gateway.
Re-run enabled/paid/ready inspection afterward. Do not expect an unrelated healthy provider
to be usable without its own eligibility evidence.

## Emergency shutdown — LOCAL

```powershell
docker compose stop gateway
docker compose -f evals/compose.live.yaml stop
docker compose stop proxy
```

This stops new Gateway admissions plus the known benchmark services. A one-off runner created
with `compose run` may need explicit stopping: list its ID with the known project label,
inspect the name, then stop that specific container. Do not stop unrelated projects.

```powershell
docker ps --filter 'label=com.docker.compose.project=mg-ai-benchmark' --format '{{.ID}} {{.Names}}'
```

For any remaining listed benchmark runner: `docker stop <verified-container-id>` (replace the
placeholder; do not paste literally). Keep volumes. Never add `-v` to `down` for recovery.
Already dispatched provider work cannot be recalled; inspect DISPATCHED/AMBIGUOUS records
before restarting or resubmitting. Verify Gateway port no longer answers and known containers
are stopped with `docker compose ps -a` and the label-filtered listing.

## Validate this handover — LOCAL

```powershell
.venv\Scripts\python.exe scripts/owner_inventory.py --check-docs
.venv\Scripts\python.exe -m pytest tests/test_owner_inventory.py -q
git diff --check
git status --short
```

The tool checks annotated exact symbols and local document links. It does not claim to prove
every English sentence or execute runbook commands. No full test suite or live probe needed.
