import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from worker import Journal, Stopped, classify_session, owner_login, recover_owner_auth, run, send


class AuthWaitTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).parent / ".test-runtime"
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name)
        (self.root / "state").mkdir()
        (self.root / "runtime").mkdir()
        self.path = self.root / "state" / "task-conversations.sqlite"
        self.journal = Journal(self.path)
        self.journal.create("one")
        self.args = argparse.Namespace(command="certify", task="one", approve_two_synthetic_messages=True)

    def tearDown(self):
        self.journal.db.close()
        self.temp.cleanup()

    def first_turn(self):
        self.journal.reserve("one")
        self.journal.complete("one", "https://chatgpt.com/c/one", "NONCE_STORED")
        self.journal.title_verified("one", "MG Portal - Task one")

    def test_expired_session_never_dispatches_or_uses_external_fallback(self):
        self.first_turn()
        ui = Mock()
        ui.authenticated.side_effect = Stopped("NEEDS_OWNER_LOGIN")
        with patch("worker.subprocess.run", side_effect=AssertionError("no external process allowed")):
            with self.assertRaisesRegex(Stopped, "NEEDS_OWNER_LOGIN"):
                send(ui, self.journal, "one", "synthetic")
        self.assertEqual(ui.mock_calls, [unittest.mock.call.authenticated()])
        status = self.journal.request_status("one")
        self.assertEqual(status["state"], "NEEDS_OWNER_LOGIN")
        self.assertEqual(status["conversation_url"], "https://chatgpt.com/c/one")
        self.assertEqual(status["turns"], 1)
        self.assertEqual(status["request_state"], "WAITING_OWNER_LOGIN")
        self.assertFalse(status["automatic_fallback"])

    def test_certify_missing_marker_persists_request_before_return(self):
        with patch("worker.owner_boundary", return_value=self.root), patch("worker.browser") as browser:
            result = run(self.args)
        browser.assert_not_called()
        self.assertEqual(result["state"], "NEEDS_OWNER_LOGIN")
        self.assertEqual(result["portal_task_id"], "one")
        self.assertEqual(result["turns"], 0)
        self.assertEqual(result["notification"]["message"], "Deep Chat session expired. Owner login required.")

    def test_certify_ui_expiry_persists_existing_mapping(self):
        self.first_turn()
        (self.root / "runtime" / "owner-ready").touch()
        with patch("worker.owner_boundary", return_value=self.root), patch("worker.browser") as browser, \
                patch("worker.send") as dispatch:
            ui = browser.return_value.__enter__.return_value
            ui.same_chat.side_effect = Stopped("NEEDS_OWNER_LOGIN")
            result = run(self.args)
        dispatch.assert_not_called()
        self.assertEqual(result["state"], "NEEDS_OWNER_LOGIN")
        self.assertEqual(result["conversation_url"], "https://chatgpt.com/c/one")

    def test_auth_wait_survives_database_reopen(self):
        self.first_turn()
        self.journal.record_stop("one", "NEEDS_OWNER_LOGIN")
        reopened = Journal(self.path)
        try:
            result = reopened.request_status("one")
            self.assertEqual(result["waiting_reason"], "NEEDS_OWNER_LOGIN")
            self.assertEqual(result["request_kind"], "CERTIFY_TWO_PUBLIC_MESSAGES")
            self.assertEqual(result["execution_state"], "READY")
        finally:
            reopened.db.close()

    def test_browser_cleanup_does_not_hide_auth_wait(self):
        self.first_turn()
        (self.root / "runtime" / "owner-ready").touch()
        with patch("worker.owner_boundary", return_value=self.root), patch("worker.browser") as browser:
            browser.return_value.__enter__.return_value.same_chat.side_effect = Stopped("NEEDS_OWNER_LOGIN")
            browser.return_value.__exit__.side_effect = RuntimeError("synthetic diagnostic")
            result = run(self.args)
        self.assertEqual(result["state"], "NEEDS_OWNER_LOGIN")
        self.assertEqual(result["turns"], 1)

    def test_auth_loss_after_dispatch_preserves_ambiguity(self):
        self.first_turn()
        ui = Mock()
        ui.authenticated.side_effect = [None, None, Stopped("NEEDS_OWNER_LOGIN")]
        ui.wait_answer.side_effect = Stopped("NEEDS_OWNER_LOGIN")
        ui.composer.return_value.count.return_value = 1
        ui.composer.return_value.is_visible.return_value = True
        ui.composer.return_value.get_attribute.return_value = "true"
        ui.messages.return_value.count.return_value = 1
        button = ui.send_button.return_value
        button.get_attribute.return_value = "submit"
        button.count.return_value = 1
        button.is_visible.return_value = True
        button.is_enabled.return_value = True
        with self.assertRaisesRegex(Stopped, "NEEDS_OWNER_LOGIN"):
            send(ui, self.journal, "one", "synthetic")
        button.click.assert_called_once()
        self.assertEqual(self.journal.get("one")["state"], "AMBIGUOUS")
        recover_owner_auth(self.root)
        with self.assertRaisesRegex(Stopped, "DISPATCH_BLOCKED"):
            self.journal.reserve("one")

    def test_successful_owner_login_clears_wait_without_dispatch(self):
        self.first_turn()
        self.journal.record_stop("one", "NEEDS_OWNER_LOGIN")
        before = dict(self.journal.get("one"))
        with patch("worker.browser"), patch("builtins.input", side_effect=["", "PLUS"]), \
                patch("worker.send") as dispatch:
            result = owner_login(self.root, self.root / "runtime" / "owner-ready")
        dispatch.assert_not_called()
        self.assertEqual(result["state"], "AUTHENTICATED")
        after = self.journal.get("one")
        for field in ("id", "nonce", "conversation_url", "turns", "state", "latest_answer", "title", "certification_status"):
            self.assertEqual(after[field], before[field])
        status = self.journal.request_status("one")
        self.assertTrue(status["resumable"])
        self.assertIsNone(status["waiting_reason"])
        self.assertIsNone(status["notification"])
        self.journal.reserve("one")
        self.assertEqual(self.journal.get("one")["turns"], 2)

    def test_failed_owner_login_cannot_clear_wait(self):
        self.journal.record_stop("one", "NEEDS_OWNER_LOGIN")
        with patch("worker.browser") as browser, patch("builtins.input", return_value=""):
            browser.return_value.__enter__.return_value.authenticated.side_effect = Stopped("NEEDS_OWNER_LOGIN")
            with self.assertRaises(Stopped):
                owner_login(self.root, self.root / "runtime" / "owner-ready")
        self.assertEqual(self.journal.request_status("one")["state"], "NEEDS_OWNER_LOGIN")

    def test_ambiguous_after_login_remains_non_replayable(self):
        self.first_turn()
        self.journal.reserve("one")
        self.journal.record_stop("one", "NEEDS_OWNER_LOGIN")
        recover_owner_auth(self.root)
        status = self.journal.request_status("one")
        self.assertEqual(status["state"], "AMBIGUOUS")
        self.assertEqual(status["turns"], 2)
        self.assertEqual(status["conversation_url"], "https://chatgpt.com/c/one")
        self.assertFalse(status["resumable"])
        with self.assertRaisesRegex(Stopped, "DISPATCH_BLOCKED"):
            self.journal.reserve("one")

    def test_recovery_does_not_reset_global_budget(self):
        self.journal.reserve("one")
        self.journal.create("two")
        self.journal.reserve("two")
        self.journal.record_stop("one", "NEEDS_OWNER_LOGIN")
        recover_owner_auth(self.root)
        self.journal.create("three")
        with self.assertRaisesRegex(Stopped, "DISPATCH_BLOCKED"):
            self.journal.reserve("three")

    def test_challenge_is_not_auth_expiry(self):
        ui = Mock()
        ui.authenticated.side_effect = Stopped("UI_OR_CHALLENGE_BLOCKED")
        with self.assertRaisesRegex(Stopped, "UI_OR_CHALLENGE_BLOCKED"):
            send(ui, self.journal, "one", "synthetic")
        before = dict(self.journal.get("one"))
        recover_owner_auth(self.root)
        self.assertEqual(dict(self.journal.get("one")), before)
        self.assertEqual(self.journal.request_status("one")["state"], "UI_OR_CHALLENGE_BLOCKED")

    def test_failed_is_distinct_and_login_does_not_clear_it(self):
        self.journal.record_stop("one", "FAILED")
        recover_owner_auth(self.root)
        self.assertEqual(self.journal.request_status("one")["state"], "FAILED")

    def test_auth_wait_on_existing_failure_preserves_independent_block(self):
        for code in ("FAILED", "UI_OR_CHALLENGE_BLOCKED"):
            self.journal.record_stop("one", code)
            self.journal.record_stop("one", "NEEDS_OWNER_LOGIN")
            self.assertEqual(self.journal.request_status("one")["state"], "NEEDS_OWNER_LOGIN")
            recover_owner_auth(self.root)
            self.assertEqual(self.journal.request_status("one")["state"], code)
            self.assertEqual(self.journal.get("one")["last_error"], code)
            self.assertFalse(self.journal.request_status("one")["resumable"])

    def test_visible_expiry_classification_and_challenge_priority(self):
        self.assertEqual(classify_session("https://chatgpt.com/", auth_invalid=True), "NEEDS_OWNER_LOGIN")
        self.assertEqual(classify_session("https://chatgpt.com/auth/error"), "NEEDS_OWNER_LOGIN")
        self.assertEqual(classify_session("https://chatgpt.com/", auth_invalid=True, challenge=True), "UI_OR_CHALLENGE_BLOCKED")

    def test_task_status_reads_durable_contract_without_browser(self):
        self.journal.record_stop("one", "NEEDS_OWNER_LOGIN")
        args = argparse.Namespace(command="task-status", task="one")
        with patch("worker.owner_boundary", return_value=self.root), patch("worker.browser") as browser:
            result = run(args)
        browser.assert_not_called()
        self.assertEqual(result["state"], "NEEDS_OWNER_LOGIN")

    def test_session_status_expiry_marks_pending_request(self):
        self.first_turn()
        with patch("worker.owner_boundary", return_value=self.root), patch("worker.browser") as browser:
            browser.return_value.__enter__.return_value.session.return_value = "NEEDS_OWNER_LOGIN"
            result = run(argparse.Namespace(command="status"))
        self.assertEqual(result["state"], "NEEDS_OWNER_LOGIN")
        self.assertEqual(self.journal.request_status("one")["request_state"], "WAITING_OWNER_LOGIN")
        self.assertEqual(self.journal.get("one")["conversation_url"], "https://chatgpt.com/c/one")


if __name__ == "__main__":
    unittest.main()
