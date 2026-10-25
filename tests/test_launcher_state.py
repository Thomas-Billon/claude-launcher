import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher import launcher_state
from launcher.accounts import Account

PERSO = Path("C:/Projets/Perso")


class LauncherStateTestCase(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.state_file = self.root / "launcher_state.json"
        state_patch = patch("launcher.launcher_state.STATE_FILE", self.state_file)
        state_patch.start()
        self.addCleanup(state_patch.stop)
        self.account = Account("a1b2c3d4", self.root / "a1b2c3d4", name="Perso")
        self.other_account = Account("e5f6a7b8", self.root / "e5f6a7b8", name="Shope")

    def read_state(self):
        return json.loads(self.state_file.read_text(encoding="utf-8"))


class FavoritesTest(LauncherStateTestCase):
    def test_new_account_has_no_favorites(self):
        self.assertEqual(launcher_state.load_favorites(self.account), [])

    def test_toggle_adds_then_removes(self):
        self.assertTrue(launcher_state.toggle_favorite(self.account, PERSO))
        self.assertEqual(launcher_state.load_favorites(self.account), [PERSO])

        self.assertFalse(launcher_state.toggle_favorite(self.account, PERSO))
        self.assertEqual(launcher_state.load_favorites(self.account), [])

    def test_toggle_ignores_the_case_of_the_path(self):
        launcher_state.toggle_favorite(self.account, PERSO)

        self.assertFalse(launcher_state.toggle_favorite(self.account, Path("c:/projets/PERSO")))
        self.assertEqual(launcher_state.load_favorites(self.account), [])

    def test_favorites_are_sorted_by_folder_name_then_path(self):
        for folder in ("C:/b/Zeta", "C:/a/alpha", "C:/c/Beta", "C:/d/same", "C:/a/same"):
            launcher_state.toggle_favorite(self.account, Path(folder))

        self.assertEqual(
            launcher_state.load_favorites(self.account),
            [Path("C:/a/alpha"), Path("C:/c/Beta"), Path("C:/a/same"), Path("C:/d/same"), Path("C:/b/Zeta")],
        )

    def test_favorites_are_kept_per_account(self):
        launcher_state.toggle_favorite(self.account, PERSO)
        launcher_state.toggle_favorite(self.other_account, Path("C:/Projets/Shope"))

        self.assertEqual(launcher_state.load_favorites(self.account), [PERSO])
        self.assertEqual(launcher_state.load_favorites(self.other_account), [Path("C:/Projets/Shope")])

    def test_favorites_are_saved_in_the_account_state(self):
        launcher_state.save_name(self.account, "Perso")
        launcher_state.toggle_favorite(self.account, PERSO)

        account_state = self.read_state()["accounts"][self.account.account_id]

        self.assertEqual(account_state["name"], "Perso")
        self.assertEqual([Path(folder) for folder in account_state["favorites"]], [PERSO])


class HistoryRemovalTest(LauncherStateTestCase):
    def test_history_functions_are_removed(self):
        for name in ("HISTORY_SIZE", "load_history", "prune_history", "record_launch", "remove_from_history", "clear_history"):
            self.assertFalse(hasattr(launcher_state, name), name)
