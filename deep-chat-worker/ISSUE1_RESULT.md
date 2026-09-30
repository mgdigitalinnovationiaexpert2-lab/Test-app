# Issue #1 — Windows Deep Chat Worker

Issue: https://github.com/mgdigitalmarketingai-spec/MaghsoudGroup_AI_Infrastructure/issues/1

Updated working copy: `C:\Users\MGDeepChatOwner\Documents\DeepChatWorker`.
The source-only diff against the original owner working copy is `issue1-final.diff`.

## Verified live result

```json
{
  "state": "CERTIFIED_WITH_OWNER_PLUS_ATTESTATION",
  "portal_task_id": "synthetic-certification-20260921-03",
  "conversation_url": "https://chatgpt.com/c/6ab0e872-56c8-83e8-a3c5-153747b1a0d4",
  "response_text": "MG-SYNTHETIC-d0cc15f7dda38db7",
  "messages": 2,
  "runtime": "normal_chatgpt_web"
}
```

The checked owner launcher returned `AUTHENTICATED`. Recovery matched the exact
original user prompt and `NONCE_STORED` reply in the canonical conversation,
checked persistence after reload, and completed the existing reservation without
changing `turns=1`. The remaining prompt was dispatched once. Its exact nonce
answer and URL survived reload. The final journal state is `COMPLETED`, execution
state `READY`, `turns=2`, authenticated, and `automatic_fallback=false`.

Earlier certification attempts stopped before Send on title UI prerequisites;
their durable status remained `READY`, `turns=1`. No first prompt was replayed,
no ambiguous send was replayed, and no journal or budget was reset. Plus is
owner-attested, as stated by the certification result.

## Root causes and implementation

- The current message DOM has no `data-message-author-role`. The worker now
  recognizes the observed user bubble and assistant markdown attributes inside
  the unique visible main region, with legacy message DOM support.
- Response completion no longer requires `Copy response`. It requires the exact
  expected synthetic answer, stable text, an additional visible assistant reply,
  an empty editable composer and absence of visible stop controls. Certification
  also verifies persistence after reload.
- History recovery uses a private DB/WAL/SHM snapshot and original visit records.
  Nonce-title/time correlation only proposes URLs. Exact ordered conversation
  evidence, reload persistence and one unique match authorize binding.
- Current chat rows are outside the navigation region. The visible sidebar is
  the correct scope, and its collapsed state hides otherwise existing rows.
  A unique structural sidebar trigger can expand it once, with a bounded wait.
  Rename retains current-row uniqueness, URL checks, scoped actions/editor,
  actual title verification and reload verification. A readiness wait handles
  modal dismissal after saving.
- Diagnostic environment branches and raw traceback writers were removed.
  `recover-first-turn` provides an explicit recovery-only path with no Send.
  The isolated launcher, owner identity/ACL checks and global budget remain.

Changed implementation files: `worker.py`, `run-owner.ps1`, `test_worker.py`,
`test_auth_wait.py`, new `test_recovery.py`, and `README.md`.

## Final validation in the owner working copy

- Python compilation: PASS.
- Worker tests: 76 PASS.
- Authentication tests: 16 PASS.
- Recovery tests: 19 PASS.
- Total Python tests: 111 PASS.
- Offline identity/ACL checks: 123 PASS.
- Offline launcher checks: 5 PASS.

Live execution used the already logged-in MGDeepChatOwner session and checked
launcher. No account or filesystem ACL was changed, no alternate profile was
used, and no commit, push or production deployment was performed.

The five temporary scheduled tasks were removed after completion. Twenty-three
old source diagnostic helpers/backups and temporary probe artifacts were archived
under `issue1-archive-20260921` in the owner working copy. An exact original source
backup is in its `source-before` subdirectory. No runtime/profile/journal files
were moved or deleted. Certification result JSON and test logs remain in the
working-copy root.

## Outstanding acceptance criterion: Portal integration

The Portal → Deep Chat → Plus → Portal smoke test has **not** run. The inspected
local Portal has MG Deep HTTP and ChatGPT-plugin adapters; no DeepChatWorker
transport was found. This worker remains a synthetic owner CLI, with no generic
prompt endpoint. No authenticated Portal test entry point was supplied. An
existing Deep/Codex route was not repurposed and the certification budget was
not raised to manufacture a smoke-test result.

Finishing that criterion requires the intended Portal instance/authenticated test
entry point and a Deep Chat transport with its own explicit request/dispatch
contract. Portal source, database and containers were not modified. No Portal
backup or migration was performed because no Portal mutation occurred.
