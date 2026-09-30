import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import types
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, Mock, call, patch

from worker import (Journal, Stopped, WebUI, boundary_report, browser, classify_session,
                    consume_launcher_context, conversation_url, ensure_title, exclusive,
                    main, new_chat_guard, run, send_checked, validate_windows_identity)


class OwnerLoginClassificationTests(unittest.TestCase):
    def setUp(self):
        self.diagnostic = "SYNTHETIC_PRIVATE_DIAGNOSTIC https://example.invalid/?private=synthetic"
        for target, kwargs in (
            ("worker.owner_boundary", {"return_value": Path("C:/synthetic-owner/DeepChatPrototype")}),
            ("worker.exclusive", {}), ("worker.browser", {}),
            ("builtins.input", {"side_effect": ["", "PLUS"]}),
            ("worker.Path.write_text", {}),
        ):
            patcher = patch(target, **kwargs)
            mocked = patcher.start()
            self.addCleanup(patcher.stop)
            if target == "worker.browser":
                self.browser = mocked
            elif target == "builtins.input":
                self.input = mocked
            elif target == "worker.Path.write_text":
                self.write = mocked
        self.ui = self.browser.return_value.__enter__.return_value

    def assert_output(self, state):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["worker.py", "owner-login"]), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            main()
        self.assertEqual(stdout.getvalue(), json.dumps({"state": state}) + "\n")
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn(self.diagnostic, stdout.getvalue())

    def test_navigation_exception_is_safe_phase(self):
        self.ui.navigate.side_effect = RuntimeError(self.diagnostic)
        self.assert_output("CHATGPT_NAVIGATION_FAILED")
        self.input.assert_not_called()
        self.write.assert_not_called()

    def test_input_eof_oserror_and_interrupt_are_safe_phase(self):
        for error in (EOFError, OSError, KeyboardInterrupt):
            with self.subTest(error=error):
                self.input.side_effect = error(self.diagnostic)
                self.assert_output("OWNER_INTERACTIVE_INPUT_UNAVAILABLE")
        self.write.assert_not_called()

    def test_second_input_failure_is_safe_phase(self):
        self.input.side_effect = ["", EOFError(self.diagnostic)]
        self.assert_output("OWNER_INTERACTIVE_INPUT_UNAVAILABLE")
        self.write.assert_not_called()

    def test_auth_unexpected_exception_is_safe_phase(self):
        self.ui.authenticated.side_effect = RuntimeError(self.diagnostic)
        self.assert_output("AUTH_STATE_CHECK_FAILED")
        self.write.assert_not_called()

    def test_context_entry_failure_is_safe_phase(self):
        self.browser.return_value.__enter__.side_effect = RuntimeError(self.diagnostic)
        self.assert_output("EDGE_CONTEXT_FAILED")

    def test_context_exit_failure_is_safe_phase(self):
        self.browser.return_value.__exit__.side_effect = RuntimeError(self.diagnostic)
        self.assert_output("EDGE_CONTEXT_FAILED")

    def test_marker_failure_is_safe_flow_state(self):
        self.write.side_effect = OSError(self.diagnostic)
        self.assert_output("OWNER_LOGIN_FLOW_FAILED")

    def test_explicit_states_preserved_in_all_phases(self):
        for operation, state in ((self.ui.navigate, "UI_OR_CHALLENGE_BLOCKED"),
                                 (self.ui.authenticated, "NEEDS_OWNER_LOGIN"),
                                 (self.input, "PLUS_NOT_CONFIRMED"),
                                 (self.browser.return_value.__enter__, "EDGE_LAUNCH_FAILED")):
            with self.subTest(state=state):
                previous = operation.side_effect
                operation.side_effect = Stopped(state)
                self.assert_output(state)
                operation.side_effect = previous
                self.input.side_effect = ["", "PLUS"]

    def test_cleanup_does_not_mask_original_explicit_state(self):
        self.ui.navigate.side_effect = Stopped("UI_OR_CHALLENGE_BLOCKED")
        self.browser.return_value.__exit__.side_effect = RuntimeError(self.diagnostic)
        self.assert_output("UI_OR_CHALLENGE_BLOCKED")

    def test_cleanup_does_not_mask_original_phase(self):
        self.ui.navigate.side_effect = RuntimeError(self.diagnostic)
        self.browser.return_value.__exit__.side_effect = RuntimeError(self.diagnostic)
        self.assert_output("CHATGPT_NAVIGATION_FAILED")

    def test_successful_mocked_flow_unchanged(self):
        self.assert_output("AUTHENTICATED")
        self.write.assert_called_once()


class EdgeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.api = types.ModuleType("playwright.sync_api")
        self.api.sync_playwright = MagicMock()
        self.driver = self.api.sync_playwright.return_value.__enter__.return_value
        self.context = self.driver.chromium.launch_persistent_context.return_value
        self.context.pages = [Mock()]
        self.root = Path("C:/synthetic-owner/DeepChatPrototype")
        self.modules = patch.dict("sys.modules", {
            "playwright": types.ModuleType("playwright"), "playwright.sync_api": self.api,
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_installed_edge_uses_dedicated_persistent_profile(self):
        with browser(self.root) as ui:
            self.assertIs(ui.page, self.context.pages[0])
        self.driver.chromium.launch_persistent_context.assert_called_once_with(
            str(self.root / "profile"), channel="msedge", headless=False,
            chromium_sandbox=True, accept_downloads=False,
        )
        self.context.close.assert_called_once()

    def test_edge_launch_failure_is_safe_without_retry_or_fallback(self):
        launch = self.driver.chromium.launch_persistent_context
        launch.side_effect = RuntimeError("synthetic private diagnostic")
        with self.assertRaises(Stopped) as caught:
            with browser(self.root):
                self.fail("failed launch must not yield a browser")
        self.assertEqual(str(caught.exception), "EDGE_LAUNCH_FAILED")
        launch.assert_called_once()
        self.assertEqual(len(self.driver.mock_calls), 1)

    def test_ui_failure_is_not_misclassified_as_launch_failure(self):
        with self.assertRaisesRegex(Stopped, "UNKNOWN_SAFE_STOP"):
            with browser(self.root):
                raise Stopped("UNKNOWN_SAFE_STOP")
        self.context.close.assert_called_once()


class SafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (Path(__file__).parent / ".test-runtime").mkdir(exist_ok=True)

    def setUp(self):
        # Keep synthetic test files inside the component, never in owner storage.
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent / ".test-runtime")
        self.root = Path(self.temp.name).resolve()
        (self.root / "runtime").mkdir()
        (self.root / "state").mkdir()
        self.journal = Journal(self.root / "journal.sqlite")

    def tearDown(self):
        self.journal.db.close()
        self.temp.cleanup()

    def first_turn(self):
        self.journal.create("one")
        self.journal.reserve("one")
        self.journal.complete("one", "https://chatgpt.com/c/one", "NONCE_STORED")

    def test_crash_reservation_is_durable_and_cannot_retry(self):
        self.journal.create("one")
        self.journal.reserve("one")
        other = Journal(self.root / "journal.sqlite")
        try:
            with self.assertRaises(Stopped):
                other.reserve("one")
            self.assertEqual(other.get("one")["turns"], 1)
            self.assertEqual(other.get("one")["state"], "AMBIGUOUS")
        finally:
            other.db.close()

    def test_two_messages_global_across_tasks(self):
        for task in ("one", "two"):
            self.journal.create(task)
            self.journal.reserve(task)
            self.journal.complete(task, "https://chatgpt.com/c/" + task, "synthetic")
        self.journal.create("three")
        with self.assertRaisesRegex(Stopped, "DISPATCH_BLOCKED"):
            self.journal.reserve("three")

    def test_conversation_replacement_rejected(self):
        self.first_turn()
        self.journal.title_verified("one", "MG Portal - Task one")
        self.journal.reserve("one")
        with self.assertRaisesRegex(Stopped, "CONTINUITY_MISMATCH"):
            self.journal.complete("one", "https://chatgpt.com/c/two", "synthetic")
        self.assertEqual(self.journal.get("one")["state"], "AMBIGUOUS")

    def test_two_turns_same_task_then_cap(self):
        self.first_turn()
        self.journal.title_verified("one", "MG Portal - Task one")
        self.journal.reserve("one")
        self.journal.complete("one", "https://chatgpt.com/c/one", "synthetic")
        with self.assertRaisesRegex(Stopped, "DISPATCH_BLOCKED"):
            self.journal.reserve("one")

    def test_only_normal_conversation_urls(self):
        for value in ("https://chatgpt.com/", "https://other.invalid/c/one",
                      "https://chatgpt.com/c/one?extra=synthetic", "https://chatgpt.com/g/g-one"):
            with self.assertRaises(Stopped):
                conversation_url(value)

    def test_wrong_identity_and_acl_block_before_browser(self):
        for command in ("owner-login", "certify", "status"):
            for code in ("OWNER_IDENTITY_REQUIRED", "OWNER_ACL_UNSAFE"):
                with patch("worker.owner_boundary", side_effect=Stopped(code)), patch("worker.browser") as browser:
                    with self.assertRaisesRegex(Stopped, code):
                        run(argparse.Namespace(command=command))
                    browser.assert_not_called()

    def test_security_probe_fails_closed(self):
        for code in ("OWNER_IDENTITY_REQUIRED", "OWNER_ACL_UNSAFE"):
            result = subprocess.CompletedProcess([], 1, json.dumps({"state": code}))
            with self.assertRaisesRegex(Stopped, code):
                boundary_report(result, self.root, self.root)
        with self.assertRaisesRegex(Stopped, "OWNER_BOUNDARY_UNVERIFIED"):
            boundary_report(subprocess.CompletedProcess([], 0, "invalid"), self.root, self.root)

    def test_repository_runtime_rejected(self):
        result = subprocess.CompletedProcess([], 0, json.dumps({"state": "OWNER_BOUNDARY_VALID", "root": str(self.root)}))
        with self.assertRaisesRegex(Stopped, "RUNTIME_PATH_UNSAFE"):
            boundary_report(result, self.root.parent, self.root)

    def test_legacy_journal_cannot_be_silently_reset(self):
        (self.root / "task-conversations.sqlite").touch()
        result = subprocess.CompletedProcess([], 0, json.dumps({"state": "OWNER_BOUNDARY_VALID", "root": str(self.root)}))
        with self.assertRaisesRegex(Stopped, "LEGACY_STATE_RELOCATION_REQUIRED"):
            boundary_report(result, self.root.parent / "unrelated-repository", self.root)

    def launcher_metadata(self):
        return {"state": "OWNER_BOUNDARY_VALID", "root": str(self.root),
                "ticket": "launch-" + "a" * 32 + ".json", "created_at": int(time.time())}

    def test_direct_worker_commands_require_launcher_before_identity_or_browser(self):
        for command in ("owner-login", "status", "certify"):
            with patch.dict(os.environ, {}, clear=True), patch("worker.windows_owner_root") as identity, \
                    patch("worker.browser") as browser:
                with self.assertRaisesRegex(Stopped, "OWNER_LAUNCHER_REQUIRED"):
                    run(argparse.Namespace(command=command))
                identity.assert_not_called()
                browser.assert_not_called()

    def test_launcher_cannot_choose_arbitrary_runtime_root(self):
        metadata = self.launcher_metadata()
        metadata["root"] = str(self.root.parent / "another-owner")
        with self.assertRaisesRegex(Stopped, "RUNTIME_PATH_UNSAFE"):
            consume_launcher_context(json.dumps(metadata), self.root, self.root.parent / "repo")

    def test_launcher_handoff_is_required_and_one_use(self):
        metadata = self.launcher_metadata()
        raw = json.dumps(metadata)
        ticket = self.root / "runtime" / metadata["ticket"]
        with self.assertRaisesRegex(Stopped, "OWNER_LAUNCHER_REQUIRED"):
            consume_launcher_context(raw, self.root, self.root.parent / "repo")
        ticket.write_text(raw, encoding="utf-8")
        self.assertEqual(consume_launcher_context(raw, self.root, self.root.parent / "repo"), self.root)
        self.assertFalse(ticket.exists())
        with self.assertRaisesRegex(Stopped, "OWNER_LAUNCHER_REQUIRED"):
            consume_launcher_context(raw, self.root, self.root.parent / "repo")

    def test_launcher_rejects_expired_bad_status_and_traversal_metadata(self):
        for field, value in (("state", "OWNER_ACL_UNSAFE"), ("ticket", "../outside.json"),
                             ("created_at", int(time.time()) - 121)):
            metadata = self.launcher_metadata()
            metadata[field] = value
            with self.assertRaisesRegex(Stopped, "OWNER_LAUNCHER_REQUIRED"):
                consume_launcher_context(json.dumps(metadata), self.root, self.root.parent / "repo")

    def test_python_identity_independently_rejects_wrong_account_and_admin(self):
        groups = [["synthetic Users", "group", "S-1-5-32-545", "enabled"]]
        users = [[r"MACHINE\MGDeepChatOwner", "S-1-5-21-100-200-300-1001"]]
        self.assertEqual(validate_windows_identity(users, groups, "MACHINE", "MGDeepChatOwner"), users[0][1])
        for bad_users, bad_groups in (([[r"MACHINE\Administrator", "S-1-5-21-100-200-300-500"]], groups),
                                     (users, [["Administrators", "group", "S-1-5-32-544", "deny-only"]]),
                                     ([[r"OTHER\MGDeepChatOwner", users[0][1]]], groups), (users, [])):
            with self.assertRaisesRegex(Stopped, "OWNER_IDENTITY_REQUIRED"):
                validate_windows_identity(bad_users, bad_groups, "MACHINE", "MGDeepChatOwner")

    def test_missing_login_does_not_launch_certification(self):
        with patch("worker.owner_boundary", return_value=self.root), patch("worker.browser") as browser:
            result = run(argparse.Namespace(command="certify", task="one", approve_two_synthetic_messages=True))
            self.assertEqual(result["state"], "NEEDS_OWNER_LOGIN")
            self.assertEqual(result["request_state"], "WAITING_OWNER_LOGIN")
            browser.assert_not_called()

    def test_status_uses_ui_not_marker(self):
        for state in ("NEEDS_OWNER_LOGIN", "AUTHENTICATED", "UI_OR_CHALLENGE_BLOCKED", "UNKNOWN_SAFE_STOP"):
            with patch("worker.owner_boundary", return_value=self.root), patch("worker.browser") as browser:
                ui = browser.return_value.__enter__.return_value
                ui.session.return_value = state
                self.assertEqual(run(argparse.Namespace(command="status")), {"state": state})

    def test_exclusive_browser_owner(self):
        with exclusive(self.root):
            with self.assertRaisesRegex(Stopped, "WORKER_LOCKED"):
                with exclusive(self.root):
                    self.fail("concurrent browser allowed")

    def test_new_chat_guard(self):
        new_chat_guard("https://chatgpt.com/", 0, False, True)
        for url, count, empty in (("https://chatgpt.com/c/old", 0, True),
                                  ("https://chatgpt.com/", 1, True),
                                  ("https://chatgpt.com/", 0, False)):
            with self.assertRaisesRegex(Stopped, "NEW_CHAT_NOT_CONFIRMED"):
                new_chat_guard(url, count, False, empty)

    def test_temporary_and_unknown_normal_mode_rejected(self):
        for mode, code in ((True, "TEMPORARY_CHAT_REJECTED"), (None, "NORMAL_CHAT_UNVERIFIED")):
            with self.assertRaisesRegex(Stopped, code):
                new_chat_guard("https://chatgpt.com/", 0, mode, True)

    def test_new_chat_ui_click_precedes_guard(self):
        page = Mock()
        sidebar = page.locator.return_value
        sidebar.count.return_value = 1
        sidebar.is_visible.return_value = True
        action = sidebar.locator.return_value
        action.count.return_value = 1
        action.is_visible.return_value = True
        action.nth.return_value = action
        action.inner_text.return_value = "New chat"
        ui = WebUI(page)
        with patch.object(ui, "authenticated"), patch.object(ui, "wait_ready"), patch.object(ui, "fresh_guard") as guard:
            guard.side_effect = [Stopped("NEW_CHAT_NOT_CONFIRMED"), None]
            ui.new_chat()
            action.click.assert_called_once()
            self.assertEqual(guard.call_count, 2)

    def test_session_classifications(self):
        cases = [({}, "UNKNOWN_SAFE_STOP"), ({"login": True}, "NEEDS_OWNER_LOGIN"),
                 ({"profile": True, "composer": True}, "AUTHENTICATED"),
                 ({"challenge": True, "profile": True, "composer": True}, "UI_OR_CHALLENGE_BLOCKED"),
                 ({"profile": True}, "UNKNOWN_SAFE_STOP")]
        for facts, state in cases:
            self.assertEqual(classify_session("https://chatgpt.com/", **facts), state)
        self.assertEqual(classify_session("https://auth.openai.com/log-in"), "NEEDS_OWNER_LOGIN")
        self.assertEqual(classify_session("https://chatgpt.com.other.invalid/", profile=True, composer=True), "UNKNOWN_SAFE_STOP")

    def test_title_workflow_rename_verify_then_allow_continuation(self):
        self.first_turn()
        with self.assertRaisesRegex(Stopped, "TITLE_NOT_VERIFIED"):
            self.journal.reserve("one")
        ui = Mock()
        ensure_title(ui, self.journal, "one")
        self.assertEqual(ui.mock_calls, [call.same_chat("https://chatgpt.com/c/one"),
                         call.prepare_sidebar("https://chatgpt.com/c/one"),
                         call.rename("https://chatgpt.com/c/one", "MG Portal - Task one"),
                         call.reload(), call.prepare_sidebar("https://chatgpt.com/c/one"),
                         call.verify_title("https://chatgpt.com/c/one", "MG Portal - Task one")])
        self.assertEqual(self.journal.get("one")["certification_status"], "TITLE_VERIFIED")
        self.journal.reserve("one")

    def test_title_failure_preserves_mapping_and_blocks_second_send(self):
        self.first_turn()
        ui = Mock()
        ui.verify_title.side_effect = Stopped("TITLE_NOT_VERIFIED")
        with self.assertRaises(Stopped):
            ensure_title(ui, self.journal, "one")
        self.assertEqual(self.journal.get("one")["conversation_url"], "https://chatgpt.com/c/one")
        self.assertEqual(self.journal.get("one")["turns"], 1)
        with self.assertRaisesRegex(Stopped, "TITLE_NOT_VERIFIED"):
            self.journal.reserve("one")

    def test_ui_rename_uses_only_scoped_menu_and_editor(self):
        page = Mock()
        ui = WebUI(page)
        row = Mock()
        menu = row.get_by_role.return_value
        action = page.get_by_role.return_value.get_by_role.return_value
        for item in (row, menu, action):
            item.count.return_value = 1
            item.is_visible.return_value = True
        with patch.object(ui, "history_row", return_value=(row, menu)), \
                patch.object(ui, "wait_ready") as ready, patch.object(ui, "verify_title") as verify:
            ui.rename("https://chatgpt.com/c/one", "MG Portal - Task one")
            ready.assert_called_once()
            verify.assert_called_once_with("https://chatgpt.com/c/one", "MG Portal - Task one")
        menu.click.assert_called_once()
        action.click.assert_called_once()
        menu.fill.assert_called_once_with("MG Portal - Task one")
        menu.press.assert_called_once_with("Enter")

    def test_schema_migration_preserves_ambiguous_budget(self):
        path = self.root / "legacy.sqlite"
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE task(id TEXT PRIMARY KEY,nonce TEXT,url TEXT,turns INTEGER,state TEXT,answer TEXT)")
        db.execute("INSERT INTO task VALUES('old','synthetic','https://chatgpt.com/c/old',2,'AMBIGUOUS','synthetic')")
        db.commit()
        db.close()
        migrated = Journal(path)
        try:
            row = migrated.get("old")
            self.assertEqual(row["conversation_url"], "https://chatgpt.com/c/old")
            self.assertEqual(row["turns"], 2)
            self.assertIsNone(row["created_at"])
            self.assertIsNotNone(row["updated_at"])
            with self.assertRaisesRegex(Stopped, "DISPATCH_BLOCKED"):
                migrated.reserve("old")
            migrated.create("new")
            with self.assertRaisesRegex(Stopped, "DISPATCH_BLOCKED"):
                migrated.reserve("new")
        finally:
            migrated.db.close()

    def test_new_records_have_timestamps(self):
        self.journal.create("one")
        row = self.journal.get("one")
        self.assertEqual(row["created_at"], row["updated_at"])
        self.assertTrue(row["created_at"].endswith("+00:00"))


class SemanticUITests(unittest.TestCase):
    @staticmethod
    def locator(count=1, text=""):
        item = Mock()
        item.count.return_value = count
        item.is_visible.return_value = True
        item.nth.return_value = item
        item.inner_text.return_value = text
        return item

    def normal_ui(self):
        page = Mock()
        page.url = "https://chatgpt.com/"
        controls = {("button", "Open profile menu"): self.locator(),
                    ("textbox", "Ask ChatGPT"): self.locator()}
        page.get_by_role.side_effect = lambda role, name=None, **kw: controls.get((role, name), self.locator(0))
        page.get_by_text.return_value = self.locator(0)
        controls[("textbox", "Ask ChatGPT")].get_attribute.return_value = "true"
        page.locator.return_value = self.locator(0)
        return WebUI(page), controls

    def fresh_fixture(self, buttons=None):
        ui, controls = self.normal_ui()
        main = self.locator()
        main.locator.return_value = self.locator(0)
        controls[("main", None)] = main
        sidebar = self.locator()
        if buttons is None:
            buttons = '<button type="button" class="sidebar-item relative cursor-interaction" aria-current="page"><svg /> New chat </button>'
        dom = ET.fromstring(f'<div id="app-shell-sidebar">{buttons}</div>')
        candidates = [node for node in dom.iter("button")
                      if node.get("type") == "button"
                      and "sidebar-item" in node.get("class", "").split()
                      and node.get("hidden") is None]
        action = self.locator(len(candidates))
        action.dom_candidates = candidates
        def visible_text(node):
            if node.get("hidden") is not None or node.get("style") == "display:none":
                return ""
            return (node.text or "") + "".join(visible_text(child) + (child.tail or "") for child in node)
        action.items = [self.locator(text=visible_text(node)) for node in candidates]
        for item in action.items:
            item.click.side_effect = action.click
        action.nth.side_effect = action.items.__getitem__
        semantic_actions = self.locator(2)
        semantic_actions.nth.side_effect = [action, self.locator()]
        sidebar.get_by_role.return_value = semantic_actions
        controls[("button", "New chat")] = semantic_actions
        sidebar.locator.side_effect = lambda selector: action if selector == 'button[type="button"].sidebar-item:visible' else self.locator(0)
        ui.page.locator.side_effect = lambda selector: sidebar if selector == "#app-shell-sidebar:visible" else self.locator(0)
        # Most fixture tests exercise a transition from an existing conversation.
        ui.page.url = "https://chatgpt.com/c/old"
        action.click.side_effect = lambda **kw: setattr(ui.page, "url", "https://chatgpt.com/")
        return ui, controls, sidebar, action

    def test_live_fresh_state_and_scoped_click_ignore_global_duplicates(self):
        ui, controls, sidebar, action = self.fresh_fixture()
        semantic_actions = controls[("button", "New chat")]
        self.assertEqual(semantic_actions.count(), 2)
        self.assertTrue(semantic_actions.nth(0).is_visible())
        self.assertTrue(semantic_actions.nth(1).is_visible())
        self.assertEqual(action.count(), 1)
        self.assertIsNone(action.dom_candidates[0].get("aria-label"))
        with patch.object(Journal, "reserve") as reserve:
            ui.new_chat()
            ui.fresh_guard()
            reserve.assert_not_called()
        action.click.assert_called_once_with(timeout=5000)
        ui.page.locator.assert_called_once_with("#app-shell-sidebar:visible")
        sidebar.locator.assert_called_once_with('button[type="button"].sidebar-item:visible')
        action.items[0].inner_text.assert_called_once_with()
        sidebar.get_by_role.assert_not_called()
        semantic_actions.click.assert_not_called()
        self.assertFalse(any(c.kwargs.get("name") == "New chat" for c in ui.page.get_by_role.call_args_list))

    def test_structural_dom_candidates_require_exactly_one(self):
        valid = '<button type="button" class="sidebar-item relative" aria-current="page"><svg /> New chat </button>'
        unrelated = (
            '<button type="button" aria-label="New chat">Other action</button>'
            '<button type="button" class="sidebar-item" aria-label="New chat">New chat settings</button>'
            '<button type="button" class="other-sidebar-item">New chat</button>'
            '<button type="submit" class="sidebar-item">New chat</button>'
            '<a role="button" class="sidebar-item" aria-label="New chat">New chat</a>'
            '<button type="button" class="sidebar-item" hidden="hidden">New chat</button>'
        )
        for count in (0, 1, 2):
            with self.subTest(valid_candidates=count):
                ui, _, _, action = self.fresh_fixture(valid * count + unrelated)
                with patch.object(Journal, "reserve") as reserve:
                    if count == 1:
                        ui.new_chat()
                        action.click.assert_called_once_with(timeout=5000)
                    else:
                        with self.assertRaisesRegex(Stopped, "NEW_CHAT_NOT_CONFIRMED"):
                            ui.new_chat()
                        action.click.assert_not_called()
                    for item in action.items:
                        if count == 1 and item.inner_text.return_value.strip() == "New chat":
                            item.click.assert_called_once_with(timeout=5000)
                        else:
                            item.click.assert_not_called()
                    reserve.assert_not_called()

    def test_scoped_ambiguity_missing_and_hidden_fail_before_click(self):
        for target in ("sidebar",):
            for attr, value in (("count", 0), ("count", 2), ("is_visible", False)):
                with self.subTest(target=target, attr=attr, value=value):
                    ui, _, sidebar, action = self.fresh_fixture()
                    getattr(sidebar if target == "sidebar" else action, attr).return_value = value
                    with patch.object(Journal, "reserve") as reserve:
                        with self.assertRaisesRegex(Stopped, "NEW_CHAT_NOT_CONFIRMED"):
                            ui.new_chat()
                        reserve.assert_not_called()
                    action.click.assert_not_called()

    def test_new_chat_uses_visible_inner_text_with_only_edge_whitespace_stripped(self):
        cases = (
            ('New chat', True),
            ('<span hidden="hidden">Hidden label</span><span>New chat</span>', True),
            ('<span style="display:none">Hidden label</span><span>New chat</span>', True),
            (' \n\tNew chat\t\n ', True),
            ('New chat settings', False),
            ('New  chat', False),
            ('', False),
        )
        for content, qualifies in cases:
            with self.subTest(content=content):
                ui, _, _, action = self.fresh_fixture(
                    f'<button type="button" class="sidebar-item">{content}</button>')
                with patch.object(Journal, "reserve") as reserve:
                    if qualifies:
                        ui.new_chat()
                        action.click.assert_called_once_with(timeout=5000)
                    else:
                        with self.assertRaisesRegex(Stopped, "NEW_CHAT_NOT_CONFIRMED"):
                            ui.new_chat()
                        action.click.assert_not_called()
                    reserve.assert_not_called()
                action.items[0].inner_text.assert_called_once_with()

    def test_candidate_hidden_during_inspection_fails_before_click(self):
        ui, _, _, action = self.fresh_fixture()
        action.items[0].is_visible.return_value = False
        with patch.object(Journal, "reserve") as reserve:
            with self.assertRaisesRegex(Stopped, "NEW_CHAT_NOT_CONFIRMED"):
                ui.new_chat()
            reserve.assert_not_called()
        action.click.assert_not_called()

    def test_already_fresh_root_never_clicks_or_reserves(self):
        ui, _, _, action = self.fresh_fixture()
        ui.page.url = "https://chatgpt.com/"
        with patch.object(Journal, "reserve") as reserve:
            ui.new_chat()
            reserve.assert_not_called()
        action.click.assert_not_called()

    def test_fresh_guard_invalid_live_conditions_fail_closed(self):
        for condition in ("path", "query", "host", "scheme", "fragment", "messages", "main", "empty", "composer", "profile", "temp_button", "temp_heading"):
            with self.subTest(condition=condition):
                ui, controls, _, _ = self.fresh_fixture()
                urls = {"path": "https://chatgpt.com/c/old", "query": "https://chatgpt.com/?x=1",
                        "host": "https://other.invalid/", "scheme": "http://chatgpt.com/",
                        "fragment": "https://chatgpt.com/#x"}
                if condition in urls:
                    ui.page.url = urls[condition]
                elif condition == "messages":
                    controls[("main", None)].locator.return_value.count.return_value = 1
                elif condition == "main":
                    controls[("main", None)].is_visible.return_value = False
                elif condition == "empty":
                    controls[("textbox", "Ask ChatGPT")].inner_text.return_value = "draft"
                elif condition in ("composer", "profile"):
                    key = ("textbox", "Ask ChatGPT") if condition == "composer" else ("button", "Open profile menu")
                    controls[key].is_visible.return_value = False
                else:
                    key = ("button", "Turn off temporary chat") if condition == "temp_button" else ("heading", "Temporary chat")
                    controls[key] = self.locator()
                with self.assertRaises(Stopped):
                    ui.fresh_guard()

    def test_new_chat_polls_full_readiness_without_reclick_or_reservation(self):
        ui, controls, _, action = self.fresh_fixture()
        def transition(**kwargs):
            ui.page.url = "https://chatgpt.com/c/old"
            controls[("main", None)].locator.return_value.count.return_value = 2
        def ready(milliseconds):
            ui.page.url = "https://chatgpt.com/"
            controls[("main", None)].locator.return_value.count.return_value = 0
        action.click.side_effect = transition
        ui.page.wait_for_timeout.side_effect = ready
        with patch.object(Journal, "reserve") as reserve:
            ui.new_chat()
            reserve.assert_not_called()
        action.click.assert_called_once()
        ui.page.wait_for_timeout.assert_called_once_with(250)

    def test_new_chat_timeout_is_bounded_and_never_reclicks(self):
        ui, _, _, action = self.fresh_fixture()
        action.click.side_effect = lambda **kw: setattr(ui.page, "url", "https://chatgpt.com/c/old")
        with patch("worker.time.monotonic", side_effect=[0, 0, 10]), patch.object(Journal, "reserve") as reserve:
            with self.assertRaisesRegex(Stopped, "NEW_CHAT_NOT_CONFIRMED"):
                ui.new_chat()
            reserve.assert_not_called()
        action.click.assert_called_once()
        ui.page.wait_for_timeout.assert_called_once_with(250)

    def test_new_chat_login_or_temporary_transition_stops_immediately(self):
        for key, code in ((("button", "Log in"), "NEEDS_OWNER_LOGIN"),
                          (("heading", "Temporary chat"), "TEMPORARY_CHAT_REJECTED")):
            ui, controls, _, action = self.fresh_fixture()
            action.click.side_effect = lambda **kw: controls.update({key: self.locator()})
            with patch.object(Journal, "reserve") as reserve:
                with self.assertRaisesRegex(Stopped, code):
                    ui.new_chat()
                reserve.assert_not_called()
            action.click.assert_called_once()
            ui.page.wait_for_timeout.assert_not_called()

    def test_new_chat_click_exception_is_never_replayed(self):
        ui, _, _, action = self.fresh_fixture()
        action.click.side_effect = RuntimeError("uncertain click")
        with patch.object(Journal, "reserve") as reserve:
            with self.assertRaises(RuntimeError):
                ui.new_chat()
            reserve.assert_not_called()
        action.click.assert_called_once()
        ui.page.wait_for_timeout.assert_not_called()

    def test_current_authenticated_semantic_controls(self):
        ui, _ = self.normal_ui()
        self.assertEqual(ui.session(), "AUTHENTICATED")
        self.assertFalse(ui.normal_mode())
        ui.send_button()
        ui.page.get_by_role.assert_any_call("button", name="Send", exact=True)

    def test_duplicate_temporary_controls_always_rejected(self):
        for role, name in (("button", "Turn off temporary chat"), ("heading", "Temporary chat")):
            ui, controls = self.normal_ui()
            controls[(role, name)] = self.locator(2)
            controls.pop(("textbox", "Ask ChatGPT"))
            with self.assertRaisesRegex(Stopped, "TEMPORARY_CHAT_REJECTED"):
                ui.authenticated()
            with self.assertRaisesRegex(Stopped, "TEMPORARY_CHAT_REJECTED"):
                ui.normal_mode()

    def test_temporary_menu_entry_is_not_active_temporary_mode(self):
        ui, controls = self.normal_ui()
        controls[("button", "Temporary chat")] = self.locator()
        self.assertFalse(ui.normal_mode())

    def test_missing_normal_composer_fails_closed(self):
        ui, controls = self.normal_ui()
        controls.pop(("textbox", "Ask ChatGPT"))
        self.assertEqual(ui.session(), "UNKNOWN_SAFE_STOP")
        with self.assertRaisesRegex(Stopped, "NORMAL_CHAT_UNVERIFIED"):
            ui.normal_mode()

    def test_duplicate_login_controls_are_not_ignored(self):
        ui, controls = self.normal_ui()
        controls[("button", "Log in")] = self.locator(2)
        self.assertEqual(ui.session(), "NEEDS_OWNER_LOGIN")

    def test_messages_are_scoped_to_main(self):
        page = Mock()
        main = self.locator()
        main.locator.return_value = self.locator(0)
        page.get_by_role.return_value = main
        ui = WebUI(page)
        ui.messages("assistant")
        page.get_by_role.assert_called_once_with("main")
        main.locator.assert_any_call('[data-message-author-role="assistant"]')

    def test_modern_messages_use_observed_content_attributes(self):
        page = Mock()
        main = self.locator()
        main.locator.return_value = self.locator(2)
        page.get_by_role.return_value = main
        ui = WebUI(page)
        ui.messages("assistant")
        main.locator.assert_called_with('[data-markdown-text-style="assistant-message"]')
        ui.messages("user")
        main.locator.assert_called_with('[data-user-message-bubble="true"]')

    def history_fixture(self, count=1, menu_count=1):
        ui, controls = self.normal_ui()
        ui.page.url = "https://chatgpt.com/c/one"
        navigation = self.locator()
        controls[("navigation", None)] = navigation
        ui.page.locator.return_value = navigation
        row = self.locator(count)
        row.get_attribute.return_value = "MG Portal - Task one"
        navigation.locator.return_value = row
        menu = self.locator(menu_count)
        row.get_by_role.return_value = menu
        return ui, navigation, row, menu

    def test_history_div_current_row_without_anchors(self):
        ui, navigation, row, menu = self.history_fixture()
        self.assertEqual(ui.history_row(ui.page.url), (row, menu))
        ui.page.locator.assert_called_once_with("#app-shell-sidebar:visible")
        selector = navigation.locator.call_args.args[0]
        self.assertNotIn("href", selector)
        self.assertNotIn("class", selector)
        for branch in selector.split(", "):
            self.assertTrue(branch.startswith('div[role="button"][aria-label]'))
            self.assertTrue('aria-current=' in branch or 'aria-selected=' in branch)
        row.get_by_role.assert_called_once_with("button", name="Chat actions", exact=True)

    def test_title_row_does_not_require_navigation_ancestry(self):
        ui, _, row, menu = self.history_fixture()
        original = ui.page.get_by_role.side_effect
        ui.page.get_by_role.side_effect = lambda role, **kw: self.locator(0) if role == "navigation" else original(role, **kw)
        self.assertEqual(ui.history_row(ui.page.url), (row, menu))

    def test_ambiguous_sidebar_cannot_rename(self):
        ui, sidebar, _, menu = self.history_fixture()
        sidebar.count.return_value = 2
        with self.assertRaisesRegex(Stopped, "TITLE_UI_UNAVAILABLE"):
            ui.rename(ui.page.url, "title")
        menu.click.assert_not_called()

    def test_sidebar_expansion_uses_unique_structural_trigger_once(self):
        ui, sidebar, _, _ = self.history_fixture()
        trigger = self.locator()
        sidebar.locator.return_value = trigger
        trigger.get_attribute.side_effect = ["false", "true"]
        ui.prepare_sidebar(ui.page.url)
        sidebar.locator.assert_called_once_with(
            'button[data-app-shell-sidebar-trigger="true"][aria-controls="app-shell-sidebar"]:visible')
        trigger.click.assert_called_once_with(timeout=5000)

    def test_sidebar_ambiguous_trigger_cannot_click(self):
        ui, sidebar, _, _ = self.history_fixture()
        trigger = self.locator(2)
        sidebar.locator.return_value = trigger
        with self.assertRaisesRegex(Stopped, "TITLE_UI_UNAVAILABLE"):
            ui.prepare_sidebar(ui.page.url)
        trigger.click.assert_not_called()

    def test_sidebar_expansion_timeout_does_not_reclick(self):
        ui, sidebar, _, _ = self.history_fixture()
        trigger = self.locator()
        trigger.get_attribute.return_value = "false"
        sidebar.locator.return_value = trigger
        with patch("worker.time.monotonic", side_effect=[0, 5]):
            with self.assertRaisesRegex(Stopped, "TITLE_UI_UNAVAILABLE"):
                ui.prepare_sidebar(ui.page.url)
        trigger.click.assert_called_once()

    def test_missing_or_ambiguous_current_row_stops_before_click(self):
        for count in (0, 2, 10):
            ui, _, row, menu = self.history_fixture(count=count)
            with self.assertRaisesRegex(Stopped, "TITLE_UI_UNAVAILABLE"):
                ui.rename(ui.page.url, "title")
            row.hover.assert_not_called()
            menu.click.assert_not_called()

    def test_ambiguous_actions_in_current_row_stop_before_click(self):
        ui, _, row, menu = self.history_fixture(menu_count=2)
        with self.assertRaisesRegex(Stopped, "TITLE_UI_UNAVAILABLE"):
            ui.rename(ui.page.url, "title")
        menu.click.assert_not_called()

    def test_only_current_rows_actions_clicked_among_multiple_actions(self):
        ui, _, row, menu = self.history_fixture()
        other_actions = self.locator(9)
        original = ui.page.get_by_role.side_effect
        ui.page.get_by_role.side_effect = lambda role, name=None, **kw: (
            other_actions if name == "Chat actions" else original(role, name, **kw))
        # Missing Rename menu stops after the one safely scoped actions click.
        with self.assertRaisesRegex(Stopped, "TITLE_UI_UNAVAILABLE"):
            ui.rename(ui.page.url, "title")
        menu.click.assert_called_once()
        other_actions.click.assert_not_called()

    def test_title_verified_from_current_row_label_without_href(self):
        ui, _, _, menu = self.history_fixture()
        ui.verify_title(ui.page.url, "MG Portal - Task one")
        menu.click.assert_not_called()

    def test_exact_url_continuity_needs_no_sidebar(self):
        ui, _ = self.normal_ui()
        ui.page.url = "https://chatgpt.com/c/one"
        ui.same_chat(ui.page.url)
        with self.assertRaisesRegex(Stopped, "CONTINUITY_MISMATCH"):
            ui.same_chat("https://chatgpt.com/c/two")
        ui.page.locator.assert_not_called()

    def test_reload_title_verification_requires_same_normal_conversation(self):
        ui, _, _, _ = self.history_fixture()
        url = ui.page.url
        with patch.object(ui, "wait_ready"):
            ui.reload()
        ui.verify_title(url, "MG Portal - Task one")
        ui.page.url = "https://chatgpt.com/c/other"
        with self.assertRaisesRegex(Stopped, "CONTINUITY_MISMATCH"):
            ui.verify_title(url, "MG Portal - Task one")

    def test_changed_url_blocks_title_and_rename_before_click(self):
        ui, _, _, menu = self.history_fixture()
        for operation in (ui.verify_title, ui.rename):
            with self.assertRaisesRegex(Stopped, "CONTINUITY_MISMATCH"):
                operation("https://chatgpt.com/c/two", "MG Portal - Task one")
        menu.click.assert_not_called()

    def send_fixture(self):
        ui = Mock()
        ui.page.url = "https://chatgpt.com/c/one"
        ui.composer.return_value = self.locator()
        ui.composer.return_value.get_attribute.return_value = "true"
        button = self.locator()
        button.is_enabled.return_value = True
        button.get_attribute.return_value = "submit"
        ui.send_button.return_value = button
        ui.messages.return_value.count.return_value = 0
        journal = Mock()
        journal.get.return_value = {"conversation_url": "https://chatgpt.com/c/one", "state": "READY"}
        return ui, journal, button

    def test_send_reserves_once_before_click_and_never_retries_click(self):
        ui, journal, button = self.send_fixture()
        def click(**kwargs):
            journal.reserve.assert_called_once_with("one")
            raise RuntimeError("synthetic click uncertainty")
        button.click.side_effect = click
        with self.assertRaises(RuntimeError):
            send_checked(ui, journal, "one", "synthetic")
        button.click.assert_called_once_with(timeout=5000)

    def test_disabled_duplicate_hidden_or_non_submit_send_cannot_reserve(self):
        for attr, value in (("is_enabled", False), ("count", 2), ("is_visible", False), ("get_attribute", "button")):
            ui, journal, button = self.send_fixture()
            getattr(button, attr).return_value = value
            with self.assertRaisesRegex(Stopped, "UI_OR_CHALLENGE_BLOCKED"):
                send_checked(ui, journal, "one", "synthetic")
            journal.reserve.assert_not_called()
            button.click.assert_not_called()

    def test_missing_editable_composer_cannot_reserve(self):
        ui, journal, button = self.send_fixture()
        ui.composer.return_value.get_attribute.return_value = "false"
        with self.assertRaisesRegex(Stopped, "UI_OR_CHALLENGE_BLOCKED"):
            send_checked(ui, journal, "one", "synthetic")
        journal.reserve.assert_not_called()
        button.click.assert_not_called()

    def test_completion_uses_idle_composer_and_message_without_copy_control(self):
        page = Mock()
        page.get_by_role.return_value = self.locator(0)
        page.locator.return_value = self.locator(0)
        ui = WebUI(page)
        messages = self.locator()
        messages.last = self.locator(text="NONCE_STORED")
        composer = self.locator()
        composer.get_attribute.return_value = "true"
        with patch.object(ui, "composer", return_value=composer):
            self.assertTrue(ui.response_complete(messages))
            composer.inner_text.return_value = "draft"
            self.assertFalse(ui.response_complete(messages))
            composer.inner_text.return_value = ""
            page.get_by_role.return_value = self.locator(2)
            self.assertFalse(ui.response_complete(messages))

    def test_latest_answer_requires_visible_assistant(self):
        ui = WebUI(Mock())
        messages = self.locator(0)
        with patch.object(ui, "messages", return_value=messages):
            with self.assertRaisesRegex(Stopped, "RESPONSE_NOT_PERSISTED"):
                ui.latest_answer()


if __name__ == "__main__":
    unittest.main()
