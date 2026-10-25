import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher import worktrees, worktrees_state
from tests.git_helpers import branch_exists, commit_file, commit_on_branch, configure_identity, git_output, make_repo, run


class WorktreesTestCase(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name).resolve()
        self.worktrees_dir = self.root / "worktrees"
        self.outside_dir = self.root / "outside"
        self.outside_dir.mkdir()
        self.repo = make_repo(self.root / "repo")

        for target, value in (
            ("launcher.worktrees.WORKTREES_DIR", self.worktrees_dir),
            ("launcher.worktrees_state.WORKTREES_STATE_FILE", self.root / "worktrees_state.json"),
        ):
            value_patch = patch(target, value)
            value_patch.start()
            self.addCleanup(value_patch.stop)


class CreationTest(WorktreesTestCase):
    def test_repo_root_is_found_from_a_subfolder(self):
        (self.repo / "src").mkdir()

        self.assertEqual(worktrees.find_repo_root(self.repo / "src"), self.repo)
        self.assertIsNone(worktrees.find_repo_root(self.outside_dir))

    def test_create_worktree_on_a_temp_branch(self):
        worktree = worktrees.create_worktree(self.repo, "export-pdf", "dev")

        self.assertEqual(worktree.branch, "temp/export-pdf")
        self.assertEqual(worktree.path.name, "export-pdf")
        self.assertEqual(worktree.path.parent.parent, self.worktrees_dir)
        self.assertEqual(worktrees.load_worktrees(self.repo), [worktree])

    def test_worktree_can_start_from_the_branch_of_the_main_folder(self):
        run(self.repo, "switch", "--quiet", "dev")

        self.assertIsNotNone(worktrees.create_worktree(self.repo, "on-dev", "dev"))

    def test_invalid_or_existing_names_are_refused(self):
        worktrees.create_worktree(self.repo, "taken", "dev")

        for name in ("with space", "a/b", "trailing.", "bad..name"):
            self.assertEqual(worktrees.validate_worktree_name(self.repo, name), f'"{name}" is not a valid worktree name.')

        self.assertEqual(worktrees.validate_worktree_name(self.repo, "taken"), '"taken" already exists.')
        self.assertIsNone(worktrees.validate_worktree_name(self.repo, "free"))

    def test_worktree_deleted_by_hand_is_pruned(self):
        worktree = worktrees.create_worktree(self.repo, "gone", "dev")
        shutil.rmtree(worktree.path)

        self.assertEqual(worktrees.load_worktrees(self.repo), [])
        self.assertEqual(worktrees_state.load_worktree_sources(self.repo), {})

    def test_remote_only_branch_becomes_a_local_source(self):
        clone = self.root / "clone"
        run(self.root, "clone", "--quiet", str(self.repo), str(clone))
        configure_identity(clone)

        self.assertIn("origin/dev", worktrees.list_branches(clone))

        worktree = worktrees.create_worktree(clone, "from-remote", "origin/dev")

        self.assertEqual(worktree.source_branch, "dev")
        self.assertIn("dev", worktrees.list_branches(clone))
        self.assertNotIn("origin/dev", worktrees.list_branches(clone))
        self.assertNotIn("temp/from-remote", worktrees.list_branches(clone))

    def test_remote_source_reuses_its_local_branch_once_created(self):
        clone = self.root / "clone"
        run(self.root, "clone", "--quiet", str(self.repo), str(clone))
        configure_identity(clone)
        worktrees.create_worktree(clone, "first", "origin/dev")

        worktree = worktrees.create_worktree(clone, "second", "origin/dev")

        self.assertIsNotNone(worktree)
        self.assertEqual(worktree.source_branch, "dev")


class FinishTest(WorktreesTestCase):
    def test_merge_fast_forwards_the_source(self):
        worktree = worktrees.create_worktree(self.repo, "feature", "dev")
        commit_file(worktree.path, "feature.txt", "done")

        self.assertTrue(worktrees.merge_into_source(self.repo, worktree))
        self.assertTrue(worktrees.remove_worktree(self.repo, worktree))
        self.assertEqual(git_output(self.repo, "show", "dev:feature.txt"), "done")
        self.assertFalse(worktree.path.exists())
        self.assertFalse(branch_exists(self.repo, "temp/feature"))

    def test_merge_rebases_when_the_source_moved(self):
        worktree = worktrees.create_worktree(self.repo, "feature", "dev")
        commit_file(worktree.path, "feature.txt", "done")
        commit_on_branch(self.repo, "dev", "other.txt", "meanwhile")

        self.assertTrue(worktrees.merge_into_source(self.repo, worktree))
        self.assertEqual(git_output(self.repo, "rev-list", "--merges", "--count", "dev"), "0")
        self.assertEqual(git_output(self.repo, "show", "dev:other.txt"), "meanwhile")
        self.assertEqual(git_output(self.repo, "show", "dev:feature.txt"), "done")

    def test_merge_into_the_checked_out_source_keeps_unrelated_changes(self):
        run(self.repo, "switch", "--quiet", "dev")
        worktree = worktrees.create_worktree(self.repo, "feature", "dev")
        commit_file(worktree.path, "feature.txt", "done")
        (self.repo / "README.md").write_text("work in progress")

        self.assertTrue(worktrees.merge_into_source(self.repo, worktree))
        self.assertEqual((self.repo / "README.md").read_text(), "work in progress")
        self.assertEqual((self.repo / "feature.txt").read_text(), "done")

    def test_merge_is_refused_over_changes_on_the_same_file(self):
        run(self.repo, "switch", "--quiet", "dev")
        worktree = worktrees.create_worktree(self.repo, "feature", "dev")
        commit_file(worktree.path, "README.md", "from worktree")
        (self.repo / "README.md").write_text("work in progress")

        self.assertFalse(worktrees.merge_into_source(self.repo, worktree))
        self.assertEqual((self.repo / "README.md").read_text(), "work in progress")
        self.assertTrue(branch_exists(self.repo, "temp/feature"))
        self.assertTrue(worktree.path.exists())

    def test_rebase_conflict_leaves_the_worktree_as_it_was(self):
        worktree = worktrees.create_worktree(self.repo, "feature", "dev")
        commit_file(worktree.path, "README.md", "from worktree")
        commit_on_branch(self.repo, "dev", "README.md", "from dev")
        head = git_output(worktree.path, "rev-parse", "HEAD")

        self.assertFalse(worktrees.merge_into_source(self.repo, worktree))
        self.assertEqual(git_output(worktree.path, "rev-parse", "HEAD"), head)
        self.assertEqual(worktrees.list_worktree_changes(worktree), [])

    def test_keep_as_branch_renames_the_branch(self):
        worktree = worktrees.create_worktree(self.repo, "long-fix", "dev")
        commit_file(worktree.path, "fix.txt", "fixed")

        self.assertTrue(worktrees.keep_as_branch(self.repo, worktree, "fix/long-fix"))
        self.assertTrue(worktrees.remove_worktree(self.repo, worktree))
        self.assertTrue(branch_exists(self.repo, "fix/long-fix"))
        self.assertFalse(branch_exists(self.repo, "temp/long-fix"))
        self.assertEqual(worktrees.load_worktrees(self.repo), [])

    def test_keep_as_branch_refuses_an_existing_branch(self):
        worktree = worktrees.create_worktree(self.repo, "long-fix", "dev")

        self.assertFalse(worktrees.keep_as_branch(self.repo, worktree, "dev"))
        self.assertTrue(branch_exists(self.repo, "temp/long-fix"))

    def test_delete_reports_then_drops_unmerged_commits(self):
        worktree = worktrees.create_worktree(self.repo, "dropped", "dev")
        commit_file(worktree.path, "a.txt", "a")

        self.assertEqual(worktrees.count_unmerged_commits(self.repo, worktree), 1)
        self.assertTrue(worktrees.delete_worktree(self.repo, worktree))
        self.assertFalse(branch_exists(self.repo, "temp/dropped"))
        self.assertFalse(worktree.path.exists())
