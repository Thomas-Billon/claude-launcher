import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher import folder_menu, launcher_state
from launcher.accounts import Account
from launcher.folder_menu import FAVORITES_TITLE, NEW_FOLDER, SUBFOLDERS_TITLE, FolderMenu, format_folder_label
from launcher.keyboard import Key
from launcher.terminal_ui import ANSI_PATTERN, DARK_GRAY, GREEN, RED, SEPARATOR, Message, SectionTitle


def describe(item):
    if item is SEPARATOR:
        return ""

    return item.label


class FolderMenuTestCase(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name).resolve()
        state_patch = patch("launcher.launcher_state.STATE_FILE", self.root / "launcher_state.json")
        state_patch.start()
        self.addCleanup(state_patch.stop)

        self.projects = self.root / "Projets"
        self.other = self.root / "Other"

        for folder in ("Alpha/child1", "Alpha/child2", "beta", "Gamma"):
            (self.projects / folder).mkdir(parents=True)

        for folder in ("zeta", "Delta", "Omega"):
            (self.other / folder).mkdir(parents=True)

        self.account = Account("a1b2c3d4", self.root / "a1b2c3d4", name="Perso")
        self.other_account = Account("e5f6a7b8", self.root / "e5f6a7b8", name="Shope")

    def add_favorites(self, *folders, account=None):
        for folder in folders:
            launcher_state.toggle_favorite(account or self.account, folder)

    def open_menu(self, is_launch=True):
        help_text = folder_menu.FOLDER_HELP_TEXT if is_launch else folder_menu.DEFAULT_FOLDER_HELP_TEXT

        return FolderMenu(self.projects, [], self.account, is_launch, help_text)

    def layout(self, menu):
        return [describe(item) for item in menu.selection.items]

    def subfolders_title_index(self, menu):
        return menu.selection.items.index(SUBFOLDERS_TITLE)

    def select(self, menu, path, in_favorites):
        title_index = self.subfolders_title_index(menu)
        menu.selection.selected_index = next(
            index
            for index, item in enumerate(menu.selection.items)
            if isinstance(item, folder_menu.FolderEntry) and item.path == path and (index < title_index) == in_favorites
        )

    def type_text(self, menu, text):
        for character in text:
            menu.handle_key(character)

    def favorite_labels(self, *folders):
        return [format_folder_label(folder) for folder in folders]


class LayoutTest(FolderMenuTestCase):
    def test_favorites_section_on_top_of_subfolders(self):
        self.add_favorites(self.other / "zeta", self.other / "Delta")
        menu = self.open_menu()

        self.assertEqual(
            self.layout(menu),
            [
                "★ Favorites",
                *self.favorite_labels(self.other / "Delta", self.other / "zeta"),
                "",
                "Subfolders",
                "Alpha",
                "beta",
                "Gamma",
                "+ New folder",
            ],
        )

    def test_without_favorites_only_subfolders_are_listed(self):
        menu = self.open_menu()

        self.assertEqual(self.layout(menu), ["Subfolders", "Alpha", "beta", "Gamma", "+ New folder"])

    def test_section_titles_are_section_title_items(self):
        self.assertIsInstance(FAVORITES_TITLE, SectionTitle)
        self.assertIsInstance(SUBFOLDERS_TITLE, SectionTitle)

    def test_favorite_in_current_directory_is_listed_in_both_sections(self):
        self.add_favorites(self.projects / "beta")
        menu = self.open_menu()

        self.assertEqual(
            self.layout(menu),
            ["★ Favorites", *self.favorite_labels(self.projects / "beta"), "", "Subfolders", "Alpha", "beta", "Gamma", "+ New folder"],
        )

    def test_favorites_of_another_account_are_not_listed(self):
        self.add_favorites(self.other / "Omega", account=self.other_account)
        menu = self.open_menu()

        self.assertNotIn(FAVORITES_TITLE, menu.selection.items)

    def test_default_folder_menu_has_no_favorites(self):
        self.add_favorites(self.other / "zeta")
        menu = self.open_menu(is_launch=False)

        self.assertNotIn(FAVORITES_TITLE, menu.selection.items)
        self.assertNotIn(format_folder_label(self.other / "zeta"), self.layout(menu))

    def test_launch_help_text_shows_the_favorite_key(self):
        self.assertIn("Ctrl+F: Favorite", folder_menu.FOLDER_HELP_TEXT)


class FilterTest(FolderMenuTestCase):
    def test_filter_applies_to_favorites(self):
        self.add_favorites(self.other / "zeta", self.other / "Omega")
        menu = self.open_menu()
        self.type_text(menu, "omeg")

        self.assertEqual(self.layout(menu), ["★ Favorites", *self.favorite_labels(self.other / "Omega"), "", "Subfolders", "+ New folder"])

    def test_favorites_section_hidden_when_no_favorite_matches(self):
        self.add_favorites(self.other / "zeta")
        menu = self.open_menu()
        self.type_text(menu, "gam")

        self.assertEqual(self.layout(menu), ["Subfolders", "Gamma", "+ New folder"])


class HighlightTest(FolderMenuTestCase):
    def test_first_favorite_is_highlighted_on_opening(self):
        self.add_favorites(self.other / "zeta", self.other / "Delta")
        menu = self.open_menu()

        self.assertEqual(menu.selection.selected.path, self.other / "Delta")

    def test_first_subfolder_is_highlighted_without_favorites(self):
        menu = self.open_menu()

        self.assertEqual(menu.selection.selected.path, self.projects / "Alpha")

    def test_right_into_a_folder_highlights_its_first_subfolder(self):
        self.add_favorites(self.other / "zeta")
        menu = self.open_menu()
        self.select(menu, self.projects / "Alpha", in_favorites=False)
        menu.handle_key(Key.RIGHT)

        self.assertEqual(menu.current_dir, self.projects / "Alpha")
        self.assertEqual(menu.selection.selected.path, self.projects / "Alpha" / "child1")

    def test_titles_are_skipped_by_up_and_down(self):
        self.add_favorites(self.other / "zeta")
        menu = self.open_menu()

        menu.selection.handle_key(Key.DOWN)
        self.assertEqual(menu.selection.selected.path, self.projects / "Alpha")

        menu.selection.handle_key(Key.UP)
        menu.selection.handle_key(Key.UP)
        self.assertIs(menu.selection.selected, NEW_FOLDER)


class ToggleFavoriteTest(FolderMenuTestCase):
    def test_ctrl_f_on_subfolder_adds_it_and_keeps_the_highlight(self):
        menu = self.open_menu()
        self.select(menu, self.projects / "beta", in_favorites=False)

        self.assertIsNone(menu.handle_key(Key.CTRL_F))

        self.assertEqual(launcher_state.load_favorites(self.account), [self.projects / "beta"])
        self.assertIn(format_folder_label(self.projects / "beta"), self.layout(menu))
        self.assertEqual(menu.selection.selected.path, self.projects / "beta")
        self.assertGreater(menu.selection.selected_index, self.subfolders_title_index(menu))
        self.assertEqual(menu.notice.color, GREEN)
        self.assertTrue(menu.notice.text.startswith("Added "), menu.notice.text)
        self.assertTrue(menu.notice.text.endswith(" to favorites."), menu.notice.text)

    def test_ctrl_f_on_favorite_subfolder_removes_it(self):
        self.add_favorites(self.projects / "beta")
        menu = self.open_menu()
        self.select(menu, self.projects / "beta", in_favorites=False)
        menu.handle_key(Key.CTRL_F)

        self.assertEqual(launcher_state.load_favorites(self.account), [])
        self.assertNotIn(FAVORITES_TITLE, menu.selection.items)
        self.assertEqual(menu.selection.selected.path, self.projects / "beta")
        self.assertEqual(menu.notice.color, GREEN)
        self.assertTrue(menu.notice.text.startswith("Removed "), menu.notice.text)
        self.assertTrue(menu.notice.text.endswith(" from favorites."), menu.notice.text)

    def test_unfavorite_moves_the_highlight_to_the_next_favorite(self):
        self.add_favorites(self.other / "zeta", self.other / "Delta", self.other / "Omega")
        menu = self.open_menu()
        self.select(menu, self.other / "Omega", in_favorites=True)
        menu.handle_key(Key.CTRL_F)

        self.assertEqual(launcher_state.load_favorites(self.account), [self.other / "Delta", self.other / "zeta"])
        self.assertEqual(menu.selection.selected.path, self.other / "zeta")
        self.assertLess(menu.selection.selected_index, self.subfolders_title_index(menu))

    def test_unfavorite_of_the_last_favorite_moves_the_highlight_to_the_previous_one(self):
        self.add_favorites(self.other / "zeta", self.other / "Delta")
        menu = self.open_menu()
        self.select(menu, self.other / "zeta", in_favorites=True)
        menu.handle_key(Key.CTRL_F)

        self.assertEqual(menu.selection.selected.path, self.other / "Delta")

    def test_unfavorite_of_the_only_favorite_moves_the_highlight_to_the_first_subfolder(self):
        self.add_favorites(self.other / "zeta")
        menu = self.open_menu()
        menu.handle_key(Key.CTRL_F)

        self.assertEqual(launcher_state.load_favorites(self.account), [])
        self.assertEqual(menu.selection.selected.path, self.projects / "Alpha")

    def test_ctrl_f_on_new_folder_does_nothing(self):
        menu = self.open_menu()
        menu.selection.selected_index = menu.selection.items.index(NEW_FOLDER)

        self.assertIsNone(menu.handle_key(Key.CTRL_F))
        self.assertEqual(launcher_state.load_favorites(self.account), [])
        self.assertIsNone(menu.notice)

    def test_ctrl_f_is_ignored_in_the_default_folder_menu(self):
        menu = self.open_menu(is_launch=False)
        self.select(menu, self.projects / "beta", in_favorites=False)

        self.assertIsNone(menu.handle_key(Key.CTRL_F))
        self.assertEqual(launcher_state.load_favorites(self.account), [])
        self.assertIsNone(menu.notice)


class MissingFavoriteTest(FolderMenuTestCase):
    def setUp(self):
        super().setUp()
        self.ghost = self.root / "ghost"
        self.add_favorites(self.ghost, self.other / "zeta")

    def test_missing_favorite_is_listed_with_a_gray_label(self):
        menu = self.open_menu()
        lines = menu.selection.render(30, 200)
        ghost_line = next(line for line in lines if "ghost" in ANSI_PATTERN.sub("", line))

        self.assertIn("(missing)", ANSI_PATTERN.sub("", ghost_line))
        self.assertIn(DARK_GRAY + "  (missing)", ghost_line)
        self.assertTrue(menu.selection.selected.is_missing)

    def test_existing_favorite_has_no_missing_label(self):
        menu = self.open_menu()
        lines = menu.selection.render(30, 200)
        zeta_line = next(line for line in lines if "zeta" in ANSI_PATTERN.sub("", line))

        self.assertNotIn("(missing)", ANSI_PATTERN.sub("", zeta_line))

    def test_enter_on_missing_favorite_does_not_launch(self):
        menu = self.open_menu()
        self.select(menu, self.ghost, in_favorites=True)

        self.assertIsNone(menu.handle_key(Key.ENTER))
        self.assertEqual(menu.notice, Message("Folder not found.", RED))

    def test_enter_on_existing_favorite_launches_it(self):
        menu = self.open_menu()
        self.select(menu, self.other / "zeta", in_favorites=True)

        self.assertEqual(menu.handle_key(Key.ENTER), self.other / "zeta")

    def test_missing_favorite_can_be_removed(self):
        menu = self.open_menu()
        self.select(menu, self.ghost, in_favorites=True)
        menu.handle_key(Key.CTRL_F)

        self.assertEqual(launcher_state.load_favorites(self.account), [self.other / "zeta"])
        self.assertNotIn(format_folder_label(self.ghost), self.layout(menu))

    def test_missing_favorite_is_never_removed_automatically(self):
        self.open_menu()

        self.assertIn(self.ghost, launcher_state.load_favorites(self.account))
