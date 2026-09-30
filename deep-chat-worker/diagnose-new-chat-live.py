"""Owner-run, one-click observation of the current worker's real new_chat flow.

Place beside worker.py, owner-config.json and check-owner.ps1 in the existing
owner runtime code folder. Run with its existing Python, -I -B. No journal,
launcher ticket, worker lock, readiness marker or task state is written.
Edge itself can update its persistent profile as part of normal browser use.
Close other owner worker/Edge sessions before running; never run concurrently.
"""

import ast
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time

sys.dont_write_bytecode = True


def emit(name, value):
    print(f"{name}={value!r}", flush=True)


def load_worker(folder):
    spec = importlib.util.spec_from_file_location("diagnostic_worker", folder / "worker.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    return worker


def owner_root(w, folder):
    account = json.loads((folder / "owner-config.json").read_text())["windows_local_account"]
    if account != "MGDeepChatOwner":
        raise w.Stopped("OWNER_CONFIGURATION_INVALID")
    # Identity is verified before any private profile path is inspected.
    expected = w.windows_owner_root(account)
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer)):
        raise w.Stopped("OWNER_IDENTITY_REQUIRED")
    powershell = Path(buffer.value) / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    report = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-File",
         str(folder / "check-owner.ps1"), "-AccountName", account],
        capture_output=True, text=True, timeout=120, check=False,
    )
    root = w.boundary_report(report, folder.parent, expected)
    if (root / "runtime" / "worker.lock").exists():
        raise w.Stopped("WORKER_LOCKED")
    return root


class Diagnostic:
    def __init__(self, w, ui):
        self.w = w
        self.ui = ui
        self.clicked = False
        self.click_failed = False
        self.started = None
        self.iteration = 0
        self.failed_stage = None
        self.guard_arguments = None
        self.passed = False

    def observe(self, name, function):
        try:
            value = function()
            emit(name, value)
            return value
        except self.w.Stopped as exc:
            emit(name, "Stopped:" + str(exc))
        except Exception as exc:
            emit(name, "EXCEPTION:" + type(exc).__name__ + ":" + str(exc))
        return None

    def locator(self, name, locator):
        count = self.observe(name + ".count", locator.count)
        if count is not None:
            self.observe(name + ".visibility", lambda: [locator.nth(i).is_visible() for i in range(count)])
        self.observe(name + ".worker_visible", lambda: self.w.visible(locator))

    def before(self):
        p = self.ui.page
        emit("BEFORE.page.url", p.url)
        sidebar = p.locator("#app-shell-sidebar:visible")
        self.locator("BEFORE.sidebar", sidebar)
        candidates = sidebar.locator('button[type="button"].sidebar-item:visible')
        count = self.observe("BEFORE.structural_candidate_count", candidates.count)
        if count is not None:
            self.observe("BEFORE.qualifying_new_chat_count", lambda: sum(
                candidates.nth(i).is_visible() and candidates.nth(i).inner_text().strip() == "New chat"
                for i in range(count)))
        self.observe("BEFORE.authenticated", self.ui.authenticated)
        self.observe("BEFORE.normal_mode", self.ui.normal_mode)

    def click(self, action, **kwargs):
        if self.clicked:
            raise self.w.Stopped("DIAGNOSTIC_SECOND_CLICK_REFUSED")
        self.clicked = True
        try:
            action.click(**kwargs)
        except BaseException:
            self.click_failed = True
            raise
        self.started = time.monotonic()

    def install(self):
        w, ui = self.w, self.ui
        original_auth = ui.authenticated
        original_normal = ui.normal_mode
        original_fresh = ui.fresh_guard
        original_guard = w.new_chat_guard

        def traced_auth():
            try:
                result = original_auth()
                emit("FLOW.authenticated", result)
                return result
            except BaseException as exc:
                self.failed_stage = "AUTHENTICATED"
                emit("FLOW.authenticated", "Stopped:" + str(exc) if isinstance(exc, w.Stopped) else repr(exc))
                raise

        def traced_normal():
            try:
                result = original_normal()
                emit("FLOW.normal_mode", result)
                return result
            except BaseException as exc:
                self.failed_stage = "NORMAL_MODE"
                emit("FLOW.normal_mode", "Stopped:" + str(exc) if isinstance(exc, w.Stopped) else repr(exc))
                raise

        def traced_guard(url, message_count, temporary_state, composer_empty):
            self.guard_arguments = (url, message_count, temporary_state, composer_empty)
            emit("FLOW.new_chat_guard.arguments", dict(url=url, message_count=message_count,
                 temporary_state=temporary_state, composer_empty=composer_empty))
            try:
                result = original_guard(url, message_count, temporary_state, composer_empty)
            except w.Stopped as exc:
                self.failed_stage = (
                    "NORMAL_MODE" if temporary_state is not False else
                    "URL" if url not in {"https://chatgpt.com", "https://chatgpt.com/"} else
                    "MESSAGE" if message_count else "COMPOSER")
                emit("FLOW.new_chat_guard", "Stopped:" + str(exc))
                raise
            emit("FLOW.new_chat_guard", "PASS")
            return result

        def traced_fresh():
            self.iteration += 1
            self.failed_stage = None
            self.guard_arguments = None
            emit("iteration", self.iteration)
            emit("elapsed_ms", round((time.monotonic() - self.started) * 1000))
            emit("page.url", ui.page.url)
            # Observe without replacing the worker's own sequential reads below.
            self.observe("authenticated", original_auth)
            self.locator("profile_control", ui.profile_control())
            self.locator("main", ui.page.get_by_role("main"))
            self.observe("message_count", lambda: ui.messages().count())
            composer = ui.composer()
            self.locator("composer", composer)
            content = self.observe("composer.inner_text", lambda: composer.inner_text(timeout=250)
                                   if composer.count() == 1 else None)
            emit("composer_empty", None if content is None else not content.strip())
            self.locator("temporary_button", ui.page.get_by_role("button", name="Turn off temporary chat", exact=True))
            self.locator("temporary_heading", ui.page.get_by_role("heading", name="Temporary chat", exact=True))
            self.observe("normal_mode", original_normal)
            try:
                result = original_fresh()
            except BaseException as exc:
                if self.failed_stage is None:
                    self.failed_stage = "MAIN" if isinstance(exc, w.Stopped) and str(exc) == "NEW_CHAT_NOT_CONFIRMED" else "TRANSITION"
                emit("FLOW.fresh_guard", "Stopped:" + str(exc) if isinstance(exc, w.Stopped) else repr(exc))
                raise
            else:
                self.passed = True
                emit("FLOW.fresh_guard", "PASS")
                return result
            finally:
                if self.guard_arguments is None:
                    emit("FLOW.new_chat_guard.arguments", "NOT_CALLED: earlier guard/read stopped")
                    emit("FLOW.new_chat_guard", "NOT_REACHED")

        ui.authenticated = traced_auth
        ui.normal_mode = traced_normal
        ui.fresh_guard = traced_fresh
        w.new_chat_guard = traced_guard
        # Change only the click call in memory; retain the actual selection, 10s
        # deadline, 250ms waits and exception/retry policy from worker.new_chat.
        tree = ast.parse(textwrap.dedent(inspect.getsource(w.WebUI.new_chat)))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "click"]
        if len(calls) != 1 or ast.unparse(calls[0].func.value) != "action":
            raise w.Stopped("DIAGNOSTIC_SOURCE_SHAPE_CHANGED")
        call = calls[0]
        call.func = ast.Attribute(value=ast.Name(id="diagnostic", ctx=ast.Load()), attr="click", ctx=ast.Load())
        call.args.insert(0, ast.Name(id="action", ctx=ast.Load()))
        ast.fix_missing_locations(tree)
        namespace = dict(vars(w), diagnostic=self)
        exec(compile(tree, str(Path(w.__file__)), "exec"), namespace)
        return lambda: namespace["new_chat"](ui)

    def result(self):
        if not self.clicked:
            return "FAIL_BEFORE_CLICK"
        if self.click_failed:
            return "CLICK_EXCEPTION"
        if self.passed:
            return "FRESH_GUARD_PASS"
        return "POST_CLICK_" + (self.failed_stage or "TRANSITION") + "_FAILURE"


def main():
    result = "FAIL_BEFORE_CLICK"
    diagnostic = None
    try:
        folder = Path(__file__).resolve().parent
        w = load_worker(folder)
        emit("worker_sha256", hashlib.sha256((folder / "worker.py").read_bytes()).hexdigest())
        root = owner_root(w, folder)
        emit("profile_path", str(root / "profile"))
        emit("profile_notice", "Edge may persist normal browser profile updates; diagnostic writes no task state")
        with w.browser(root) as ui:
            diagnostic = Diagnostic(w, ui)
            try:
                ui.navigate("https://chatgpt.com/")
                diagnostic.before()
                diagnostic.install()()
            finally:
                result = diagnostic.result()
        emit("edge_cleanup", "context.close completed")
    except (Exception, KeyboardInterrupt) as exc:
        emit("STOP", type(exc).__name__ + ":" + str(exc))
        if diagnostic is not None:
            result = diagnostic.result()
        if result == "FRESH_GUARD_PASS":
            result = "EDGE_CLEANUP_FAILURE"
    print("RESULT=" + result, flush=True)
    return 0 if result == "FRESH_GUARD_PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
