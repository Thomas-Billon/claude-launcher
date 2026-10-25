import subprocess
import sys

from launcher import worktree_menu, worktrees
from tests.git_helpers import branch_exists, commit_file, git_output, run
from tests.test_worktrees import WorktreesTestCase


class LeftBranchTest(WorktreesTestCase):
    def test_merge_is_refused_when_the_worktree_left_its_branch(self):
        worktree = worktrees.create_worktree(self.repo, "feature", "dev")
        run(worktree.path, "checkout", "--quiet", "--detach")
        commit_file(worktree.path, "detached.txt", "detached")
        head = git_output(worktree.path, "rev-parse", "HEAD")

        self.assertFalse(worktrees.merge_into_source(self.repo, worktree))
        self.assertTrue(worktree.path.exists())
        self.assertEqual(git_output(worktree.path, "rev-parse", "HEAD"), head)

    def test_delete_is_refused_when_the_worktree_left_its_branch(self):
        worktree = worktrees.create_worktree(self.repo, "feature", "dev")
        run(worktree.path, "checkout", "--quiet", "--detach")
        commit_file(worktree.path, "detached.txt", "detached")

        self.assertFalse(worktrees.delete_worktree(self.repo, worktree))
        self.assertTrue(worktree.path.exists())

    def test_switched_branch_is_not_reported_as_merged(self):
        worktree = worktrees.create_worktree(self.repo, "feature", "dev")
        run(worktree.path, "switch", "--quiet", "-c", "other")
        commit_file(worktree.path, "other.txt", "other")

        self.assertFalse(worktrees.merge_into_source(self.repo, worktree))
        self.assertFalse(worktrees.keep_as_branch(self.repo, worktree, "fix/other"))
        self.assertTrue(worktree.path.exists())


class LockedFolderTest(WorktreesTestCase):
    def lock_folder(self, folder):
        # INFO: On Windows, a process whose current directory is the folder prevents its removal
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=folder)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)

    def test_merge_is_reported_even_when_the_folder_cannot_be_removed(self):
        worktree = worktrees.create_worktree(self.repo, "busy", "dev")
        commit_file(worktree.path, "busy.txt", "done")
        self.lock_folder(worktree.path)

        self.assertTrue(worktrees.merge_into_source(self.repo, worktree))
        self.assertFalse(worktrees.remove_worktree(self.repo, worktree))
        self.assertEqual(git_output(self.repo, "show", "dev:busy.txt"), "done")
        self.assertEqual(worktrees.load_worktrees(self.repo), [])

    def test_kept_branch_survives_a_folder_that_cannot_be_removed(self):
        worktree = worktrees.create_worktree(self.repo, "kb", "dev")
        self.lock_folder(worktree.path)

        self.assertTrue(worktrees.keep_as_branch(self.repo, worktree, "fix/kb"))
        self.assertFalse(worktrees.remove_worktree(self.repo, worktree))
        self.assertTrue(branch_exists(self.repo, "fix/kb"))
        self.assertEqual(worktrees.load_worktrees(self.repo), [])


class DeleteWarningTest(WorktreesTestCase):
    def test_unknown_unmerged_count_is_a_warning(self):
        worktree = worktrees.Worktree("gone-source", self.repo, "deleted")

        self.assertEqual(
            worktree_menu.delete_warning(worktree, None).text,
            "Could not count the commits of gone-source not merged into deleted, they would be lost.",
        )
        self.assertEqual(worktree_menu.delete_warning(worktree, 2).text, "2 commits of gone-source are not merged into deleted.")
        self.assertIsNone(worktree_menu.delete_warning(worktree, 0))
