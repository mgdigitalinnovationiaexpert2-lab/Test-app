# Live FREE benchmark operations

The live runner is explicit, isolated and synthetic. It never uses the runtime gateway's
enabled pool, never evaluates `openrouter/free`, never mutates Model Registry, never promotes a
model and never permits paid inference. OpenRouter requires a fresh official zero-price catalog.
Groq requires an authenticated active-model catalog plus explicit owner confirmation of the FREE
project and Global ZDR. A matching private provider key is mandatory; otherwise the report is
BLOCKED without network inference.

The fixed dataset covers `life-study`, `dev-code` and `portal-workhorse`. It checks exact
faithfulness/coverage, schema validity, scoped code answers, a synthetic tool call, Persian
script presence, long-context marker recovery, reliability and latency. Exact checks are
necessary but not sufficient: Persian fluency, code quality and reasoning require human review.
Fixtures contain no employee, Portal, company-confidential or private educational data.

Prepare one pinned disabled candidate and inspect the generated private proxy configuration:

```powershell
.venv\Scripts\python.exe -m mg_ai.discovery
.venv\Scripts\python.exe -m mg_ai.capacity
.venv\Scripts\python.exe -m mg_ai.live_benchmark prepare --candidate proposal-cohere-north-mini-code
docker compose -f evals/compose.live.yaml up -d benchmark-proxy
```

Then run once with a new stable identity and explicit route set:

```powershell
docker compose -f evals/compose.live.yaml --profile manual run --rm benchmark-runner `
  run --candidate proposal-cohere-north-mini-code --catalog /catalog/discovery.json `
  --live --run-id mg-20260909-north-01 --routes dev-code `
  --output /results/mg-20260909-north-01.json
docker compose -f evals/compose.live.yaml down
```

The output file is created exclusively and updated atomically. The SQLite journal records
dispatch before I/O. Reusing a run ID is denied, and interruption/ambiguous delivery requires
inspection rather than replay. Each row stores request ID, route, candidate sequence,
zero fallback count, provider/model, outcome/category, latency, available token counts and
timestamp; prompts and responses are excluded.

Use a distinct run ID for each pinned candidate with the same dataset and route set. Generate
provisional comparisons with `python -m mg_ai.model_intelligence --reports <files>`. It
recomputes exact scores from per-case results, rejects malformed/non-free/mismatched reports,
and emits route-specific candidate recommendations. Final selection still requires qualitative,
privacy, capacity, free-expiry and owner review. No universal Champion is selected.

External Artificial Analysis, LiveBench, LMArena or OpenRouter ranking facts may be manually
ingested as dated HTTPS references through `--external-evidence` on discovery. They remain
candidate evidence and never override MG results. No fragile runtime scraping is implemented.
