import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from launcher import restore_menu
from launcher.accounts import Account
from launcher.keyboard import Key
from launcher.restore_menu import START_NEW_SESSION, RestoreMenu, restore_label
from launcher.session_restore import RestorableSession
from launcher.terminal_ui import QUIT
from launcher.worktrees import Worktree


def setUpModule():
    # INFO: A menu waiting for a key would hang the tests, any unexpected read fails them instead
    read_key_patch = patch("launcher.restore_menu.read_key", side_effect=AssertionError("Unexpected key read"))
    read_key_patch.start()
    unittest.addModuleCleanup(read_key_patch.stop)


def make_session(entry_id, folder_name, worktree_name=None):
    account = Account("a1b2c3d4", Path("C:/accounts/a1b2c3d4"), name="Perso")
    folder = Path("C:/Projets") / folder_name
    worktree = Worktree(worktree_name, Path("C:/worktrees") / worktree_name, folder, "dev") if worktree_name else None

    return RestorableSession(entry_id, account, folder, worktree, f"session-{entry_id}", datetime(2026, 11, 5, 17, 35))


class RestoreMenuTestCase(unittest.TestCase):
    def setUp(self):
        self.sessions = [make_session("e1", "shope", "export-pdf"), make_session("e2", "claude-launcher"), make_session("e3", "blog")]
        self.menu = RestoreMenu([], self.sessions)

    def open_session_list(self):
        self.menu.choice_selection.selected_index = 0
        self.assertIsNone(self.menu.handle_choice_key(Key.ENTER))

    def highlight(self, session):
        self.menu.session_selection.selected_index = self.menu.session_selection.items.index(session)


class ChoiceTest(RestoreMenuTestCase):
    def test_restore_label_counts_the_sessions(self):
        self.assertEqual(restore_label(1), "Restore 1 session")
        self.assertEqual(restore_label(3), "Restore 3 sessions")

    def test_choice_between_restore_and_new_session(self):
        selection = self.menu.choice_selection

        self.assertEqual([selection.label(item) for item in selection.items], ["Restore 3 sessions", START_NEW_SESSION])
        self.assertEqual(selection.selected_index, 0)
        self.assertIsNone(self.menu.session_selection)

    def test_new_session_restores_nothing(self):
        self.menu.choice_selection.selected_index = 1

        self.assertEqual(self.menu.handle_choice_key(Key.ENTER), [])

    def test_esc_quits(self):
        self.assertIs(self.menu.handle_choice_key(Key.ESC), QUIT)


class SessionListTest(RestoreMenuTestCase):
    def test_restore_opens_the_list_with_every_session_checked(self):
        self.open_session_list()
        selection = self.menu.session_selection

        self.assertEqual(selection.items, self.sessions)
        self.assertEqual(
            [selection.label(session) for session in self.sessions],
            ["[x] Perso · shope · export-pdf", "[x] Perso · claude-launcher", "[x] Perso · blog"],
        )

    def test_last_message_date_is_shown_in_gray(self):
        self.open_session_list()

        self.assertEqual(self.menu.session_selection.secondary_label(self.sessions[0]), "2026-11-05 17:35")

    def test_space_toggles_the_highlighted_session(self):
        self.open_session_list()
        self.highlight(self.sessions[1])

        self.assertIsNone(self.menu.handle_session_list_key(Key.SPACE))
        self.assertEqual(self.menu.session_selection.label(self.sessions[1]), "[ ] Perso · claude-launcher")
        self.assertEqual(self.menu.session_selection.label(self.sessions[0]), "[x] Perso · shope · export-pdf")

        self.menu.handle_session_list_key(Key.SPACE)
        self.assertEqual(self.menu.session_selection.label(self.sessions[1]), "[x] Perso · claude-launcher")

    def test_enter_restores_the_checked_sessions_in_list_order(self):
        self.open_session_list()
        self.highlight(self.sessions[1])
        self.menu.handle_session_list_key(Key.SPACE)

        self.assertEqual(self.menu.handle_session_list_key(Key.ENTER), [self.sessions[0], self.sessions[2]])

    def test_enter_with_nothing_checked_restores_nothing(self):
        self.open_session_list()

        for session in self.sessions:
            self.highlight(session)
            self.menu.handle_session_list_key(Key.SPACE)

        self.assertEqual(self.menu.handle_session_list_key(Key.ENTER), [])

    def test_esc_goes_back_to_the_choice(self):
        self.open_session_list()

        self.assertIsNone(self.menu.handle_session_list_key(Key.ESC))
        self.assertIsNone(self.menu.session_selection)

    def test_list_opens_again_with_every_session_checked(self):
        self.open_session_list()
        self.menu.handle_session_list_key(Key.SPACE)
        self.menu.handle_session_list_key(Key.ESC)

        self.open_session_list()

        self.assertEqual(self.menu.handle_session_list_key(Key.ENTER), self.sessions)


class RunTest(RestoreMenuTestCase):
    def test_ctrl_c_quits_from_both_screens(self):
        with patch("launcher.restore_menu.render_screen"), patch("launcher.restore_menu.read_key", return_value=Key.CTRL_C):
            self.assertIs(RestoreMenu([], self.sessions).run(), QUIT)

        with (
            patch("launcher.restore_menu.render_screen"),
            patch("launcher.restore_menu.read_key", side_effect=[Key.ENTER, Key.CTRL_C]),
        ):
            self.assertIs(RestoreMenu([], self.sessions).run(), QUIT)

    def test_keys_restore_the_checked_sessions(self):
        keys = [Key.ENTER, Key.DOWN, Key.SPACE, Key.ENTER]

        with patch("launcher.restore_menu.render_screen"), patch("launcher.restore_menu.read_key", side_effect=keys):
            self.assertEqual(restore_menu.prompt_for_restore([], self.sessions), [self.sessions[0], self.sessions[2]])
