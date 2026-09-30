# Deep Chat: owner-only synthetic certification worker

This component uses the owner's dedicated Edge profile and durable two-message
certification budget. Never reset its journal or replay an ambiguous send.
Deep Codex and all other certified routes are outside this component.

## Ambiguous first-turn recovery (issue #1)

`recover-first-turn` recovers an existing ambiguous task with `turns=1` and no
canonical URL. It cannot send a prompt. `certify` uses the same recovery path
before resuming the remaining turn. Use the existing task ID:

```powershell
.\run-owner.ps1 -Command recover-first-turn -ApproveTwoSyntheticMessages -Task synthetic-certification-20260921-03
.\run-owner.ps1 -Command certify -ApproveTwoSyntheticMessages -Task synthetic-certification-20260921-03
```

Recovery copies only `profile/Default/History` and its WAL/SHM sidecars into a
temporary directory inside the private runtime. Source changes during copying,
hot rollback journals, unreadable/corrupt snapshots and excessive candidates stop
recovery. SQLite opens only the disposable snapshot. Visit records correlate
nonce-bearing titles with canonical conversation visits within two minutes;
history/title/time alone never establishes identity.

Every candidate is checked in the same authenticated, non-temporary profile.
Exactly one conversation must contain precisely the original nonce prompt and
`NONCE_STORED` reply in user/assistant order. Stable response and reload evidence
are required before the existing journal completion method binds the URL, with
`turns=1` preserved. Multiple matches stop without binding. Title verification
must then pass before the second reservation. The global two-message limit,
reserve-before-Send, URL continuity, and no replay/fallback remain enforced.

The observed UI uses `[data-user-message-bubble="true"]` and
`[data-markdown-text-style="assistant-message"]` inside a unique visible main
region; the previous author-role DOM remains supported. Completion requires an
empty editable composer, no visible stop control, an additional visible assistant
message stable across five polling intervals, and the exact expected synthetic
answer. Certification verifies the answer after reload. It does not depend on
`Copy response`. Raw diagnostic traceback files and environment-controlled
diagnostic execution branches have been removed from the worker.

## Architecture and security boundary

Future Portal approval → Deep Chat worker → dedicated persistent headed Microsoft Edge
→ normal chatgpt.com Chat. Today the entry point is an owner-operated CLI with
fixed PUBLIC synthetic prompts, not a Portal integration or HTTP service.
Python standard library + Playwright are the only runtime dependencies. No Codex
inference/authentication/allowance, OmniRoute, OpenAI inference/conversation API,
Deep Codex state, account rotation, fingerprint spoofing or bypass is used.

Windows only. `owner-config.json` pins local account `MGDeepChatOwner`. Every
command checks the process Windows identity against that local account SID and
rejects Administrator, administrator-group membership, disabled accounts, wrong
identities and unverifiable checks. The former acknowledgement flag is removed.
There is no CLI/environment identity or profile override. The root is derived
from the Windows ProfileList registry entry for the verified SID, not LOCALAPPDATA.

All owner commands must start through **`run-owner.ps1`**, from the owner's existing
PowerShell session. The launcher invokes the unchanged `check-owner.ps1` directly
in its PowerShell process before Python starts. Only the exact, case-sensitive
`OWNER_BOUNDARY_VALID` result permits Python launch. Failures never become success.
This avoids the verified protected-DACL observation failure when the ACL validator
was run under a PowerShell child of venv Python; no ACLs or ACL policy are changed.

After full validation, the launcher creates a short-lived, one-use handoff file
inside the private `runtime` directory. It passes only state, validated root,
handoff filename and creation time through the child process environment. There
are no credentials, cookies or browser-storage values in the handoff. The worker
removes the environment value before launching any subprocess and consumes the
file before browser access; the launcher cleans any remaining handoff on exit.
The worker runs under the existing `.venv\Scripts\python.exe` in isolated mode.

Direct `python worker.py owner-login/status/certify` returns
`OWNER_LAUNCHER_REQUIRED` without inspecting browser state or launching Edge.
Setting the environment value alone is insufficient: a matching, unexpired private
handoff must exist. Python independently checks the actual identity and group SIDs
using the OS `whoami.exe` (including deny-only Administrator membership), derives
the expected root from that SID's registry profile, and rejects alternate roots,
repository paths, junctions and legacy-journal replacement. Python no longer spawns
PowerShell for ACL validation. Full protected-DACL and recursive ACL validation remain
the launcher's responsibility immediately before Python launch.

`check-owner.ps1` validates root, profile, state, runtime and all existing descendants
using ACL metadata only. It rejects reparse points, an inheriting root ACL, unsafe
owners, unapproved ACE identities, unapproved deny ACEs and missing
effective owner FullControl. Directories must propagate owner FullControl to files
and subdirectories. Broad Users, Everyone Allow, Authenticated Users and
individual programmer/MG accounts fail. Missing paths or failed checks stop before
browser startup. It never reads cookie/storage file contents. Source code/config
must be a trusted owner-controlled copy; this is not a defense against tampered code.

Root, state, runtime, SQLite, markers, locks and launcher handoffs retain the strict
owner/SYSTEM-only policy. Only the canonical `profile` directory and its descendants
permit the exact owner-confirmed Edge capability SID
`S-1-15-3-1024-3239966617-1410756637-3494353204-65451782-2225605771-3526040376-1730753648-3419555762`.
Its ACE must be Allow with rights no broader than Modify + Synchronize, or the exact
observed signed rights value `-536805376` with InheritOnly and child inheritance flags.
Both explicit and inherited versions are accepted. That signed mask is rejected if
effective on the current object (not InheritOnly). It can never be the ACL owner or
substitute for owner FullControl. Profile alone also permits Everyone (`S-1-1-0`)
**Deny Traverse/ExecuteFile only**, exact rights value 32. Everyone Allow, Deny Read,
Deny Modify, Deny FullControl or any additional rights remain rejected, as does
Everyone ownership. Neither exception applies outside the canonical profile subtree.
The final post-login inventory also permits `BUILTIN\Administrators` (`S-1-5-32-544`)
inside profile only: Allow, exactly FullControl, explicit or inherited, with either
no inheritance flags or ContainerInherit + ObjectInherit, and no propagation flags.
Administrators Deny, other rights, other inheritance/propagation forms and Administrators
ownership fail closed. This ACE cannot substitute for the dedicated owner's effective
FullControl. Administrators remains rejected everywhere outside profile, including
root, state, runtime, SQLite, markers, locks and launcher handoffs. Other privileged
groups receive no exception. Runtime identity still cannot be an Administrator.
Unknown capability SIDs, AppContainer package/group SIDs, ordinary users, other broad groups,
other Deny ACEs and capability permission/ownership changes remain rejected. Path-prefix
lookalikes and traversal outside profile do not receive the exception. Reparse-point
rejection and protected-root-DACL validation are unchanged.

This is an explicit allowlist based on the owner-observed Edge ACL, not blanket trust
of `S-1-15-3-*` and not a claim of Windows capability registration verification.
Additional capabilities require review and explicit approval; unknown entries fail
closed. The validator never removes, rewrites or adds filesystem ACEs.

**This does not protect against a malicious Windows local administrator**, SYSTEM,
host malware or someone who can modify the worker. Administrators can take ownership
or inspect processes. Use an owner-controlled machine/VM if programmers administer
the host. ACL checks are point-in-time checks, not protection against privileged races.
The launcher/handoff prevents accidental or wrong-account execution and protects
against ordinary users. It trusts the dedicated owner and reviewed code executing
as that owner; it is not an attestation against malicious code running under the
same owner identity, which can create files in the owner's private directory.

No inbound HTTP/LAN/public listener, VNC service, SSH tunnel or TCP CDP/debug port
is configured. Playwright uses local browser control. There are no storage exports,
screenshots, HAR, trace files or application log files. Browser exceptions are not
printed; stdout contains fixed prompts, safe state codes and synthetic results.
Python stderr is suppressed during browser operation and DEBUG/PWDEBUG are removed.
Native crash diagnostics/host logging have not been certified; do not enable external
debugging or capture around the owner browser. Do not share profile data or screenshots.

## Owner setup plan — commands for later, NOT executed

Recommended account: **MGDeepChatOwner**, standard local user, never Administrator.
The owner runs the following once in elevated 64-bit Windows PowerShell. The password
is entered privately at that future time; do not provide it to developers or this agent.
The script refuses an existing account instead of silently repurposing one.

```powershell
$ErrorActionPreference = 'Stop'
if (Get-LocalUser -Name 'MGDeepChatOwner' -ErrorAction SilentlyContinue) {
    throw 'Account already exists; owner review required'
}
$deepChatPassword = Read-Host 'Choose the private MGDeepChatOwner password' -AsSecureString
New-LocalUser -Name 'MGDeepChatOwner' -Password $deepChatPassword -Description 'Dedicated Deep Chat owner session' | Out-Null
Remove-Variable deepChatPassword
$deepChatUsers = Get-LocalGroup -SID 'S-1-5-32-545'
Add-LocalGroupMember -Group $deepChatUsers -Member 'MGDeepChatOwner'
```

Do not add the account to Administrators or remote-access groups. Sign out, then
sign in locally through Windows as `.\MGDeepChatOwner` to initialize its profile.
No tunnel is used. Domain/group policy may require owner-admin review of local sign-in
rights; this component does not change host policy or open remote desktop access.

Under that standard owner account, copy only reviewed component source/config into
`$env:USERPROFILE\Documents\DeepChatWorker` (not the shared repository), then run:

```powershell
Set-Location "$env:USERPROFILE\Documents\DeepChatWorker"
.\setup-owner-runtime.ps1
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Use the installed Microsoft Edge through Playwright `channel="msedge"`; no Playwright
browser download is required. The owner verified Edge 153.0.4234.32 at
`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` with Playwright 1.58.0.
The worker keeps its dedicated `profile` directory and never selects the normal
owner Edge profile. Edge launch failure returns `EDGE_LAUNCH_FAILED`, without
falling back to bundled Chromium or printing launch diagnostics.

`setup-owner-runtime.ps1` refuses the wrong identity and any existing runtime root.
It creates a protected root ACL with owner and SYSTEM FullControl only, then profile,
state and runtime subdirectories inheriting that private ACL. It invokes the same
validator afterward. No account/password is created by this script. If PowerShell
policy blocks reviewed scripts, stop for the owner's policy review; no bypass is supplied.
Protect the copied code and virtual environment from other non-admin users as well.

Expected locations for a fresh, default Windows profile:

```text
C:\Users\MGDeepChatOwner\AppData\Local\Maghsoud\DeepChatPrototype\profile\
C:\Users\MGDeepChatOwner\AppData\Local\Maghsoud\DeepChatPrototype\state\task-conversations.sqlite
C:\Users\MGDeepChatOwner\AppData\Local\Maghsoud\DeepChatPrototype\runtime\owner-ready
C:\Users\MGDeepChatOwner\AppData\Local\Maghsoud\DeepChatPrototype\runtime\worker.lock
```

Windows can choose a suffixed/different profile directory. The authoritative prefix
is `HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\<owner SID>`
`ProfileImagePath`, followed by `AppData\Local\Maghsoud\DeepChatPrototype`.
The validator reports only this non-secret root and a state code. Runtime under the
repository, junctions and an old root-level SQLite journal are rejected. Never delete
a journal to reset certification. A legacy journal needs owner-reviewed relocation
with the worker stopped, preserving the database and any SQLite sidecars; no automatic
move/reset is performed. Schema migration then preserves counts, mappings and ambiguity.

## One-time owner ChatGPT login — later only

From the private owner component directory:

```powershell
.\run-owner.ps1 -Command owner-login
```

After identity/ACL validation, a dedicated browser opens **https://chatgpt.com/**.
Manually sign in, verify Plus in account settings, return to the chat page, press
Enter in the terminal and type `PLUS`. No password is entered by automation. The
worker confirms visible authentication and closes the browser. `owner-ready` records
only Plus attestation, never authentication proof or credentials. Stop if challenged;
there is no CAPTCHA, anti-bot or rate-limit bypass.

## Session status and controls

```powershell
.\run-owner.ps1 -Command status
```

**Status now opens the dedicated browser after security checks. Do not run it during
this offline-only phase.** It navigates to ChatGPT and classifies visible UI and URL
only; it never trusts the marker as proof of authentication and never sends a message.

- `AUTHENTICATED`: normal ChatGPT origin, visible profile control and composer,
  no observed login/challenge indicators.
- `NEEDS_OWNER_LOGIN`: visible Log in/Sign up control or recognized authentication URL.
- `UI_OR_CHALLENGE_BLOCKED`: recognized visible human-verification/rate-limit notice.
- `UNKNOWN_SAFE_STOP`: incomplete/unrecognized UI, unexpected origin or general errors.

Wrong identity/unsafe ACLs return their specific security failure before this browser
classification. Unknown UI is never treated as authenticated. UI selectors currently
assume English and are not live-certified. Some challenges will classify UNKNOWN rather
than BLOCKED; neither permits a send. Missing Plus attestation blocks certification.
Stop the foreground worker with Ctrl+C; graceful cleanup closes the dedicated Edge. A hard crash
may leave a lock requiring owner investigation, never automatic stale-lock deletion.

## New chat, automatic title and continuity

For a new task an already verified fresh root requires no click. Otherwise the
worker selects `#app-shell-sidebar:visible`, requires one
visible sidebar, then enumerates `button[type="button"].sidebar-item:visible`
within it. Python qualifies visible candidates whose `inner_text().strip()` is
exactly `New chat`, requires exactly one, and clicks once (5-second click timeout).
Hidden descendant text does not qualify a control; accessible names and labels
are not used for selection. Zero
or multiple qualifying visible buttons fail closed before clicking. Global New chat
links/buttons are never used. After the click, the worker polls the complete fresh
guard every 250 ms for at most 10 seconds; authentication alone does not establish
fresh-chat readiness. Login loss, challenges and active Temporary Chat stop
immediately. No click replay or dispatch reservation occurs during this work.
It requires a root chat URL with no query, a visible main region with no message
elements, and an empty normal `Ask ChatGPT` textbox. Normal mode requires the visible
`Open profile menu` button and normal composer; absence of Temporary Chat indicators
alone is insufficient. Any visible `Turn off temporary chat` button or `Temporary chat`
heading rejects the operation, including duplicate indicators. The profile-menu
`Temporary chat` entry alone is not an active-mode indicator. The normal-mode check
also applies to continuations; the worker never toggles temporary mode automatically.
After sending, only a normal `https://chatgpt.com/c/<id>` URL is accepted.

The latest owner-supplied live DOM identifies one visible `button` with
`type="button"`, class token `sidebar-item`, and text `New chat` inside the visible
sidebar. It has no `aria-label`, so the previous `button[aria-label="New chat"]:visible`
selector matched nothing and caused `NEW_CHAT_NOT_CONFIRMED` before click. The
structural enumeration with Python visible-text qualification fixes the later
text pseudo-selector failure and avoids global accessible-name ambiguity.
`visible()` still requires exactly one match; `any_visible()` is used for negative
signals so duplicates cannot hide login or Temporary Chat. Offline HTML fixtures
model the absent label, duplicate structural candidates and unrelated controls;
mocked transition tests preserve bounded polling and no replay. That earlier
locator fix was offline-only; issue #1 recovery is documented above.

All callers are covered by that trace: `new_chat()` verifies freshness before
and after any required click; `send_checked()` calls `fresh_guard()` before filling a first
prompt and calls `new_chat_guard()` again after filling, before reserving dispatch.
The latter deliberately supplies the composer-empty flag because it has just filled
the authorized prompt. Continuations use `same_chat()` and authoritative `page.url`.
The certification budget remains two messages globally.

Offline validation for this fix: Python compilation passed; 66 worker tests,
16 auth-wait tests, 123 security checks and 5 launcher checks passed. The Python
suites required an approved run outside the sandbox after Windows denied access
to repository-local synthetic temporary directories.

After the first response is saved, the worker automatically opens that conversation's
sidebar options → Rename, fills its scoped title editor and presses Enter. It reloads
and verifies the exact visible sidebar title `MG Portal - Task <task_id>` on the
stored conversation link. No manual renaming, extra ChatGPT message or API call occurs.
If rename/verification fails, the mapping and first answer remain durable and the
second send is blocked. A later run can retry title UI work without resending prompt 1.

Table `task`: `id` (portal_task_id primary key), `nonce`, `conversation_url`, `title`,
`turns`, `state`, `latest_answer`, `created_at`, `updated_at`, `certification_status`.
Additive auth-wait fields are `auth_state`, `waiting_reason`, `request_state`,
`request_kind`, `last_error`; their contract is described below.
Times are UTC ISO-8601. Legacy rows retain NULL created_at because it is unknown.
Legacy `url`/`answer` columns migrate to their new names transactionally. No dispatch
count or AMBIGUOUS state is reset. READY is execution readiness, not authentication.
Certification status progresses from NOT_CERTIFIED to TITLE_VERIFIED and finally
CERTIFIED_OWNER_PLUS_ATTESTED after history/reopen/nonce checks.

Every send reserves a slot durably before clicking Send. Two reservations total are
allowed across this journal. An uncertain send stays AMBIGUOUS and cannot replay.
The first URL is persisted with the first captured response before title work; an
interruption before capture can leave an unlinked conversation and a blocked task.
Later requests navigate the same stored URL, verify the URL before sending, and reject
URL replacement. Successful continuation is tested across a closed/reopened browser.
Deleting state or running another installation is outside this local counter's guarantee.

## Later certification — NOT executed

```powershell
.\run-owner.ps1 -Command certify -ApproveTwoSyntheticMessages -Task synthetic-certification-001
```

Exactly two possible PUBLIC synthetic messages: store a nonce, then retrieve it from
the same conversation. Title changes send no messages. The worker checks exact nonce,
sidebar title/URL and response persistence after reload. DOM assistant text is returned
as JSON with task ID and normal conversation URL; session data is never exported.
Completion requires stable exact expected text, an additional visible assistant
message, no visible Stop control and an empty editable normal composer. The final
certification answer must persist after reload. Missing evidence times out as
ambiguous. Plus is owner-attested.
There is no generic prompt endpoint, Portal connection, Docker/Compose deployment,
production approval or independent proof of live browser compatibility.

## Offline checks

From the repository root:

```powershell
python -m unittest discover -s deep-chat-worker -p 'test_*.py' -v
powershell.exe -NoProfile -NonInteractive -File deep-chat-worker/test-security.ps1
powershell.exe -NoProfile -NonInteractive -File deep-chat-worker/test-launcher.ps1
```

Python tests use synthetic SQLite files and mocked browser UI only. PowerShell tests
use synthetic identity facts and in-memory ACL objects; they create no account and
change no filesystem ACL. No test installs/imports Playwright or launches a browser.
Pre-login hardening validation: 21 Python tests and 11 PowerShell identity/ACL checks
passed; all PowerShell sources parsed successfully. The Windows sandbox denied access
to synthetic temporary directories, so Python checks passed on the approved outside-
sandbox rerun. The actual current shared identity was rejected by the security probe.
Real Windows ACL traversal and current authenticated ChatGPT selectors still require
owner-side validation after setup. Strict selectors may stop even a legitimate session;
they must not be relaxed to guess normal mode or bypass a challenge.

Launcher change validation: 29 Python tests, 5 PowerShell launcher checks and all
11 existing PowerShell identity/ACL checks passed offline. Launcher tests mock the
checker and Python invocation and use synthetic handoff files only. Existing owner
state, directory ACLs and `check-owner.ps1` were not modified. No browser was opened,
no owner login performed and no ChatGPT message sent during this change.

## Fixed routing policy

| Explicit selection | Backend |
| --- | --- |
| Normal | FREE pool |
| dev-light | Qwen/Groq |
| dev-code | Codex |
| Deep Codex | OmniRoute/Codex |
| Deep Chat | Normal ChatGPT web only |

This table documents the owner product rule; this component does not configure or
modify any other route. **Deep Chat automatic Codex fallback = DISABLED.**
Deep Chat authentication failure → NEEDS_OWNER_LOGIN → notify owner → wait.
No automatic Deep Codex, OmniRoute, Codex inference, OpenAI API or other-provider
recovery exists. Deep Codex requires an explicit Deep Codex selection/request.

## Durable authentication wait contract

An approved synthetic certification request is journaled before login checks,
including when the Plus marker is absent. The task ID, nonce, pending request kind,
turn count/state and existing conversation mapping survive authentication expiry.
The prototype stores the fixed `CERTIFY_TWO_PUBLIC_MESSAGES` operation, not arbitrary
Portal payloads. A future general-purpose Portal adapter is not implemented.

Visible Log in/Sign up, recognized authentication URLs and visible session-expired /
authentication-invalid notices produce exactly `state: NEEDS_OWNER_LOGIN`. Before
dispatch, the worker checks authentication, persists `auth_state` and `waiting_reason`
as NEEDS_OWNER_LOGIN and `request_state` as WAITING_OWNER_LOGIN, then stops without
clicking Send or invoking another provider. Ambiguous execution state is never reset.
Observed challenge/rate-limit UI remains UI_OR_CHALLENGE_BLOCKED, and unrelated safe
failures are durably FAILED with a safe error code. Unknown UI is not guessed to be
an expired session. No browser storage, credentials or raw diagnostics are inspected
or returned. Live UI selectors remain subject to owner-side verification.

Machine-readable durable status, without opening a browser:

```powershell
.\run-owner.ps1 -Command task-status -Task synthetic-certification-001
```

The launcher still performs identity/ACL validation. JSON includes `state`,
`portal_task_id`, `conversation_url`, `execution_state`, `turns`, `request_kind`,
`request_state`, `auth_state`, `waiting_reason`, `updated_at`, `resumable`,
`backend: normal_chatgpt_web`, and `automatic_fallback: false`. An auth wait includes:

```json
{"notification":{"code":"DEEP_CHAT_OWNER_LOGIN_REQUIRED","message":"Deep Chat session expired. Owner login required."}}
```

This is a future Portal notification contract, not a message sent to anyone.
Rows/fields persist in the existing private SQLite journal. Migration is transactional
and preserves legacy mappings, timestamps, nonces, turns, answers and ambiguity.

After `run-owner.ps1 -Command owner-login` completes visible authentication, owner
Plus attestation and browser cleanup successfully, a scoped SQL update clears only
authentication waiting. Eligible WAITING_OWNER_LOGIN requests become RESUMABLE;
auth-related notification/error fields clear. It never changes task identity,
conversation URL, title, answer, execution state, certification history or counters.
No pending request is dispatched automatically: the owner explicitly reissues the
same certification command/task to resume. The global two-reservation cap remains.

If auth loss is detected after a Send reservation/click, the request also retains
execution_state AMBIGUOUS and request_state BLOCKED_AMBIGUOUS, with `resumable: false`.
Authentication recovery clears the auth wait but leaves it AMBIGUOUS and blocked.
The worker cannot retroactively prevent an already-dispatched message, and never
replays one with uncertain outcome. Browser-cleanup failures cannot mask a persisted
auth-wait state. Completing login does not clear independent UI failures or FAILED states.

The live `status` command also persists detected expiry for existing unfinished
requests. `task-status` only reads the durable contract and does not open Edge.
This phase passed 56 Python tests, 71 in-memory PowerShell identity/ACL checks and
5 mocked launcher checks (132 total); PowerShell source parsing also passed.
No existing owner database, runtime ACL, browser session or certified route was
accessed or modified by these offline tests.

## Browser UI selector audit

Current UI access is centralized in small WebUI helpers. Profile, composer and Send
use exact semantic roles/names: button `Open profile menu`, textbox `Ask ChatGPT`,
button `Send`. Sending additionally requires `contenteditable=true`, a unique visible,
enabled Send button with `type=submit`, and all existing pre-dispatch guards. Durable
reservation still precedes the single click. No stale profile/composer/send/stop
test-ID selectors or volatile CSS classes are used.

Modern message-content attributes and legacy message-author attributes are centralized
inside semantic `main`; no reliable role distinguishes user and assistant text. Conversation identity
and exact continuity come directly from `page.url`, including after reload; sidebar
hrefs, row order, indices and title matching never establish identity.

Title operations require exactly one visible, named `div[role="button"]` in the
unique visible `#app-shell-sidebar`, with `aria-current="page"`, `aria-current="true"`
or `aria-selected="true"`.
If collapsed, the sidebar opens once through its unique visible
`button[data-app-shell-sidebar-trigger="true"][aria-controls="app-shell-sidebar"]`;
the worker waits at most five seconds for `aria-expanded="true"`. Two global
`Show sidebar` controls are not treated as a unique action.
Its descendant button named exactly `Chat actions` must be unique. Rename rechecks
identity and row uniqueness after hover before clicking only that row's actions.
Missing/ambiguous current rows or actions stop with `TITLE_UI_UNAVAILABLE`, with no
menu click. No generated CSS class or first/last-row fallback is used. Rename uses
the semantic Rename menuitem and a row-scoped inline textbox or explicitly named
Rename chat/conversation dialog. Verification requires the current row's exact
`aria-label` to equal `MG Portal - Task <task_id>`, with authenticated normal mode
and the same exact URL. Both immediate verification and verification after reload
remain mandatory before title readiness is recorded. No action/message is replayed.

The issue #1 probe confirmed a named current DIV row with a descendant `Chat actions`
button inside the visible sidebar, outside the semantic navigation region. Missing
or ambiguous identity, action or editor evidence stops title operations before Send.
History URLs never substitute for the live canonical URL and exact nonce evidence.

Offline validation: worker suite 59 tests, auth-wait suite 16 tests, security suite
123 checks, launcher suite 5 checks, and Python compilation passed. Python suites
needed an approved rerun outside the sandbox due to synthetic-directory access
errors. Only repository source/tests/docs were edited; tests used synthetic fixtures.
No browser, ChatGPT message, live certification, owner runtime state or runtime sync
was involved.
