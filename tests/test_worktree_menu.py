import os
import unittest
from unittest.mock import patch

from launcher import history, worktree_menu, worktrees, worktrees_state
from launcher.accounts import Account
from launcher.folder_menu import NEW_SESSION
from launcher.keyboard import Key
from launcher.terminal_ui import BACK, GREEN, SEPARATOR, SectionTitle
from launcher.worktree_menu import ADD_WORKTREE, NO_WORKTREE, BranchPicker, entry_label, entry_secondary_label, worktree_header_line
from tests.git_helpers import clone, read_upstream, run
from tests.test_history import make_junction
from tests.test_worktrees import WorktreesTestCase


def setUpModule():
    # INFO: A menu waiting for a key would hang the tests, any unexpected read fails them instead
    read_key_patch = patch("launcher.worktree_menu.read_key", side_effect=AssertionError("Unexpected key read"))
    read_key_patch.start()
    unittest.addModuleCleanup(read_key_patch.stop)
    # INFO: A background fetch would outlive the test and its temp folder
    fetch_patch = patch("launcher.worktrees.start_fetch_prune")
    fetch_patch.start()
    unittest.addModuleCleanup(fetch_patch.stop)


def describe(item):
    if item is SEPARATOR:
        return ""

    if isinstance(item, SectionTitle):
        return item.label

    return item if isinstance(item, str) else entry_label(item)


class WorktreeMenuTestCase(WorktreesTestCase):
    def setUp(self):
        super().setUp()
        self.account = Account("a1b2c3d4", self.root / "account", name="Tests")

    def open_menu(self, repo=None):
        return worktree_menu.WorktreeMenu(repo or self.repo, repo or self.repo, [], self.account, NEW_SESSION)

    def select(self, menu, entry):
        menu.selection.selected_index = menu.selection.items.index(entry)

    def selectable_labels(self, menu):
        return [entry_label(menu.selection.items[index]) for index in menu.selection.selectable_indexes]

    def add_worktree(self, menu, name, picked_branch):
        """Confirms + Worktree with the name, then picks the branch. Returns the outcome and the arguments of the branch picker."""
        self.select(menu, ADD_WORKTREE)

        with (
            patch("launcher.worktree_menu.ask_worktree_name", return_value=name),
            patch("launcher.worktree_menu.prompt_for_branch", return_value=picked_branch) as prompt_for_branch,
        ):
            outcome = menu.handle_list_key(Key.ENTER)

        return outcome, prompt_for_branch.call_args.args if prompt_for_branch.called else None


class MainListTest(WorktreeMenuTestCase):
    def test_no_worktree_then_worktrees_by_name_then_add(self):
        worktrees.create_worktree(self.repo, "beta", "dev")
        worktrees.create_worktree(self.repo, "Alpha", "dev")
        menu = self.open_menu()

        self.assertEqual(self.selectable_labels(menu), ["No worktree", "Alpha", "beta", "+ Worktree"])
        self.assertIs(menu.entry, NO_WORKTREE)

    def test_repo_without_worktrees(self):
        menu = self.open_menu()

        self.assertEqual(self.selectable_labels(menu), ["No worktree", "+ Worktree"])
        self.assertIs(menu.entry, NO_WORKTREE)

    def test_enter_launches_the_highlighted_entry(self):
        worktree = worktrees.create_worktree(self.repo, "feature", "dev")
        menu = self.open_menu()

        self.assertIs(menu.handle_list_key(Key.ENTER), NO_WORKTREE)

        self.select(menu, worktree)
        self.assertEqual(menu.handle_list_key(Key.ENTER), worktree)

    def test_esc_goes_back(self):
        self.assertIs(self.open_menu().handle_list_key(Key.ESC), BACK)


class RemovedOptionsTest(WorktreeMenuTestCase):
    def test_right_on_add_worktree_does_nothing(self):
        menu = self.open_menu()
        self.select(menu, ADD_WORKTREE)

        self.assertIsNone(menu.handle_list_key(Key.RIGHT))
        self.assertIs(menu.entry, ADD_WORKTREE)
        self.assertNotIn("Right", worktree_menu.WORKTREE_HELP_TEXT)

    def test_base_branch_options_no_longer_exist(self):
        for name in ("EDIT_BASE_BRANCHES", "WORKTREE_FROM_BRANCH", "ADD_WORKTREE_OPTIONS", "prompt_for_base_branches"):
            self.assertFalse(hasattr(worktree_menu, name), name)


class LabelTest(WorktreeMenuTestCase):
    def make_worktree(self, origin_branch, is_merged=False):
        return worktrees.Worktree("feature", self.worktrees_dir / "a1b2c3d4" / "feature", self.repo, origin_branch, is_merged)

    def test_worktree_with_an_origin(self):
        worktree = self.make_worktree("dev")

        self.assertEqual(entry_secondary_label(worktree), "from dev")
        self.assertEqual(worktree_header_line(worktree, GREEN).value, "feature  (from dev)")

    def test_worktree_without_origin(self):
        worktree = self.make_worktree(None)

        self.assertIsNone(entry_secondary_label(worktree))
        self.assertEqual(worktree_header_line(worktree, GREEN).value, "feature")

    def test_merged_worktree(self):
        worktree = self.make_worktree("feature/pr", is_merged=True)

        self.assertEqual(entry_secondary_label(worktree), "from feature/pr · merged")
        self.assertEqual(worktree_header_line(worktree, GREEN).value, "feature  (from feature/pr · merged)")

    def test_other_entries_have_no_secondary_label(self):
        self.assertIsNone(entry_secondary_label(NO_WORKTREE))
        self.assertIsNone(entry_secondary_label(ADD_WORKTREE))


class MergedOnOpeningTest(WorktreeMenuTestCase):
    def setUp(self):
        super().setUp()
        run(self.repo, "branch", "feature/pr")
        self.clone = clone(self.repo, self.root / "clone")
        worktrees.create_worktree(self.clone, "merged-one", "origin/feature/pr")
        run(self.repo, "branch", "--quiet", "-D", "feature/pr")

    def listed_worktree(self, menu):
        return next(item for item in menu.selection.items if isinstance(item, worktrees.Worktree))

    def test_opening_shows_the_merged_worktree_of_the_last_fetch(self):
        run(self.clone, "fetch", "--quiet", "--prune")

        worktree = self.listed_worktree(self.open_menu(self.clone))

        self.assertTrue(worktree.is_merged)
        self.assertEqual(entry_secondary_label(worktree), "from feature/pr · merged")

    def test_opening_starts_a_fetch_for_the_next_one(self):
        worktree = self.listed_worktree(self.open_menu(self.clone))

        self.assertFalse(worktree.is_merged)
        worktrees.start_fetch_prune.assert_called_with(self.clone)


class AddWorktreeTest(WorktreeMenuTestCase):
    def test_valid_name_opens_the_branch_picker_of_the_repo(self):
        outcome, picker_arguments = self.add_worktree(self.open_menu(), "feature", BACK)

        self.assertIsNone(outcome)
        self.assertEqual(picker_arguments[0], self.repo)
        self.assertEqual(worktrees.load_worktrees(self.repo), [])

    def test_picked_local_branch_becomes_the_upstream(self):
        outcome, _ = self.add_worktree(self.open_menu(), "feature", "dev")

        self.assertIsInstance(outcome, worktrees.Worktree)
        self.assertEqual(outcome.origin_branch, "dev")
        self.assertEqual(read_upstream(self.repo, "temp/feature"), "dev")

    def test_picked_remote_only_branch_gets_its_local_branch(self):
        run(self.repo, "branch", "release/test")
        cloned = clone(self.repo, self.root / "clone")

        outcome, _ = self.add_worktree(self.open_menu(cloned), "feature", "origin/release/test")

        self.assertEqual(outcome.origin_branch, "release/test")
        self.assertEqual(read_upstream(cloned, "release/test"), "origin/release/test")
        self.assertEqual(read_upstream(cloned, "temp/feature"), "release/test")

    def test_invalid_name_is_refused_before_the_branch_choice(self):
        menu = self.open_menu()
        outcome, picker_arguments = self.add_worktree(menu, "with space", "dev")

        self.assertIsNone(outcome)
        self.assertIsNone(picker_arguments)
        self.assertEqual(menu.message.text, '"with space" is not a valid worktree name.')

    def test_cancelled_name_creates_nothing(self):
        outcome, picker_arguments = self.add_worktree(self.open_menu(), None, "dev")

        self.assertIsNone(outcome)
        self.assertIsNone(picker_arguments)
        self.assertEqual(worktrees.load_worktrees(self.repo), [])

    def test_failed_creation_shows_a_message_and_saves_nothing(self):
        menu = self.open_menu()
        outcome, _ = self.add_worktree(menu, "feature", "no-such-branch")

        self.assertIsNone(outcome)
        self.assertEqual(menu.message.text, "Could not create the worktree.")
        self.assertIsNone(worktrees_state.load_repo_id(self.repo))


class StaleHistoryLinkTest(WorktreeMenuTestCase):
    def test_opening_removes_the_links_of_removed_worktrees(self):
        live = worktrees.create_worktree(self.repo, "live", "dev")
        removed_path = live.path.parent / "removed"
        repo_history = history.get_history_dir(self.account.config_dir, self.repo)
        repo_history.mkdir(parents=True)
        live_link = history.get_history_dir(self.account.config_dir, live.path)
        removed_link = history.get_history_dir(self.account.config_dir, removed_path)
        make_junction(live_link, repo_history)
        make_junction(removed_link, repo_history)

        self.open_menu()

        self.assertTrue(os.path.isjunction(live_link))
        self.assertFalse(os.path.lexists(removed_link))
        self.assertTrue(repo_history.is_dir())


class BranchPickerTestCase(WorktreesTestCase):
    def setUp(self):
        super().setUp()
        for branch in ("stage", "release/test"):
            run(self.repo, "branch", branch)

        self.clone = clone(self.repo, self.root / "clone")
        worktrees.create_worktree(self.clone, "busy", "master")

    def open_picker(self, *favorites):
        for branch in favorites:
            worktrees_state.toggle_favorite_branch(self.clone, branch)

        return BranchPicker(self.clone, [])

    def layout(self, picker):
        return [describe(item) for item in picker.selection.items]

    def select(self, picker, branch, in_favorites):
        separator_index = picker.selection.items.index(SEPARATOR) if SEPARATOR in picker.selection.items else -1
        picker.selection.selected_index = next(
            index
            for index, item in enumerate(picker.selection.items)
            if item == branch and (index < separator_index) == in_favorites
        )

    def type_text(self, picker, text):
        for character in text:
            self.assertIsNone(picker.handle_key(character))


ALL_BRANCHES = ["master", "origin/dev", "origin/release/test", "origin/stage"]


class BranchLayoutTest(BranchPickerTestCase):
    def test_favorites_on_top_of_every_branch(self):
        picker = self.open_picker("origin/stage", "master")

        self.assertEqual(self.layout(picker), ["★ Favorites", "master", "origin/stage", "", "Branches", *ALL_BRANCHES])
        self.assertEqual(picker.selection.selected, "master")

    def test_without_favorites_only_branches_are_listed(self):
        picker = self.open_picker()

        self.assertEqual(self.layout(picker), ["Branches", *ALL_BRANCHES])
        self.assertEqual(picker.selection.selected, "master")

    def test_favorite_that_no_longer_exists_is_hidden_but_kept(self):
        picker = self.open_picker("deleted-branch", "origin/dev")

        self.assertEqual(self.layout(picker), ["★ Favorites", "origin/dev", "", "Branches", *ALL_BRANCHES])
        self.assertIn("deleted-branch", worktrees_state.load_favorite_branches(self.clone))

    def test_temp_branches_are_never_listed(self):
        self.assertFalse(any("temp/" in label for label in self.layout(self.open_picker())))


class BranchFavoriteTest(BranchPickerTestCase):
    def test_ctrl_f_adds_the_highlighted_branch(self):
        picker = self.open_picker()
        self.select(picker, "origin/dev", in_favorites=False)

        self.assertIsNone(picker.handle_key(Key.CTRL_F))

        self.assertEqual(worktrees_state.load_favorite_branches(self.clone), ["origin/dev"])
        self.assertEqual(self.layout(picker), ["★ Favorites", "origin/dev", "", "Branches", *ALL_BRANCHES])
        self.assertEqual(picker.selection.selected, "origin/dev")
        self.assertEqual(picker.notice.color, GREEN)

    def test_ctrl_f_on_a_favorite_removes_it(self):
        picker = self.open_picker("origin/dev", "master")
        self.select(picker, "origin/dev", in_favorites=True)

        self.assertIsNone(picker.handle_key(Key.CTRL_F))

        self.assertEqual(worktrees_state.load_favorite_branches(self.clone), ["master"])
        self.assertEqual(self.layout(picker), ["★ Favorites", "master", "", "Branches", *ALL_BRANCHES])
        self.assertIsInstance(picker.selection.selected, str)

    def test_ctrl_f_on_the_last_favorite_removes_the_section(self):
        picker = self.open_picker("master")

        picker.handle_key(Key.CTRL_F)

        self.assertEqual(self.layout(picker), ["Branches", *ALL_BRANCHES])
        self.assertIsInstance(picker.selection.selected, str)


class BranchFilterTest(BranchPickerTestCase):
    def test_typed_characters_filter_both_sections(self):
        picker = self.open_picker("origin/stage", "master")
        self.type_text(picker, "stag")

        self.assertEqual(picker.filter_text, "stag")
        self.assertEqual(self.layout(picker), ["★ Favorites", "origin/stage", "", "Branches", "origin/stage"])

    def test_favorites_section_hidden_when_no_favorite_matches(self):
        picker = self.open_picker("master")
        self.type_text(picker, "release")

        self.assertEqual(self.layout(picker), ["Branches", "origin/release/test"])

    def test_backspace_erases_one_character(self):
        picker = self.open_picker()
        self.type_text(picker, "stagx")
        self.assertEqual(self.layout(picker), ["Branches"])

        self.assertIsNone(picker.handle_key(Key.BACKSPACE))

        self.assertEqual(picker.filter_text, "stag")
        self.assertEqual(self.layout(picker), ["Branches", "origin/stage"])

    def test_esc_clears_the_filter_then_goes_back(self):
        picker = self.open_picker()
        self.type_text(picker, "stag")

        self.assertIsNone(picker.handle_key(Key.ESC))
        self.assertEqual(picker.filter_text, "")
        self.assertEqual(self.layout(picker), ["Branches", *ALL_BRANCHES])

        self.assertIs(picker.handle_key(Key.ESC), BACK)


class BranchPickTest(BranchPickerTestCase):
    def test_enter_picks_the_highlighted_branch(self):
        picker = self.open_picker("origin/stage")
        self.select(picker, "origin/release/test", in_favorites=False)

        self.assertEqual(picker.handle_key(Key.ENTER), "origin/release/test")

    def test_enter_picks_a_favorite(self):
        picker = self.open_picker("origin/stage")

        self.assertEqual(picker.handle_key(Key.ENTER), "origin/stage")

    def test_enter_and_ctrl_f_do_nothing_without_any_listed_branch(self):
        picker = self.open_picker()
        self.type_text(picker, "zzz")

        self.assertIsNone(picker.handle_key(Key.ENTER))
        self.assertIsNone(picker.handle_key(Key.CTRL_F))
        self.assertEqual(worktrees_state.load_favorite_branches(self.clone), [])
