import argparse
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from worker import HistoryUnavailable, history_candidates
from worker import Journal, Stopped, WebUI, first_prompt, run, send_checked


NONCE = "MG-SYNTHETIC-0123456789abcdef"
URL = "https://chatgpt.com/c/one"


class HistoryTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).parent / ".test-runtime"
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "runtime").mkdir()
        self.path = self.root / "profile" / "Default" / "History"
        self.path.parent.mkdir(parents=True)
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.executescript("CREATE TABLE urls(id INTEGER PRIMARY KEY,url TEXT,title TEXT);"
                             "CREATE TABLE visits(url INTEGER,visit_time INTEGER);")
        self.entry(1, "https://chatgpt.com/c/local-chatgpt%3Aone", first_prompt(NONCE), 500_000_000)
        self.entry(2, URL, "Nonce storage request", 501_000_000)

    def entry(self, key, url, title, stamp):
        self.db.execute("INSERT INTO urls VALUES(?,?,?)", (key, url, title))
        self.db.execute("INSERT INTO visits VALUES(?,?)", (key, stamp))
        self.db.commit()

    def test_nonce_correlates_nearby_canonical_only_without_mutation(self):
        self.entry(3, "https://chatgpt.com/c/old", "Old", 1)
        self.entry(4, "https://evil.invalid/c/one", "Unrelated", 501_000_000)
        self.entry(5, "https://chatgpt.com/c/one?x=1", "Query", 501_000_000)
        before = hashlib.sha256(self.path.read_bytes()).digest()
        self.assertEqual(history_candidates(self.root, NONCE), [URL])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), before)
        self.assertEqual(list((self.root / "runtime").iterdir()), [])

    def test_wal_only_committed_entry_is_in_snapshot(self):
        self.db.execute("PRAGMA journal_mode=WAL")
        self.entry(3, "https://chatgpt.com/c/two", "Nearby", 502_000_000)
        self.assertTrue(Path(str(self.path) + "-wal").exists())
        self.assertEqual(history_candidates(self.root, NONCE), [URL, "https://chatgpt.com/c/two"])

    def test_locked_database_is_read_from_copy(self):
        self.db.execute("BEGIN EXCLUSIVE")
        self.assertEqual(history_candidates(self.root, NONCE), [URL])
        self.db.rollback()

    def test_changed_snapshot_fails_closed(self):
        with patch("worker._history_signature", side_effect=[[(1, 1), None, None], [(2, 2), None, None]]):
            with self.assertRaisesRegex(HistoryUnavailable, "RECOVERY_HISTORY_BUSY"):
                history_candidates(self.root, NONCE)

    def test_hot_rollback_journal_is_never_recovered(self):
        Path(str(self.path) + "-journal").write_bytes(b"synthetic")
        with self.assertRaisesRegex(HistoryUnavailable, "RECOVERY_HISTORY_BUSY"):
            history_candidates(self.root, NONCE)

    def test_missing_nonce_never_uses_recent_title_alone(self):
        with self.assertRaisesRegex(HistoryUnavailable, "RECOVERY_NONCE_HISTORY_NOT_FOUND"):
            history_candidates(self.root, "MG-SYNTHETIC-1111111111111111")

    def test_candidate_overflow_is_not_silently_truncated(self):
        for i in range(3, 24):
            self.entry(i, f"https://chatgpt.com/c/{i}", "Nearby", 501_000_000)
        with self.assertRaisesRegex(HistoryUnavailable, "RECOVERY_HISTORY_AMBIGUOUS"):
            history_candidates(self.root, NONCE)


class RecoveryUITests(unittest.TestCase):
    def ui(self):
        ui = WebUI(Mock())
        ui.page.url = URL
        for method in ("navigate", "same_chat", "authenticated", "normal_mode", "reload"):
            setattr(ui, method, Mock())
        ui.messages = Mock()
        ui.messages.return_value.count.return_value = 2
        ui.first_turn_evidence = Mock(return_value=True)
        ui.wait_answer = Mock(return_value=(URL, "NONCE_STORED"))
        return ui

    def test_recovery_requires_unique_match_and_reload_without_dispatch(self):
        ui = self.ui()
        self.assertEqual(ui.recover_ambiguous_first_turn(NONCE, [URL]), (URL, "NONCE_STORED"))
        ui.reload.assert_called_once()
        self.assertEqual(ui.first_turn_evidence.call_count, 3)
        ui.page.get_by_role.assert_not_called()

    def test_two_matching_conversations_fail_closed(self):
        ui = self.ui()
        with self.assertRaisesRegex(Stopped, "RECOVERY_AMBIGUOUS_MATCHES"):
            ui.recover_ambiguous_first_turn(NONCE, [URL, "https://chatgpt.com/c/two"])

    def test_title_time_without_exact_nonce_dom_never_binds(self):
        ui = self.ui()
        ui.first_turn_evidence.return_value = False
        with self.assertRaisesRegex(Stopped, "RECOVERY_NONCE_CONVERSATION_NOT_FOUND"):
            ui.recover_ambiguous_first_turn(NONCE, [URL])
        ui.wait_answer.assert_not_called()

    def test_reload_evidence_loss_fails(self):
        ui = self.ui()
        ui.first_turn_evidence.side_effect = [True, False]
        ui.wait_first_turn_evidence = Mock(return_value=False)
        with self.assertRaisesRegex(Stopped, "RECOVERY_EVIDENCE_NOT_PERSISTED"):
            ui.recover_ambiguous_first_turn(NONCE, [URL])

    def test_login_temp_and_url_change_abort_recovery(self):
        for code in ("NEEDS_OWNER_LOGIN", "TEMPORARY_CHAT_REJECTED", "CONTINUITY_MISMATCH"):
            ui = self.ui()
            ui.same_chat.side_effect = Stopped(code)
            with self.assertRaisesRegex(Stopped, code):
                ui.recover_ambiguous_first_turn(NONCE, [URL])

    def test_exact_original_user_and_assistant_order(self):
        ui = WebUI(Mock())
        ui.same_chat = Mock()
        messages = Mock()
        messages.count.return_value = 2
        user, assistant = Mock(), Mock()
        user.is_visible.return_value = assistant.is_visible.return_value = True
        user.get_attribute.side_effect = lambda name: "true" if name == "data-user-message-bubble" else None
        assistant.get_attribute.side_effect = lambda name: "assistant-message" if name == "data-markdown-text-style" else None
        user.inner_text.return_value = first_prompt(NONCE)
        assistant.inner_text.return_value = "NONCE_STORED"
        messages.nth.side_effect = [user, assistant] * 4
        ui.messages = Mock(return_value=messages)
        self.assertTrue(ui.first_turn_evidence(URL, NONCE))
        user.inner_text.return_value += " additional text"
        self.assertFalse(ui.first_turn_evidence(URL, NONCE))
        user.inner_text.return_value = first_prompt(NONCE)
        assistant.inner_text.return_value = "OTHER"
        self.assertFalse(ui.first_turn_evidence(URL, NONCE))
        messages.count.return_value = 3
        self.assertFalse(ui.first_turn_evidence(URL, NONCE))

    def test_wait_answer_requires_stability_and_expected_text(self):
        ui = self.ui()
        ui.wait_answer = WebUI.wait_answer.__get__(ui)
        ui.messages.return_value.count.return_value = 1
        ui.latest_answer = Mock(side_effect=["NONCE", "NONCE_STORED"] + ["NONCE_STORED"] * 5)
        ui.response_complete = Mock(return_value=True)
        with patch("worker.time.monotonic", side_effect=range(8)):
            self.assertEqual(ui.wait_answer(0, URL, expected="NONCE_STORED"), (URL, "NONCE_STORED"))
        self.assertEqual(ui.page.wait_for_timeout.call_count, 7)

    def test_wait_answer_timeout_login_and_continuity_stop(self):
        for code in ("NEEDS_OWNER_LOGIN", "TEMPORARY_CHAT_REJECTED", "CONTINUITY_MISMATCH"):
            ui = self.ui()
            ui.wait_answer = WebUI.wait_answer.__get__(ui)
            ui.same_chat.side_effect = Stopped(code)
            with self.assertRaisesRegex(Stopped, code):
                ui.wait_answer(0, URL)
        ui = self.ui()
        ui.wait_answer = WebUI.wait_answer.__get__(ui)
        with patch("worker.time.monotonic", side_effect=[0, 121]):
            with self.assertRaisesRegex(Stopped, "AMBIGUOUS"):
                ui.wait_answer(0, URL)


class RecoveryJournalTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).parent / ".test-runtime"
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "state").mkdir()
        (self.root / "runtime").mkdir()
        (self.root / "runtime" / "owner-ready").touch()
        self.journal = Journal(self.root / "state" / "task-conversations.sqlite")
        self.addCleanup(self.journal.db.close)
        self.journal.create("existing")
        self.journal.reserve("existing")

    def execute(self, command, ui):
        args = argparse.Namespace(command=command, task="existing", approve_two_synthetic_messages=True)
        with patch("worker.owner_boundary", return_value=self.root), \
                patch("worker.history_candidates", return_value=[URL]), patch("worker.browser") as browser:
            browser.return_value.__enter__.return_value = ui
            return run(args)

    def test_recovery_preserves_consumed_turn_without_send_or_reservation(self):
        ui = Mock()
        ui.recover_ambiguous_first_turn.return_value = URL, "NONCE_STORED"
        with patch("worker.send") as dispatch, patch.object(Journal, "reserve") as reserve:
            result = self.execute("recover-first-turn", ui)
        dispatch.assert_not_called()
        reserve.assert_not_called()
        self.assertEqual(result["turns"], 1)
        self.assertEqual(result["execution_state"], "READY")
        self.assertEqual(result["conversation_url"], URL)
        self.assertEqual(self.journal.get("existing")["latest_answer"], "NONCE_STORED")

    def test_failed_recovery_retains_ambiguity_and_budget(self):
        ui = Mock()
        ui.recover_ambiguous_first_turn.side_effect = Stopped("RECOVERY_AMBIGUOUS_MATCHES")
        with self.assertRaisesRegex(Stopped, "RECOVERY_AMBIGUOUS_MATCHES"):
            self.execute("recover-first-turn", ui)
        row = self.journal.get("existing")
        self.assertEqual((row["state"], row["turns"], row["conversation_url"]), ("AMBIGUOUS", 1, None))

    def test_certification_sends_only_second_prompt_after_recovery(self):
        nonce = self.journal.get("existing")["nonce"]
        ui = Mock()
        ui.recover_ambiguous_first_turn.return_value = URL, "NONCE_STORED"
        ui.latest_answer.return_value = nonce
        def second_only(ui, journal, task, prompt):
            self.assertEqual(prompt, "What synthetic nonce did I ask you to remember? Reply with only that nonce.")
            self.assertEqual(journal.get(task)["turns"], 1)
            journal.reserve(task)
            journal.complete(task, URL, nonce)
        with patch("worker.send", side_effect=second_only) as dispatch:
            result = self.execute("certify", ui)
        dispatch.assert_called_once()
        ui.new_chat.assert_not_called()
        self.assertEqual(result["state"], "CERTIFIED_WITH_OWNER_PLUS_ATTESTATION")
        self.assertEqual(self.journal.get("existing")["turns"], 2)
        with self.assertRaisesRegex(Stopped, "DISPATCH_BLOCKED"):
            self.journal.reserve("existing")

    def test_ambiguous_send_cannot_even_fill_composer(self):
        ui = Mock()
        with self.assertRaisesRegex(Stopped, "DISPATCH_BLOCKED"):
            send_checked(ui, self.journal, "existing", first_prompt(NONCE))
        ui.composer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
