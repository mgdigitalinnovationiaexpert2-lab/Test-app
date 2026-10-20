# Developer acceptance and handoff

Portal and Website use the same `TaskPolicy` YAML schema and central Scope Guard.
Required fields: task, repository, goal, acceptance_criteria, allowed_paths, forbidden_paths,
allow_schema_change, allow_infrastructure_change, allow_commit, allow_push, risk_level.
Optional fields: relevant_tests, notes. The example is `scope-guard/task.example.yaml`.

For a dirty repository, record `mg_ai.scope_guard.baseline(Path(repository))` as JSON before
the bounded edit. Supply that file with `--baseline` when checking. Inspect the snapshot and
final diff together: baseline exclusion is not permission for pre-existing work or a security
sandbox. Without a baseline the guard checks the entire current Git change set, including
staged and untracked files. Never widen the task to hide unrelated changes.

The integration run created these genuinely useful documentation exercises:

| Task | Repository | Change | Deterministic result | Live Cline journey |
|---|---|---|---|---|
| MG-DEV-PORTAL-001 | F:/Projects/MaghsoudGroup_Portal | Bounded documentation handoff procedure | Positive PASS, simulated forbidden schema path denied | BLOCKED |
| MG-DEV-WEBSITE-001 | F:/Projects/MaghsoudGroup_Website/MaghsoudGroup_Website | Correct obsolete CMS startup claim and add Windows instructions | Positive PASS, simulated forbidden schema path denied | BLOCKED |

Task YAML, programmer instructions and handoff are under each repository's
`docs/developer-acceptance/`. Implementation used local deterministic editing. It was not
performed by a free model. No Cline or developer inference success is claimed.

Recorded pre-task baselines, exact diffs and positive/negative evidence are under ignored
`.runtime/acceptance/`. Deliberate negative checks use simulated path input; no forbidden
file was created. Documentation is LOW risk, services MEDIUM, schema/auth/env/infra HIGH.
Commit and push operations are denied by both exercise policies.

Portal's required legacy `npm run task-scope:check -- --scope docs/developer-acceptance/task.json`
was also run. It rejects the entire dirty tree because it has no baseline support; this is
expected and is recorded as a separate whole-tree failure. It was not bypassed or widened.
Only the central baseline-scoped exercise check passes. All other changes remain reviewable.

Owner review is next. Automatic Codex review, commit, push and merge are OFF. An optional
independent Codex review is initiated by the owner, never by a programmer automation.
