import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import claude_launcher
from launcher import history
from launcher.accounts import Account
from launcher.folder_menu import CONTINUE_SESSION, NEW_SESSION, SESSION_MODES
from launcher.worktrees import Worktree
from tests.test_history import write_conversation

RESUME_SESSION = SESSION_MODES[2]


class LaunchTestCase(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name).resolve()
        self.account = Account("a1b2c3d4", self.root / "account", name="Tests")
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.worktree = Worktree("export-pdf", self.root / "worktrees" / "a1b2c3d4" / "export-pdf", self.repo, "dev")
        self.repo_history = history.get_history_dir(self.account.config_dir, self.repo)


class SessionArgumentsTest(LaunchTestCase):
    def test_main_folder_keeps_the_session_arguments(self):
        for session in SESSION_MODES:
            self.assertEqual(claude_launcher.build_session_arguments(self.account, session, None), list(session.claude_arguments))

    def test_worktree_keeps_new_and_resume_sessions(self):
        self.assertEqual(claude_launcher.build_session_arguments(self.account, NEW_SESSION, self.worktree), [])
        self.assertEqual(claude_launcher.build_session_arguments(self.account, RESUME_SESSION, self.worktree), ["--resume"])

    def test_worktree_continues_its_own_last_conversation(self):
        write_conversation(self.repo_history, "worktree-session", self.worktree.path, 200)
        write_conversation(self.repo_history, "main-session", self.repo, 100)

        self.assertEqual(
            claude_launcher.build_session_arguments(self.account, CONTINUE_SESSION, self.worktree),
            ["--resume", "worktree-session"],
        )

    def test_worktree_without_conversation_starts_a_new_one(self):
        write_conversation(self.repo_history, "main-session", self.repo, 100)

        self.assertEqual(claude_launcher.build_session_arguments(self.account, CONTINUE_SESSION, self.worktree), [])


class LaunchTest(LaunchTestCase):
    def launch(self, worktree):
        """Launches with Claude Code replaced by a stub, returns whether the worktree history was a junction when it started."""
        worktree_history = history.get_history_dir(self.account.config_dir, self.worktree.path)
        observed = {}

        def start_claude(*_, **__):
            observed["is_linked"] = os.path.isjunction(worktree_history)

            return MagicMock(returncode=0)

        subprocess_stub = MagicMock()
        subprocess_stub.run.side_effect = start_claude

        with (
            patch("claude_launcher.subprocess", subprocess_stub),
            patch("claude_launcher.os.chdir"),
            patch("claude_launcher.set_title"),
            patch("claude_launcher.accounts.prepare_account_dir", return_value=[]),
            patch("claude_launcher.accounts.build_launch_command", return_value=["claude"]),
            patch("builtins.print"),
        ):
            claude_launcher.launch_claude_code(self.account, self.repo, worktree, [])

        return observed["is_linked"]

    def test_worktree_history_is_linked_before_claude_code_starts(self):
        self.assertTrue(self.launch(self.worktree))
        self.assertTrue(self.repo_history.is_dir())

    def test_main_folder_launch_creates_no_link(self):
        self.assertFalse(self.launch(None))
