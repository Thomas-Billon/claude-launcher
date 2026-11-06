import json
import os
import sys
import time
from datetime import datetime
from unittest.mock import patch

from launcher import history, launcher_state, session_restore, sessions_state, worktrees
from launcher.accounts import Account
from launcher.paths import LAUNCHER_SCRIPT
from launcher.session_restore import (
    ACCOUNT_NOT_FOUND,
    FOLDER_NOT_FOUND,
    WORKTREE_NOT_FOUND,
    RejectedSession,
    RestorableSession,
)
from launcher.terminal_ui import YELLOW, HeaderLine
from tests.test_history import write_conversation
from tests.test_sessions_state import SessionsStateTestCase
from tests.test_worktrees import WorktreesTestCase


class SessionRestoreTestCase(WorktreesTestCase, SessionsStateTestCase):
    def setUp(self):
        WorktreesTestCase.setUp(self)
        SessionsStateTestCase.setUp(self)
        self.accounts_dir = self.root / "accounts"
        self.config_file = self.root / "config.json"

        for target, value in (
            ("launcher.accounts.ACCOUNTS_DIR", self.accounts_dir),
            ("launcher.launcher_state.STATE_FILE", self.root / "launcher_state.json"),
            ("launcher.session_restore.CONFIG_FILE", self.config_file),
        ):
            value_patch = patch(target, value)
            value_patch.start()
            self.addCleanup(value_patch.stop)

        self.account = Account("a1b2c3d4", self.accounts_dir / "a1b2c3d4", name="Perso")
        self.account.config_dir.mkdir(parents=True)
        launcher_state.save_name(self.account, "Perso")
        self.folder = self.root / "blog"
        self.folder.mkdir()

    def write_folder_conversation(self, session_id, age_seconds=60):
        write_conversation(history.get_history_dir(self.account.config_dir, self.folder), session_id, self.folder, age_seconds)

    def write_worktree_conversation(self, worktree, session_id):
        write_conversation(history.get_history_dir(self.account.config_dir, worktree.repo), session_id, worktree.path, 60)

    def entry_ids(self):
        return set(self.read_sessions())


class RestorableTest(SessionRestoreTestCase):
    def test_closed_folder_session_is_restorable(self):
        self.write_folder_conversation("session-1", age_seconds=60)
        self.write_entry("e1", "a1b2c3d4", self.folder, session_id="session-1")

        restorable, rejected = session_restore.find_restorable_sessions()

        self.assertEqual(len(restorable), 1)
        session = restorable[0]
        self.assertEqual(
            (session.entry_id, session.account.account_id, session.folder, session.worktree, session.session_id),
            ("e1", "a1b2c3d4", self.folder, None, "session-1"),
        )
        self.assertAlmostEqual(session.last_message_at.timestamp(), time.time() - 60, delta=5)
        self.assertEqual(session.label, "Perso · blog")
        self.assertEqual(rejected, [])

    def test_closed_worktree_session_is_restorable(self):
        worktree = worktrees.create_worktree(self.repo, "export-pdf", "dev")
        self.write_worktree_conversation(worktree, "session-1")
        self.write_entry("e1", "a1b2c3d4", self.repo, worktree=worktree.path, session_id="session-1")

        restorable, _ = session_restore.find_restorable_sessions()

        self.assertEqual(restorable[0].worktree, worktree)
        self.assertEqual(restorable[0].label, "Perso · repo · export-pdf")

    def test_most_recent_message_comes_first(self):
        self.write_folder_conversation("old", age_seconds=3600)
        self.write_folder_conversation("recent", age_seconds=60)
        self.write_entry("e-old", "a1b2c3d4", self.folder, session_id="old")
        self.write_entry("e-recent", "a1b2c3d4", self.folder, session_id="recent")

        restorable, _ = session_restore.find_restorable_sessions()

        self.assertEqual([session.entry_id for session in restorable], ["e-recent", "e-old"])

    def test_restorable_sessions_are_kept_until_picked(self):
        self.write_folder_conversation("session-1")
        self.write_entry("e1", "a1b2c3d4", self.folder, session_id="session-1")

        session_restore.find_restorable_sessions()

        self.assertEqual(self.entry_ids(), {"e1"})

    def test_running_session_is_neither_offered_nor_forgotten(self):
        self.write_folder_conversation("session-1")
        self.write_entry("e1", "a1b2c3d4", self.folder, session_id="session-1", is_running=True)
        self.write_entry("e2", "unknown", self.folder, session_id="session-1", is_running=True)

        restorable, rejected = session_restore.find_restorable_sessions()

        self.assertEqual((restorable, rejected), ([], []))
        self.assertEqual(self.entry_ids(), {"e1", "e2"})

    def test_no_entries(self):
        self.assertEqual(session_restore.find_restorable_sessions(), ([], []))


class RejectedTest(SessionRestoreTestCase):
    def assert_rejected(self, reason, label):
        restorable, rejected = session_restore.find_restorable_sessions()

        self.assertEqual(restorable, [])
        self.assertEqual(rejected, [RejectedSession(label, reason)])
        self.assertEqual(self.entry_ids(), set())

    def test_missing_account(self):
        self.write_folder_conversation("session-1")
        self.write_entry("e1", "e5f6a7b8", self.folder, session_id="session-1")

        self.assert_rejected(ACCOUNT_NOT_FOUND, "blog")

    def test_missing_folder(self):
        missing_folder = self.root / "deleted"
        self.write_entry("e1", "a1b2c3d4", missing_folder, session_id="session-1")

        self.assert_rejected(FOLDER_NOT_FOUND, "Perso · deleted")

    def test_missing_worktree(self):
        worktree = worktrees.create_worktree(self.repo, "export-pdf", "dev")
        self.write_worktree_conversation(worktree, "session-1")
        self.write_entry("e1", "a1b2c3d4", self.repo, worktree=worktree.path, session_id="session-1")
        worktrees.run_git(self.repo, "worktree", "remove", "--force", str(worktree.path))

        self.assert_rejected(WORKTREE_NOT_FOUND, "Perso · repo · export-pdf")

    def test_rejection_is_shown_in_yellow_with_its_reason(self):
        self.assertEqual(
            session_restore.rejection_header_line(RejectedSession("Perso · repo · export-pdf", WORKTREE_NOT_FOUND)),
            HeaderLine("Restore", "Perso · repo · export-pdf  (worktree not found)", YELLOW),
        )


class SilentlyForgottenTest(SessionRestoreTestCase):
    def test_session_closed_before_the_hook_ran(self):
        self.write_entry("e1", "a1b2c3d4", self.folder, session_id=None)

        self.assertEqual(session_restore.find_restorable_sessions(), ([], []))
        self.assertEqual(self.entry_ids(), set())

    def test_session_closed_before_any_message(self):
        self.write_entry("e1", "a1b2c3d4", self.folder, session_id="never-saved")

        self.assertEqual(session_restore.find_restorable_sessions(), ([], []))
        self.assertEqual(self.entry_ids(), set())


class RestoredTabTest(SessionRestoreTestCase):
    def test_session_claimed_by_the_first_tab_is_loaded(self):
        self.write_folder_conversation("session-1")
        self.write_entry("e1", "a1b2c3d4", self.folder, session_id="session-1", is_running=True)

        session = session_restore.load_restorable_session("e1")

        self.assertEqual((session.entry_id, session.session_id, session.folder), ("e1", "session-1", self.folder))

    def test_missing_entry_cannot_be_loaded(self):
        self.assertIsNone(session_restore.load_restorable_session("unknown"))

    def test_entry_whose_folder_is_gone_cannot_be_loaded(self):
        self.write_entry("e1", "a1b2c3d4", self.root / "deleted", session_id="session-1", is_running=True)

        self.assertIsNone(session_restore.load_restorable_session("e1"))


class TerminalWindowTest(SessionRestoreTestCase):
    def write_config(self, config):
        self.config_file.write_text(json.dumps(config), encoding="utf-8")

    def test_window_chosen_at_install(self):
        for window in ("claude-launcher", "new"):
            self.write_config({"skills_repo": None, "terminal_window": window})

            self.assertEqual(session_restore.load_terminal_window(), window)

    def test_install_older_than_the_window_mode_uses_the_current_window(self):
        self.write_config({"skills_repo": None})

        self.assertEqual(session_restore.load_terminal_window(), "0")

    def test_no_config_uses_the_current_window(self):
        self.assertEqual(session_restore.load_terminal_window(), "0")

    def test_windows_terminal_is_detected_from_its_session_variable(self):
        with patch.dict(os.environ, {"WT_SESSION": "5f2a"}):
            self.assertTrue(session_restore.is_windows_terminal())

        with patch.dict(os.environ):
            os.environ.pop("WT_SESSION", None)

            self.assertFalse(session_restore.is_windows_terminal())

    def test_restore_tab_command(self):
        self.assertEqual(
            session_restore.build_restore_tab_command("e1", "new"),
            ["wt", "-w", "new", "new-tab", "-p", "Claude Code", sys.executable, str(LAUNCHER_SCRIPT), "--restore-session", "e1"],
        )

    def test_each_session_opens_in_the_window_chosen_at_install(self):
        self.write_config({"terminal_window": "claude-launcher"})
        sessions = [
            RestorableSession(entry_id, self.account, self.folder, None, "session", datetime.now()) for entry_id in ("e2", "e3")
        ]

        with patch("launcher.session_restore.subprocess.Popen") as popen:
            session_restore.open_in_new_tabs(sessions)

        self.assertEqual(
            [call.args[0] for call in popen.call_args_list],
            [session_restore.build_restore_tab_command(entry_id, "claude-launcher") for entry_id in ("e2", "e3")],
        )
