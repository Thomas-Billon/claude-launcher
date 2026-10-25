from unittest.mock import patch

from launcher import worktree_menu, worktrees, worktrees_state
from launcher.accounts import Account
from launcher.folder_menu import NEW_SESSION
from launcher.keyboard import Key
from launcher.terminal_ui import BACK
from tests.git_helpers import commit_on_branch, configure_identity, run
from tests.test_worktrees import WorktreesTestCase


class WorktreeMenuTestCase(WorktreesTestCase):
    def open_menu(self, repo, selected_entry=worktree_menu.NO_WORKTREE):
        account = Account("a1b2c3d4", self.root / "account", name="Tests")
        menu = worktree_menu.WorktreeMenu(repo, repo, [], account, NEW_SESSION)
        menu.reload(selected_entry)

        return menu


class WorktreeOptionsTest(WorktreeMenuTestCase):
    def test_existing_worktree_has_no_options(self):
        worktree = worktrees.create_worktree(self.repo, "feature", "dev")
        menu = self.open_menu(self.repo, worktree)

        self.assertIsNone(menu.handle_list_key(Key.RIGHT))
        self.assertIsNone(menu.side_selection)

    def test_main_folder_has_no_options(self):
        menu = self.open_menu(self.repo)

        self.assertIsNone(menu.handle_list_key(Key.RIGHT))
        self.assertIsNone(menu.side_selection)


class WorktreeFromBranchTest(WorktreeMenuTestCase):
    def setUp(self):
        super().setUp()
        run(self.repo, "branch", "feature/handoff")
        commit_on_branch(self.repo, "feature/handoff", "progress.txt", "half done")
        self.clone = self.root / "clone"
        run(self.root, "clone", "--quiet", str(self.repo), str(self.clone))
        configure_identity(self.clone)
        worktrees_state.save_base_branches(self.clone, ["master"])

    def choose_worktree_from_branch(self, name, picked_branch):
        """Opens the options of + Worktree and enters Worktree from branch. Returns the outcome and the offered branches."""
        menu = self.open_menu(self.clone, worktree_menu.ADD_WORKTREE)
        menu.handle_list_key(Key.RIGHT)

        for _ in menu.side_selection.items:
            if menu.side_selection.selected == worktree_menu.WORKTREE_FROM_BRANCH:
                break

            menu.handle_options_key(Key.DOWN)

        self.assertEqual(menu.side_selection.selected, worktree_menu.WORKTREE_FROM_BRANCH)

        with (
            patch("launcher.worktree_menu.ask_worktree_name", return_value=name),
            patch("launcher.worktree_menu.prompt_for_branch", return_value=picked_branch) as prompt_for_branch,
        ):
            outcome = menu.handle_options_key(Key.ENTER)

        offered_branches = prompt_for_branch.call_args.args[0] if prompt_for_branch.called else None

        return menu, outcome, offered_branches

    def test_every_branch_is_offered(self):
        _, _, offered_branches = self.choose_worktree_from_branch("resume", BACK)

        self.assertEqual(offered_branches, worktrees.list_branches(self.clone))
        self.assertIn("origin/feature/handoff", offered_branches)

    def test_worktree_starts_from_the_picked_remote_branch(self):
        _, outcome, _ = self.choose_worktree_from_branch("resume", "origin/feature/handoff")

        self.assertIsInstance(outcome, worktrees.Worktree)
        self.assertEqual(outcome.branch, "temp/resume")
        self.assertEqual(outcome.source_branch, "feature/handoff")
        self.assertEqual((outcome.path / "progress.txt").read_text(), "half done")
        self.assertEqual(worktrees_state.load_base_branches(self.clone), ["master"])

    def test_cancelled_branch_choice_creates_nothing(self):
        _, outcome, _ = self.choose_worktree_from_branch("resume", BACK)

        self.assertIsNone(outcome)
        self.assertEqual(worktrees.load_worktrees(self.clone), [])

    def test_invalid_name_is_refused_before_the_branch_choice(self):
        menu, outcome, offered_branches = self.choose_worktree_from_branch("with space", "origin/feature/handoff")

        self.assertIsNone(outcome)
        self.assertIsNone(offered_branches)
        self.assertEqual(menu.message.text, '"with space" is not a valid worktree name.')

    def test_cancelled_name_creates_nothing(self):
        _, outcome, offered_branches = self.choose_worktree_from_branch(None, "origin/feature/handoff")

        self.assertIsNone(outcome)
        self.assertIsNone(offered_branches)
        self.assertEqual(worktrees.load_worktrees(self.clone), [])
