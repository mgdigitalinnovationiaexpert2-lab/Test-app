# Repository constitution

## Owner-first decisions
Prioritize Maghsoud cost, control, security, recoverability, maintainability, quality,
and vendor independence. Free-first means qualified free models; paid inference is off.

## Fresh sessions
Read AGENTS.md → git status → docs/CURRENT_STATE.md → relevant vertical slice.
No mandatory full-repository audit unless the baseline is uncertain or requested.

## Token / AI efficiency
Use the smallest relevant vertical slice. Use local deterministic tools before AI.
Never ingest whole repositories unnecessarily. Generated/build/binary/log files are
not AI context. Run targeted tests during development; full validation at milestones.

## Git safety
No auto commit, push, force push, destructive cleanup, or production deployment
without owner approval. Never modify consuming repositories as part of this task.

## Security
Never commit secrets. Fail closed. Provider credentials stay server-side. Clients
receive MG tokens only. Developer AI has no production data access by default.
Do not enable unknown or paid candidates implicitly; never retry ambiguous dispatch.

## Human maintainability
Code explains WHAT. Comments explain WHY. Comments belong only to non-obvious
business logic, security, concurrency, compatibility, provider workarounds,
migration rationale, or complex algorithms. This file is not a changelog.
