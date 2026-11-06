import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import claude_launcher
from launcher import processes, session_restore
from launcher.accounts import Account
from launcher.session_restore import RejectedSession, RestorableSession
from launcher.sessions_state import ENTRY_VARIABLE
from launcher.terminal_ui import GREEN, QUIT, HeaderLine
from tests.test_launch import LaunchTestCase
from tests.test_sessions_state import SessionsStateTestCase

LAUNCHER_LINE = HeaderLine("Launcher", "up to date", GREEN)


class RegisteredLaunchTest(LaunchTestCase, SessionsStateTestCase):
    def setUp(self):
        LaunchTestCase.setUp(self)
        SessionsStateTestCase.setUp(self)

    def launch(self, entry_id=None, claude_error=None):
        """Launches with Claude Code replaced by a stub. Returns its environment and the sessions it saw while running."""
        observed = {}

        def start_claude(*_, env, **__):
            observed["environment"] = env
            observed["sessions"] = self.read_sessions()

            if claude_error is not None:
                raise claude_error

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
            claude_launcher.launch_claude_code(self.account, self.repo, self.worktree, [], entry_id)

        return observed

    def test_running_session_is_registered(self):
        observed = self.launch()

        entry_id = observed["environment"][ENTRY_VARIABLE]
        entry = observed["sessions"][entry_id]
        self.assertEqual(
            (entry["account_id"], entry["folder"], entry["worktree"]),
            ("a1b2c3d4", str(self.repo), str(self.worktree.path)),
        )
        self.assertEqual(entry["launcher_pid"], os.getpid())

    def test_normal_exit_removes_the_entry(self):
        self.launch()

        self.assertEqual(self.read_sessions(), {})

    def test_ctrl_c_exit_removes_the_entry(self):
        with self.assertRaises(KeyboardInterrupt):
            self.launch(claude_error=KeyboardInterrupt())

        self.assertEqual(self.read_sessions(), {})

    def test_restored_session_keeps_its_entry(self):
        self.write_entry("e1", "a1b2c3d4", self.repo, session_id="session-1", is_running=True)

        observed = self.launch(entry_id="e1")

        self.assertEqual(observed["environment"][ENTRY_VARIABLE], "e1")
        self.assertEqual(set(observed["sessions"]), {"e1"})
        self.assertEqual(self.read_sessions(), {})


def make_restorable_session(entry_id, folder):
    account = Account("a1b2c3d4", folder / "account", name="Tests")

    return RestorableSession(entry_id, account, folder, None, f"session-{entry_id}", datetime(2026, 11, 5, 17, 35))


class RestoreTestCase(SessionsStateTestCase):
    def setUp(self):
        super().setUp()
        self.sessions = [make_restorable_session(entry_id, self.root) for entry_id in ("e1", "e2", "e3")]

        for session in self.sessions:
            self.write_entry(session.entry_id, "a1b2c3d4", self.root, session_id=session.session_id)


class RestoreSessionsTest(RestoreTestCase):
    def restore(self, is_windows_terminal):
        with (
            patch("claude_launcher.session_restore.is_windows_terminal", return_value=is_windows_terminal),
            patch("claude_launcher.session_restore.open_in_new_tabs") as open_in_new_tabs,
            patch("claude_launcher.launch_claude_code", return_value=0) as launch_claude_code,
            patch("claude_launcher.render_screen"),
        ):
            exit_code = claude_launcher.restore_sessions(self.sessions, ["--model", "opus"])

        return exit_code, launch_claude_code, open_in_new_tabs

    def test_current_tab_resumes_the_first_session(self):
        exit_code, launch_claude_code, _ = self.restore(is_windows_terminal=True)

        self.assertEqual(exit_code, 0)
        launch_claude_code.assert_called_once_with(
            self.sessions[0].account, self.root, None, ["--resume", "session-e1", "--model", "opus"], "e1"
        )

    def test_other_sessions_open_in_new_tabs(self):
        _, _, open_in_new_tabs = self.restore(is_windows_terminal=True)

        open_in_new_tabs.assert_called_once_with(self.sessions[1:])

    def test_restored_sessions_are_claimed_before_the_tabs_open(self):
        self.restore(is_windows_terminal=True)

        for entry in self.read_sessions().values():
            self.assertEqual(entry["launcher_started_at"], processes.read_start_time(os.getpid()))

    def test_without_windows_terminal_only_the_first_session_is_restored(self):
        _, launch_claude_code, open_in_new_tabs = self.restore(is_windows_terminal=False)

        open_in_new_tabs.assert_not_called()
        self.assertEqual(launch_claude_code.call_args.args[4], "e1")
        self.assertEqual(set(self.read_sessions()), {"e1"})


class OfferRestoreTest(RestoreTestCase):
    def offer(self, restorable, rejected, chosen):
        with (
            patch("claude_launcher.session_restore.find_restorable_sessions", return_value=(restorable, rejected)),
            patch("claude_launcher.prompt_for_restore", return_value=chosen) as prompt_for_restore,
        ):
            header_lines, outcome = claude_launcher.offer_restore([LAUNCHER_LINE])

        return header_lines, outcome, prompt_for_restore

    def test_no_restorable_session_skips_the_menu(self):
        header_lines, outcome, prompt_for_restore = self.offer([], [], None)

        prompt_for_restore.assert_not_called()
        self.assertEqual((header_lines, outcome), ([LAUNCHER_LINE], []))

    def test_rejected_sessions_are_shown_in_the_header(self):
        rejected = RejectedSession("Perso · blog", "folder not found")

        header_lines, _, _ = self.offer([], [rejected], None)

        self.assertEqual(header_lines, [LAUNCHER_LINE, session_restore.rejection_header_line(rejected)])

    def test_restorable_sessions_are_offered(self):
        _, outcome, prompt_for_restore = self.offer(self.sessions, [], self.sessions[:2])

        prompt_for_restore.assert_called_once_with([LAUNCHER_LINE], self.sessions)
        self.assertEqual(outcome, self.sessions[:2])

    def test_unchecked_sessions_are_forgotten(self):
        self.offer(self.sessions, [], [self.sessions[0], self.sessions[2]])

        self.assertEqual(set(self.read_sessions()), {"e1", "e3"})

    def test_new_session_forgets_every_closed_session(self):
        _, outcome, _ = self.offer(self.sessions, [], [])

        self.assertEqual(outcome, [])
        self.assertEqual(self.read_sessions(), {})

    def test_quit_forgets_nothing(self):
        _, outcome, _ = self.offer(self.sessions, [], QUIT)

        self.assertIs(outcome, QUIT)
        self.assertEqual(set(self.read_sessions()), {"e1", "e2", "e3"})


class RestoredTabTest(RestoreTestCase):
    def test_tab_resumes_its_session_without_any_menu(self):
        with (
            patch("claude_launcher.session_restore.load_restorable_session", return_value=self.sessions[1]),
            patch("claude_launcher.launch_claude_code", return_value=0) as launch_claude_code,
            patch("claude_launcher.render_screen"),
        ):
            exit_code = claude_launcher.restore_session_in_tab("e2", [])

        self.assertEqual(exit_code, 0)
        launch_claude_code.assert_called_once_with(self.sessions[1].account, self.root, None, ["--resume", "session-e2"], "e2")
        self.assertEqual(self.read_sessions()["e2"]["launcher_started_at"], processes.read_start_time(os.getpid()))

    def test_missing_session_fails_without_launching(self):
        with (
            patch("claude_launcher.session_restore.load_restorable_session", return_value=None),
            patch("claude_launcher.launch_claude_code") as launch_claude_code,
            patch("builtins.print"),
        ):
            exit_code = claude_launcher.restore_session_in_tab("e2", [])

        self.assertEqual(exit_code, 1)
        launch_claude_code.assert_not_called()
