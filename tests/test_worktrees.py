import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher import worktrees, worktrees_state
from tests.git_helpers import commit_on_branch, configure_identity, make_repo, run


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


class HandoffBranchTest(WorktreesTestCase):
    def test_pushed_handoff_branch_becomes_the_source_of_a_new_worktree(self):
        run(self.repo, "branch", "feature/handoff")
        commit_on_branch(self.repo, "feature/handoff", "progress.txt", "half done")
        clone = self.root / "clone"
        run(self.root, "clone", "--quiet", str(self.repo), str(clone))
        configure_identity(clone)

        self.assertIn("origin/feature/handoff", worktrees.list_branches(clone))

        worktree = worktrees.create_worktree(clone, "resume", "origin/feature/handoff")

        self.assertEqual(worktree.source_branch, "feature/handoff")
        self.assertEqual(worktree.branch, "temp/resume")
        self.assertEqual((worktree.path / "progress.txt").read_text(), "half done")


class OrphanFolderTest(WorktreesTestCase):
    def lock_folder(self, folder):
        # INFO: On Windows, a process whose current directory is the folder prevents its removal
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=folder)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)

    def unregister(self, worktree):
        """Removes the worktree with git alone, as done from a Claude Code session, leaving its folder empty."""
        run(self.repo, "worktree", "remove", "--force", str(worktree.path))
        run(self.repo, "branch", "--quiet", "-D", worktree.branch)
        worktree.path.mkdir(exist_ok=True)

    def test_worktree_unregistered_by_git_leaves_the_list(self):
        kept = worktrees.create_worktree(self.repo, "kept", "dev")
        removed = worktrees.create_worktree(self.repo, "removed", "dev")
        run(self.repo, "worktree", "remove", "--force", str(removed.path))

        self.assertEqual(worktrees.load_worktrees(self.repo), [kept])
        self.assertEqual(worktrees_state.load_worktree_sources(self.repo), {"kept": "dev"})

    def test_empty_folder_left_by_an_unregistered_worktree_is_removed(self):
        kept = worktrees.create_worktree(self.repo, "kept", "dev")
        removed = worktrees.create_worktree(self.repo, "removed", "dev")
        self.unregister(removed)

        self.assertEqual(worktrees.load_worktrees(self.repo), [kept])
        self.assertFalse(removed.path.exists())
        self.assertTrue(kept.path.exists())
        self.assertIsNone(worktrees.validate_worktree_name(self.repo, "removed"))

    def test_non_empty_unknown_folder_is_kept(self):
        notes = worktrees.get_repo_dir(self.repo) / "notes"
        notes.mkdir(parents=True)
        (notes / "todo.txt").write_text("keep me")

        self.assertEqual(worktrees.load_worktrees(self.repo), [])
        self.assertEqual((notes / "todo.txt").read_text(), "keep me")

    def test_unknown_file_is_kept(self):
        repo_dir = worktrees.get_repo_dir(self.repo)
        repo_dir.mkdir(parents=True)
        (repo_dir / "notes.txt").write_text("keep me")

        worktrees.load_worktrees(self.repo)

        self.assertEqual((repo_dir / "notes.txt").read_text(), "keep me")

    def test_locked_empty_folder_does_not_prevent_loading(self):
        kept = worktrees.create_worktree(self.repo, "kept", "dev")
        removed = worktrees.create_worktree(self.repo, "busy", "dev")
        self.unregister(removed)
        self.lock_folder(removed.path)

        self.assertEqual(worktrees.load_worktrees(self.repo), [kept])

    def test_repo_without_worktrees_folder_loads(self):
        self.assertEqual(worktrees.load_worktrees(self.repo), [])
