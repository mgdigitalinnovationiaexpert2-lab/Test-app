"""Windows owner-only, synthetic-only normal ChatGPT browser prototype."""

import argparse
import contextlib
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

class HistoryUnavailable(Exception):
    pass


def _history_signature(paths):
    return [(p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None for p in paths]


@contextlib.contextmanager
def history_snapshot(root):
    root = Path(root)
    source = root / "profile" / "Default" / "History"
    files = [source, Path(str(source) + "-wal"), Path(str(source) + "-shm")]
    if not source.is_file():
        raise HistoryUnavailable("RECOVERY_HISTORY_NOT_FOUND")
    # A hot rollback journal requires recovery of the original DB. Never do that.
    rollback = Path(str(source) + "-journal")
    if rollback.exists() and rollback.stat().st_size:
        raise HistoryUnavailable("RECOVERY_HISTORY_BUSY")
    try:
        # Copies inherit the private runtime ACL, never a shared system temp ACL.
        with tempfile.TemporaryDirectory(prefix="history-read-", dir=root / "runtime") as folder:
            destination = Path(folder) / "History"
            before = _history_signature(files)
            for source_file, signature in zip(files, before):
                if signature is not None:
                    shutil.copyfile(source_file, Path(folder) / source_file.name)
            if before != _history_signature(files):
                raise HistoryUnavailable("RECOVERY_HISTORY_BUSY")
            # SQLite may recover/checkpoint WAL only in the private disposable copy.
            with contextlib.closing(sqlite3.connect(destination, timeout=1)) as db:
                db.execute("PRAGMA query_only=ON")
                if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise HistoryUnavailable("RECOVERY_HISTORY_INVALID")
                yield db
    except (OSError, sqlite3.Error):
        raise HistoryUnavailable("RECOVERY_HISTORY_READ_FAILED") from None


def history_candidates(root, nonce):
    if not re.fullmatch(r"MG-SYNTHETIC-[0-9a-f]{16}", nonce):
        raise HistoryUnavailable("RECOVERY_NONCE_INVALID")
    with history_snapshot(root) as db:
        # Visit records survive later revisits, unlike urls.last_visit_time.
        anchors = db.execute(
            "SELECT u.url,v.visit_time FROM urls u JOIN visits v ON v.url=u.id "
            "WHERE instr(u.title,?)>0 ORDER BY v.visit_time DESC LIMIT 33", (nonce,)).fetchall()
        if len(anchors) > 32:
            raise HistoryUnavailable("RECOVERY_HISTORY_AMBIGUOUS")
        anchors = [(url, stamp) for url, stamp in anchors
                   if urlsplit(url).scheme == "https" and urlsplit(url).netloc == "chatgpt.com"
                   and urlsplit(url).path.startswith("/c/") and isinstance(stamp, int)]
        if not anchors:
            raise HistoryUnavailable("RECOVERY_NONCE_HISTORY_NOT_FOUND")
        candidates = set()
        for _, stamp in anchors:
            rows = db.execute(
                "SELECT DISTINCT u.url FROM urls u JOIN visits v ON v.url=u.id "
                "WHERE v.visit_time BETWEEN ? AND ? AND u.url LIKE 'https://chatgpt.com/c/%' "
                "LIMIT 1001", (stamp - 120_000_000, stamp + 120_000_000)).fetchall()
            if len(rows) > 1000:
                raise HistoryUnavailable("RECOVERY_HISTORY_AMBIGUOUS")
            candidates.update(url for (url,) in rows
                              if re.fullmatch(r"https://chatgpt\.com/c/[A-Za-z0-9-]+", url))
        if not candidates:
            raise HistoryUnavailable("RECOVERY_NO_CANONICAL_CONVERSATION")
        if len(candidates) > 20:
            raise HistoryUnavailable("RECOVERY_HISTORY_AMBIGUOUS")
        return sorted(candidates)


class Stopped(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def boundary_report(result, repo, expected_root):
    try:
        report = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise Stopped("OWNER_BOUNDARY_UNVERIFIED") from None
    if result.returncode or report.get("state") != "OWNER_BOUNDARY_VALID":
        code = report.get("state")
        raise Stopped(code if code in {"OWNER_IDENTITY_REQUIRED", "OWNER_ACL_UNSAFE"}
                      else "OWNER_BOUNDARY_UNVERIFIED")
    root = Path(report["root"]).resolve()
    if root != expected_root.resolve() or not Path(report["root"]).is_absolute():
        raise Stopped("RUNTIME_PATH_UNSAFE")
    if root.is_relative_to(repo) or repo.is_relative_to(root):
        raise Stopped("RUNTIME_PATH_UNSAFE")
    # Never silently replace a legacy journal and reset its dispatch budget.
    if (root / "task-conversations.sqlite").exists():
        raise Stopped("LEGACY_STATE_RELOCATION_REQUIRED")
    return root


def windows_owner_root(account):
    if os.name != "nt":
        raise Stopped("OWNER_IDENTITY_REQUIRED")
    import ctypes
    import winreg
    buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer)):
        raise Stopped("OWNER_IDENTITY_REQUIRED")
    executable = Path(buffer.value) / "whoami.exe"
    size = ctypes.c_ulong(len(buffer))
    if not ctypes.windll.kernel32.GetComputerNameW(buffer, ctypes.byref(size)):
        raise Stopped("OWNER_IDENTITY_REQUIRED")
    machine = buffer.value
    user = subprocess.run([str(executable), "/user", "/fo", "csv", "/nh"],
                          capture_output=True, text=True, timeout=15, check=True)
    groups = subprocess.run([str(executable), "/groups", "/fo", "csv", "/nh"],
                            capture_output=True, text=True, timeout=15, check=True)
    rows = list(csv.reader(user.stdout.splitlines()))
    group_rows = list(csv.reader(groups.stdout.splitlines()))
    sid = validate_windows_identity(rows, group_rows, machine, account)
    key_path = "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\ProfileList\\" + sid
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        profile, _ = winreg.QueryValueEx(key, "ProfileImagePath")
    # Refuse environment-dependent/relative profile paths rather than trusting caller variables.
    if not isinstance(profile, str) or "%" in profile or not Path(profile).is_absolute():
        raise Stopped("RUNTIME_PATH_UNSAFE")
    return Path(profile) / "AppData" / "Local" / "Maghsoud" / "DeepChatPrototype"


def validate_windows_identity(users, groups, machine, account):
    if len(users) != 1 or len(users[0]) != 2 or not groups or any(len(row) != 4 for row in groups):
        raise Stopped("OWNER_IDENTITY_REQUIRED")
    name, sid = users[0]
    if (name.casefold() != f"{machine}\\{account}".casefold()
            or not re.fullmatch(r"S-1-5-21-\d+-\d+-\d+-\d+", sid)
            or sid.endswith("-500") or any(row[2] == "S-1-5-32-544" for row in groups)):
        raise Stopped("OWNER_IDENTITY_REQUIRED")
    return sid


def consume_launcher_context(raw, expected_root, repo):
    try:
        metadata = json.loads(raw)
        if not isinstance(metadata, dict) or set(metadata) != {"state", "root", "ticket", "created_at"}:
            raise ValueError()
        if metadata["state"] != "OWNER_BOUNDARY_VALID":
            raise ValueError()
        if not re.fullmatch(r"launch-[0-9a-f]{32}\.json", metadata["ticket"]):
            raise ValueError()
        if type(metadata["created_at"]) is not int or not 0 <= time.time() - metadata["created_at"] <= 120:
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise Stopped("OWNER_LAUNCHER_REQUIRED") from None
    root = boundary_report(subprocess.CompletedProcess([], 0, raw), repo, expected_root)
    ticket = root / "runtime" / metadata["ticket"]
    try:
        # Root/ACLs were validated by PowerShell; disallow a replaced junction at consumption.
        for path in (root, *root.parents, root / "runtime", ticket):
            if path.is_symlink() or path.is_junction():
                raise ValueError()
        with ticket.open("r", encoding="utf-8") as stream:
            saved = json.loads(stream.read(4097))
        if saved != metadata:
            raise ValueError()
        ticket.unlink()
    except (OSError, ValueError):
        raise Stopped("OWNER_LAUNCHER_REQUIRED") from None
    return root


def owner_boundary():
    raw = os.environ.pop("MG_DEEP_CHAT_LAUNCH", None)
    if not raw:
        raise Stopped("OWNER_LAUNCHER_REQUIRED")
    folder = Path(__file__).resolve().parent
    config = json.loads((folder / "owner-config.json").read_text())
    account = config["windows_local_account"]
    if not re.fullmatch(r"MGDeepChatOwner[A-Za-z0-9_-]*", account):
        raise Stopped("OWNER_CONFIGURATION_INVALID")
    return consume_launcher_context(raw, windows_owner_root(account), folder.parent)


def conversation_url(value):
    if not re.fullmatch(r"https://chatgpt\.com/c/[a-zA-Z0-9-]+", value):
        raise Stopped("CONVERSATION_NOT_PERSISTED")
    return value


class Journal:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("CREATE TABLE IF NOT EXISTS task (id TEXT PRIMARY KEY, nonce TEXT NOT NULL, "
                            "conversation_url TEXT, turns INTEGER NOT NULL DEFAULT 0, "
                            "state TEXT NOT NULL, latest_answer TEXT)")
            columns = {r[1] for r in self.db.execute("PRAGMA table_info(task)")}
            for old, new in (("url", "conversation_url"), ("answer", "latest_answer")):
                if old in columns:
                    self.db.execute(f"ALTER TABLE task RENAME COLUMN {old} TO {new}")
            for name in ("created_at", "updated_at", "title", "certification_status",
                         "auth_state", "waiting_reason", "request_state", "request_kind", "last_error"):
                if name not in columns:
                    self.db.execute(f"ALTER TABLE task ADD COLUMN {name} TEXT")
            # Original creation times are unknowable for migrated rows; leave NULL.
            self.db.execute("UPDATE task SET updated_at=COALESCE(updated_at,?), "
                            "certification_status=COALESCE(certification_status,'NOT_CERTIFIED')", (now(),))
            self.db.execute("UPDATE task SET auth_state=COALESCE(auth_state,'NOT_CHECKED'), "
                            "request_kind=COALESCE(request_kind,'CERTIFY_TWO_PUBLIC_MESSAGES'), "
                            "request_state=COALESCE(request_state, CASE WHEN state='AMBIGUOUS' "
                            "THEN 'BLOCKED_AMBIGUOUS' WHEN certification_status='CERTIFIED_OWNER_PLUS_ATTESTED' "
                            "THEN 'COMPLETED' ELSE 'PENDING' END)")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            self.db.close()
            raise

    def get(self, task):
        return self.db.execute("SELECT * FROM task WHERE id=?", (task,)).fetchone()

    def create(self, task):
        stamp = now()
        self.db.execute("INSERT INTO task(id,nonce,state,created_at,updated_at,title,certification_status,turns, "
                        "auth_state,request_state,request_kind) "
                        "VALUES(?,?,'READY',?,?,?,'NOT_CERTIFIED',0,'NOT_CHECKED','PENDING','CERTIFY_TWO_PUBLIC_MESSAGES')",
                        (task, "MG-SYNTHETIC-" + secrets.token_hex(8), stamp, stamp,
                         "MG Portal - Task " + task))

    def reserve(self, task):
        # Commit before Send: uncertain dispatch consumes a slot and cannot replay.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.get(task)
            total = self.db.execute("SELECT COALESCE(SUM(turns),0) FROM task").fetchone()[0]
            if not row or row["state"] != "READY" or row["turns"] >= 2 or total >= 2:
                raise Stopped("DISPATCH_BLOCKED")
            if row["auth_state"] == "NEEDS_OWNER_LOGIN":
                raise Stopped("NEEDS_OWNER_LOGIN")
            if row["turns"] == 1 and row["certification_status"] != "TITLE_VERIFIED":
                raise Stopped("TITLE_NOT_VERIFIED")
            self.db.execute("UPDATE task SET turns=turns+1,state='AMBIGUOUS',request_state='IN_PROGRESS',updated_at=? WHERE id=?",
                            (now(), task))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def complete(self, task, url, answer):
        conversation_url(url)
        row = self.get(task)
        if not row or row["state"] != "AMBIGUOUS":
            raise Stopped("INVALID_COMPLETION")
        if row["conversation_url"] and row["conversation_url"] != url:
            raise Stopped("CONTINUITY_MISMATCH")
        self.db.execute("UPDATE task SET conversation_url=?,latest_answer=?,state='READY',request_state='PENDING',"
                        "last_error=NULL,auth_state='AUTHENTICATED',waiting_reason=NULL,updated_at=? "
                        "WHERE id=?", (url, answer, now(), task))

    def title_verified(self, task, title):
        row = self.get(task)
        if row["state"] != "READY" or not row["conversation_url"] or title != "MG Portal - Task " + task:
            raise Stopped("TITLE_NOT_VERIFIED")
        self.db.execute("UPDATE task SET title=?,certification_status='TITLE_VERIFIED',updated_at=? "
                        "WHERE id=?", (title, now(), task))

    def certified(self, task):
        row = self.get(task)
        if (not row or row["state"] != "READY" or row["turns"] != 2
                or row["latest_answer"] != row["nonce"]
                or row["certification_status"] not in {"TITLE_VERIFIED", "CERTIFIED_OWNER_PLUS_ATTESTED"}):
            raise Stopped("CERTIFICATION_NOT_VERIFIED")
        self.db.execute("UPDATE task SET certification_status='CERTIFIED_OWNER_PLUS_ATTESTED', "
                        "request_state='COMPLETED',last_error=NULL,updated_at=? "
                        "WHERE id=? AND turns=2 AND state='READY'", (now(), task))

    def record_stop(self, task, code):
        row = self.get(task)
        ambiguous = row["state"] == "AMBIGUOUS"
        if code == "NEEDS_OWNER_LOGIN":
            retained = row["request_state"] in {"FAILED", "UI_OR_CHALLENGE_BLOCKED", "COMPLETED"}
            request_state = ("BLOCKED_AMBIGUOUS" if ambiguous else row["request_state"]
                             if retained else "WAITING_OWNER_LOGIN")
            self.db.execute("UPDATE task SET auth_state='NEEDS_OWNER_LOGIN',waiting_reason='NEEDS_OWNER_LOGIN', "
                            "request_state=?,last_error=?,updated_at=? WHERE id=?",
                            (request_state, row["last_error"] if retained else "NEEDS_OWNER_LOGIN", now(), task))
        else:
            state = "BLOCKED_AMBIGUOUS" if ambiguous else (
                "UI_OR_CHALLENGE_BLOCKED" if code == "UI_OR_CHALLENGE_BLOCKED" else "FAILED")
            self.db.execute("UPDATE task SET request_state=?,last_error=?,updated_at=? WHERE id=?",
                            (state, code, now(), task))

    def recover_auth_wait(self):
        # Authentication recovery cannot modify execution state, URLs, answers or dispatch counts.
        self.db.execute("UPDATE task SET auth_state='AUTHENTICATED',waiting_reason=NULL, "
                        "request_state=CASE WHEN state='AMBIGUOUS' THEN 'BLOCKED_AMBIGUOUS' "
                        "WHEN request_state='WAITING_OWNER_LOGIN' THEN 'RESUMABLE' ELSE request_state END, "
                        "last_error=CASE WHEN last_error='NEEDS_OWNER_LOGIN' THEN NULL ELSE last_error END, "
                        "updated_at=? WHERE auth_state='NEEDS_OWNER_LOGIN' AND waiting_reason='NEEDS_OWNER_LOGIN'",
                        (now(),))

    def request_status(self, task):
        row = self.get(task)
        if row is None:
            return {"state": "TASK_NOT_FOUND", "portal_task_id": task, "automatic_fallback": False}
        waiting = row["auth_state"] == "NEEDS_OWNER_LOGIN"
        total = self.db.execute("SELECT COALESCE(SUM(turns),0) FROM task").fetchone()[0]
        state = ("NEEDS_OWNER_LOGIN" if waiting else "AMBIGUOUS" if row["state"] == "AMBIGUOUS"
                 else row["request_state"])
        return {"state": state, "portal_task_id": row["id"], "conversation_url": row["conversation_url"],
                "execution_state": row["state"], "turns": row["turns"], "request_kind": row["request_kind"],
                "request_state": row["request_state"], "auth_state": row["auth_state"],
                "waiting_reason": row["waiting_reason"], "updated_at": row["updated_at"],
                "resumable": not waiting and row["state"] == "READY" and
                    row["request_state"] in {"PENDING", "RESUMABLE"} and (total < 2 or row["turns"] == 2),
                "notification": {"code": "DEEP_CHAT_OWNER_LOGIN_REQUIRED",
                    "message": "Deep Chat session expired. Owner login required."} if waiting else None,
                "automatic_fallback": False, "backend": "normal_chatgpt_web"}


@contextlib.contextmanager
def exclusive(root):
    lock = root / "runtime" / "worker.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise Stopped("WORKER_LOCKED") from None
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink()


@contextlib.contextmanager
def browser(root):
    os.environ.pop("DEBUG", None)
    os.environ.pop("PWDEBUG", None)
    from playwright.sync_api import sync_playwright
    with open(os.devnull, "w") as sink, contextlib.redirect_stderr(sink):
        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    str(root / "profile"), channel="msedge", headless=False,
                    chromium_sandbox=True, accept_downloads=False,
                )
            except Exception:
                # Launch diagnostics may contain private paths; never retry another browser.
                raise Stopped("EDGE_LAUNCH_FAILED") from None
            try:
                yield WebUI(context.pages[0] if context.pages else context.new_page())
            finally:
                context.close()


def visible(locator):
    return locator.count() == 1 and locator.is_visible()


def any_visible(locator):
    return any(locator.nth(i).is_visible() for i in range(locator.count()))


def classify_session(url, *, challenge=False, login=False, profile=False, composer=False, auth_invalid=False):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in {"chatgpt.com", "auth.openai.com"}:
        return "UNKNOWN_SAFE_STOP"
    if challenge:
        return "UI_OR_CHALLENGE_BLOCKED"
    if parsed.netloc == "auth.openai.com" or login or auth_invalid or parsed.path in {"/auth/login", "/auth/error"}:
        return "NEEDS_OWNER_LOGIN"
    if profile and composer:
        return "AUTHENTICATED"
    return "UNKNOWN_SAFE_STOP"


def new_chat_guard(url, message_count, temporary_state, composer_empty):
    if temporary_state is True:
        raise Stopped("TEMPORARY_CHAT_REJECTED")
    if temporary_state is not False:
        raise Stopped("NORMAL_CHAT_UNVERIFIED")

    if url not in {"https://chatgpt.com", "https://chatgpt.com/"} or message_count or not composer_empty:
        raise Stopped("NEW_CHAT_NOT_CONFIRMED")


def first_prompt(nonce):
    return f"PUBLIC synthetic test. Remember this nonce: {nonce}. Reply NONCE_STORED."



class WebUI:
    def __init__(self, page):
        self.page = page

    def profile_control(self):
        return self.page.get_by_role("button", name="Open profile menu", exact=True)

    def composer(self):
        return self.page.get_by_role("textbox", name="Ask ChatGPT", exact=True)

    def send_button(self):
        return self.page.get_by_role("button", name="Send", exact=True)

    def messages(self, author=None):
        main = self.page.get_by_role("main")
        if not visible(main):
            raise Stopped("UI_OR_CHALLENGE_BLOCKED")
        selectors = {"user": '[data-user-message-bubble="true"]',
                     "assistant": '[data-markdown-text-style="assistant-message"]'}
        modern = main.locator(", ".join(selectors.values()))
        if modern.count():
            return main.locator(selectors[author]) if author else modern
        selector = '[data-message-author-role' + (f'="{author}"' if author else '') + ']'
        return main.locator(selector)

    def temporary_active(self):
        return (any_visible(self.page.get_by_role("button", name="Turn off temporary chat", exact=True)) or
                any_visible(self.page.get_by_role("heading", name="Temporary chat", exact=True)))

    def wait_ready(self):
        deadline = time.monotonic() + 10
        while self.session() == "UNKNOWN_SAFE_STOP" and time.monotonic() < deadline:
            self.page.wait_for_timeout(250)

    def navigate(self, url):
        self.page.goto(url, wait_until="domcontentloaded")
        self.wait_ready()

    def session(self):
        p = self.page
        challenge = p.get_by_text(re.compile(
            r"^(Verify you are human|Checking your browser|Too many requests|You've reached.*limit.*)$",
            re.I))
        return classify_session(p.url,
            challenge=any_visible(challenge),
            login=any(any_visible(p.get_by_role(role, name=name, exact=True))
                      for role in ("button", "link") for name in ("Log in", "Sign up")),
            auth_invalid=any_visible(p.get_by_text(re.compile(
                r"^(Your session has expired\.?|Session expired\.?|Please log in again\.?|Authentication failed\.?)$", re.I))),
            profile=visible(self.profile_control()),
            composer=visible(self.composer()))

    def authenticated(self):
        if self.temporary_active():
            raise Stopped("TEMPORARY_CHAT_REJECTED")
        state = self.session()
        if state != "AUTHENTICATED":
            raise Stopped(state)

    def normal_mode(self):
        if self.temporary_active():
            raise Stopped("TEMPORARY_CHAT_REJECTED")
        if not visible(self.composer()) or not visible(self.profile_control()):
            raise Stopped("NORMAL_CHAT_UNVERIFIED")
        return False

    def fresh_guard(self):
        self.authenticated()

        composer = self.composer()
        if (
            not visible(composer)
            or composer.get_attribute("contenteditable") != "true"
        ):
            raise Stopped("NEW_CHAT_NOT_CONFIRMED")

        new_chat_guard(
            self.page.url,
            self.messages().count(),
            self.normal_mode(),
            not composer.inner_text().strip(),
        )

    def new_chat(self):
        self.authenticated()

        # Navigating to chatgpt.com may already result in a verified blank
        # normal chat. In that case a New chat click is unnecessary.
        try:
            self.fresh_guard()
            return
        except Stopped as exc:
            if str(exc) not in {
                "NEW_CHAT_NOT_CONFIRMED",
                "NORMAL_CHAT_UNVERIFIED",
                "UNKNOWN_SAFE_STOP",
            }:
                raise

        sidebar = self.page.locator("#app-shell-sidebar:visible")
        if not visible(sidebar):
            raise Stopped("NEW_CHAT_NOT_CONFIRMED")
        buttons = sidebar.locator('button[type="button"].sidebar-item:visible')
        candidates = [buttons.nth(i) for i in range(buttons.count())
                      if buttons.nth(i).is_visible() and buttons.nth(i).inner_text().strip() == "New chat"]
        if len(candidates) != 1:
            raise Stopped("NEW_CHAT_NOT_CONFIRMED")
        action = candidates[0]
        action.click(timeout=5000)

        # Verify the resulting page; the click itself is never replayed.
        deadline = time.monotonic() + 10

        while True:
            try:
                self.fresh_guard()
                return
            except Stopped as exc:
                if str(exc) not in {
                    "NEW_CHAT_NOT_CONFIRMED",
                    "NORMAL_CHAT_UNVERIFIED",
                    "UNKNOWN_SAFE_STOP",
                }:
                    raise

                if time.monotonic() >= deadline:
                    raise

            self.page.wait_for_timeout(250)

    def first_turn_evidence(self, url, nonce):
        self.same_chat(url)
        messages = self.messages()
        if messages.count() != 2:
            return False
        user, assistant = messages.nth(0), messages.nth(1)
        return (user.is_visible() and assistant.is_visible()
                and (user.get_attribute("data-user-message-bubble") == "true"
                     or user.get_attribute("data-message-author-role") == "user")
                and (assistant.get_attribute("data-markdown-text-style") == "assistant-message"
                     or assistant.get_attribute("data-message-author-role") == "assistant")
                and user.inner_text().strip() == first_prompt(nonce)
                and assistant.inner_text().strip() == "NONCE_STORED")

    def recover_ambiguous_first_turn(self, nonce, candidates):
        matches = []
        for url in candidates:
            conversation_url(url)
            self.navigate(url)
            self.same_chat(url)
            deadline = time.monotonic() + 20
            while self.messages().count() < 2 and time.monotonic() < deadline:
                self.page.wait_for_timeout(250)
                self.same_chat(url)
            if not self.first_turn_evidence(url, nonce):
                continue
            self.wait_answer(0, url, expected="NONCE_STORED", timeout=30)
            self.reload()
            if not self.wait_first_turn_evidence(url, nonce):
                raise Stopped("RECOVERY_EVIDENCE_NOT_PERSISTED")
            matches.append(url)
        if len(matches) != 1:
            raise Stopped("RECOVERY_AMBIGUOUS_MATCHES" if matches else "RECOVERY_NONCE_CONVERSATION_NOT_FOUND")
        self.navigate(matches[0])
        if not self.wait_first_turn_evidence(matches[0], nonce):
            raise Stopped("RECOVERY_EVIDENCE_NOT_PERSISTED")
        return matches[0], "NONCE_STORED"

    def wait_first_turn_evidence(self, url, nonce):
        deadline = time.monotonic() + 10
        while True:
            if self.first_turn_evidence(url, nonce):
                return True
            if time.monotonic() >= deadline:
                return False
            self.page.wait_for_timeout(250)

    def wait_answer(self, before, url=None, *, expected=None, timeout=120):
        deadline = time.monotonic() + timeout
        last, stable = None, 0
        while time.monotonic() < deadline:
            self.page.wait_for_timeout(1000)
            self.authenticated()
            self.normal_mode()
            if url is not None:
                self.same_chat(url)
            messages = self.messages("assistant")
            if messages.count() != before + 1:
                stable = 0
                continue
            answer = self.latest_answer()
            done = self.response_complete(messages)
            stable = stable + 1 if answer and answer == last and done else 0
            last = answer
            if stable >= 5 and (expected is None or answer == expected):
                return conversation_url(self.page.url), answer
        raise Stopped("AMBIGUOUS")

    def same_chat(self, url):
        self.authenticated()
        self.normal_mode()
        if conversation_url(self.page.url) != url:
            raise Stopped("CONTINUITY_MISMATCH")

    def history_row(self, url):
        self.same_chat(url)
        # A title or sidebar position cannot bind a row to the active URL.
        # Without a unique positive semantic current state, do not open any menu.
        sidebar = self.page.locator("#app-shell-sidebar:visible")
        if not visible(sidebar):
            raise Stopped("TITLE_UI_UNAVAILABLE")
        rows = sidebar.locator(
            'div[role="button"][aria-label][aria-current="page"], '
            'div[role="button"][aria-label][aria-current="true"], '
            'div[role="button"][aria-label][aria-selected="true"]')
        if not visible(rows) or not (rows.get_attribute("aria-label") or "").strip():
            raise Stopped("TITLE_UI_UNAVAILABLE")
        menu = rows.get_by_role("button", name="Chat actions", exact=True)
        if menu.count() != 1:
            raise Stopped("TITLE_UI_UNAVAILABLE")
        return rows, menu

    def prepare_sidebar(self, url):
        self.same_chat(url)
        sidebar = self.page.locator("#app-shell-sidebar:visible")
        if not visible(sidebar):
            raise Stopped("TITLE_UI_UNAVAILABLE")
        trigger = sidebar.locator(
            'button[data-app-shell-sidebar-trigger="true"][aria-controls="app-shell-sidebar"]:visible')
        if trigger.count() == 0:
            return
        if not visible(trigger):
            raise Stopped("TITLE_UI_UNAVAILABLE")
        expanded = trigger.get_attribute("aria-expanded")
        if expanded == "true":
            return
        if expanded != "false":
            raise Stopped("TITLE_UI_UNAVAILABLE")
        trigger.click(timeout=5000)
        deadline = time.monotonic() + 5
        while True:
            self.same_chat(url)
            if visible(trigger) and trigger.get_attribute("aria-expanded") == "true":
                return
            if time.monotonic() >= deadline:
                raise Stopped("TITLE_UI_UNAVAILABLE")
            self.page.wait_for_timeout(250)

    def verify_title(self, url, title):
        deadline = time.monotonic() + 5
        while True:
            row, _ = self.history_row(url)
            if row.get_attribute("aria-label") == title:
                self.same_chat(url)
                return
            if time.monotonic() >= deadline:
                raise Stopped("TITLE_NOT_VERIFIED")
            self.page.wait_for_timeout(250)

    def rename(self, url, title):
        row, menu = self.history_row(url)
        row.hover()
        row, menu = self.history_row(url)
        if not visible(menu):
            raise Stopped("TITLE_UI_UNAVAILABLE")
        menu.click()
        action = self.page.get_by_role("menu").get_by_role("menuitem", name="Rename", exact=True)
        if not visible(action):
            raise Stopped("TITLE_UI_UNAVAILABLE")
        action.click()
        editor = row.get_by_role("textbox")
        if visible(editor):
            editor.fill(title)
            editor.press("Enter")
        else:
            dialog = self.page.get_by_role("dialog", name=re.compile(r"^Rename (chat|conversation)$", re.I))
            editor = dialog.get_by_role("textbox")
            save = dialog.get_by_role("button", name=re.compile(r"^(Save|Rename)$"))
            if not visible(dialog) or not visible(editor) or not visible(save) or not save.is_enabled():
                raise Stopped("TITLE_UI_UNAVAILABLE")
            editor.fill(title)
            save.click()
        self.wait_ready()
        self.verify_title(url, title)

    def response_complete(self, messages):
        stop_controls = [
            self.page.get_by_role(
                "button",
                name=re.compile(r"^Stop(?: generating| streaming)?$", re.I),
            ),
            self.page.locator('[data-testid*="stop"]:visible'),
            self.page.locator('button[aria-label*="Stop"]:visible'),
            self.page.locator('button[title*="Stop"]:visible'),
        ]

        if any(any_visible(control) for control in stop_controls):
            return False

        composer = self.composer()
        if not visible(composer) or composer.get_attribute("contenteditable") != "true":
            return False

        if composer.inner_text().strip():
            return False

        if not messages.count():
            return False

        latest = messages.last
        if not latest.is_visible():
            return False

        return bool(latest.inner_text().strip())

    def latest_answer(self):
        messages = self.messages("assistant")
        if not messages.count() or not messages.last.is_visible():
            raise Stopped("RESPONSE_NOT_PERSISTED")
        return messages.last.inner_text().strip()

    def reload(self):
        self.page.reload(wait_until="domcontentloaded")
        self.wait_ready()


def ensure_title(ui, journal, task):
    row = journal.get(task)
    title = "MG Portal - Task " + task
    ui.same_chat(row["conversation_url"])
    ui.prepare_sidebar(row["conversation_url"])
    if row["certification_status"] not in {"TITLE_VERIFIED", "CERTIFIED_OWNER_PLUS_ATTESTED"}:
        ui.rename(row["conversation_url"], title)
    ui.reload()
    ui.prepare_sidebar(row["conversation_url"])
    ui.verify_title(row["conversation_url"], title)
    if row["certification_status"] != "CERTIFIED_OWNER_PLUS_ATTESTED":
        journal.title_verified(task, title)


def send(ui, journal, task, prompt):
    try:
        return send_checked(ui, journal, task, prompt)
    except Stopped as exc:
        journal.record_stop(task, str(exc))
        raise
    except (Exception, KeyboardInterrupt):
        journal.record_stop(task, "FAILED")
        raise Stopped("AMBIGUOUS" if journal.get(task)["state"] == "AMBIGUOUS" else "FAILED") from None


def send_checked(ui, journal, task, prompt):
    ui.authenticated()
    row = journal.get(task)
    if row["state"] != "READY":
        raise Stopped("DISPATCH_BLOCKED")
    if row["conversation_url"]:
        ui.same_chat(row["conversation_url"])
    else:
        ui.fresh_guard()
    page = ui.page
    messages = ui.messages("assistant")
    before = messages.count()
    composer = ui.composer()
    if not visible(composer) or composer.get_attribute("contenteditable") != "true":
        raise Stopped("UI_OR_CHALLENGE_BLOCKED")
    composer.fill(prompt)
    button = ui.send_button()
    if not visible(button) or not button.is_enabled() or button.get_attribute("type") != "submit":
        raise Stopped("UI_OR_CHALLENGE_BLOCKED")
    ui.authenticated()
    ui.normal_mode()
    if row["conversation_url"]:
        ui.same_chat(row["conversation_url"])
    else:
        new_chat_guard(page.url, ui.messages().count(), False, True)
    journal.reserve(task)
    button.click(timeout=5000)
    expected = "NONCE_STORED" if not row["conversation_url"] else row["nonce"]
    url, answer = ui.wait_answer(before, row["conversation_url"], expected=expected)
    if row["conversation_url"] and url != row["conversation_url"]:
        raise Stopped("CONTINUITY_MISMATCH")
    journal.complete(task, url, answer)
    return url, answer



@contextlib.contextmanager
def owner_login_phase(state):
    try:
        yield
    except Stopped:
        raise
    except (Exception, KeyboardInterrupt):
        raise Stopped(state) from None


def owner_login(root, marker):
    failure = None
    try:
        with browser(root) as ui:
            try:
                with owner_login_phase("OWNER_LOGIN_FLOW_FAILED"):
                    with owner_login_phase("CHATGPT_NAVIGATION_FAILED"):
                        ui.navigate("https://chatgpt.com/")
                    with owner_login_phase("OWNER_INTERACTIVE_INPUT_UNAVAILABLE"):
                        input("Owner only: manually sign in, verify Plus, return to Chat, then press Enter. ")
                    with owner_login_phase("AUTH_STATE_CHECK_FAILED"):
                        ui.authenticated()
                    with owner_login_phase("OWNER_INTERACTIVE_INPUT_UNAVAILABLE"):
                        attestation = input("Type PLUS to attest your Plus account: ")
                    if attestation != "PLUS":
                        raise Stopped("PLUS_NOT_CONFIRMED")
                    marker.write_text("Owner Plus attestation; not authentication evidence.\n")
            except Stopped as exc:
                # Browser cleanup must not hide the original safe phase or explicit state.
                failure = exc
    except Stopped:
        if failure is not None:
            raise failure from None
        raise
    except (Exception, KeyboardInterrupt):
        if failure is not None:
            raise failure from None
        raise Stopped("EDGE_CONTEXT_FAILED") from None
    if failure is not None:
        raise failure
    with owner_login_phase("OWNER_LOGIN_FLOW_FAILED"):
        recover_owner_auth(root)
    return {"state": "AUTHENTICATED"}


def recover_owner_auth(root):
    path = root / "state" / "task-conversations.sqlite"
    if path.is_file():
        journal = Journal(path)
        try:
            journal.recover_auth_wait()
        finally:
            journal.db.close()


def persist_session_expiry(root):
    path = root / "state" / "task-conversations.sqlite"
    if path.is_file():
        journal = Journal(path)
        try:
            tasks = journal.db.execute("SELECT id FROM task WHERE request_state != 'COMPLETED'").fetchall()
            for task in tasks:
                journal.record_stop(task["id"], "NEEDS_OWNER_LOGIN")
        finally:
            journal.db.close()


@contextlib.contextmanager
def request_browser(root, journal, task):
    failure = None
    try:
        with browser(root) as ui:
            try:
                yield ui
            except Stopped as exc:
                # Persist the safe failure before browser cleanup can obscure it.
                journal.record_stop(task, str(exc))
                failure = exc
    except (Exception, KeyboardInterrupt):
        if failure is not None:
            raise failure from None
        raise
    if failure is not None:
        raise failure


def run(args):
    root = owner_boundary()
    marker = root / "runtime" / "owner-ready"
    with exclusive(root):
        if args.command == "owner-login":
            return owner_login(root, marker)
        if args.command == "status":
            with browser(root) as ui:
                ui.navigate("https://chatgpt.com/")
                state = ui.session()
                if state == "NEEDS_OWNER_LOGIN":
                    persist_session_expiry(root)
                return {"state": state}
        if args.command == "task-status":
            path = root / "state" / "task-conversations.sqlite"
            if not path.is_file():
                return {"state": "TASK_NOT_FOUND", "portal_task_id": args.task, "automatic_fallback": False}
            journal = Journal(path)
            try:
                return journal.request_status(args.task)
            finally:
                journal.db.close()
        if not args.approve_two_synthetic_messages:
            raise Stopped("OWNER_APPROVAL_REQUIRED")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.task):
            raise Stopped("INVALID_TASK")
        journal = Journal(root / "state" / "task-conversations.sqlite")
        try:
            if not journal.get(args.task):
                journal.create(args.task)
            row = journal.get(args.task)

            if row["state"] == "AMBIGUOUS" and row["turns"] == 1 and not row["conversation_url"]:
                if not marker.exists() or row["auth_state"] == "NEEDS_OWNER_LOGIN":
                    raise Stopped("NEEDS_OWNER_LOGIN")
                try:
                    candidates = history_candidates(root, row["nonce"])
                except HistoryUnavailable as exc:
                    raise Stopped(str(exc)) from None
                with request_browser(root, journal, args.task) as ui:
                    url, answer = ui.recover_ambiguous_first_turn(row["nonce"], candidates)
                    if answer != "NONCE_STORED" or url not in candidates:
                        raise Stopped("RECOVERY_EVIDENCE_NOT_PERSISTED")
                    journal.complete(args.task, url, answer)
                row = journal.get(args.task)
            if args.command == "recover-first-turn":
                return journal.request_status(args.task)

            if row["state"] != "READY":
                raise Stopped("AMBIGUOUS")

            if not marker.exists() or row["auth_state"] == "NEEDS_OWNER_LOGIN":
                raise Stopped("NEEDS_OWNER_LOGIN")
            with request_browser(root, journal, args.task) as ui:
                ui.navigate(row["conversation_url"] or "https://chatgpt.com/")
                if row["turns"] == 0:
                    ui.new_chat()
                    send(ui, journal, args.task,
                         first_prompt(row["nonce"]))
                ensure_title(ui, journal, args.task)
            row = journal.get(args.task)
            with request_browser(root, journal, args.task) as ui:
                ui.navigate(row["conversation_url"])
                ui.same_chat(row["conversation_url"])
                if row["turns"] == 1:
                    send(ui, journal, args.task,
                         "What synthetic nonce did I ask you to remember? Reply with only that nonce.")
                row = journal.get(args.task)
                if row["latest_answer"].strip() != row["nonce"]:
                    raise Stopped("NONCE_MISMATCH")
                ui.reload()
                ui.same_chat(row["conversation_url"])
                if ui.latest_answer() != row["nonce"]:
                    raise Stopped("RESPONSE_NOT_PERSISTED")
            journal.certified(args.task)
            return {"state": "CERTIFIED_WITH_OWNER_PLUS_ATTESTATION", "portal_task_id": args.task,
                    "conversation_url": row["conversation_url"], "response_text": row["latest_answer"],
                    "messages": 2, "runtime": "normal_chatgpt_web"}
        except Stopped as exc:
            journal.record_stop(args.task, str(exc))
            if str(exc) == "NEEDS_OWNER_LOGIN":
                return journal.request_status(args.task)
            raise
        except (Exception, KeyboardInterrupt):
            journal.record_stop(args.task, "FAILED")
            return journal.request_status(args.task)
        finally:
            journal.db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "owner-login", "certify", "task-status", "recover-first-turn"])
    parser.add_argument("--approve-two-synthetic-messages", action="store_true")
    parser.add_argument("--task", default="synthetic-certification-001")
    args = parser.parse_args()
    try:
        result = run(args)
    except Stopped as exc:
        result = {"state": str(exc)}
    except (Exception, KeyboardInterrupt):
        result = {"state": "OWNER_LOGIN_FLOW_FAILED" if args.command == "owner-login" else "UNKNOWN_SAFE_STOP"}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
