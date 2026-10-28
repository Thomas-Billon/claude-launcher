import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher import worktrees, worktrees_state
from tests.git_helpers import clone, commit_on_branch, make_repo, read, read_upstream, run


class WorktreesTestCase(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name).resolve()
        self.worktrees_dir = self.root / "worktrees"
        self.state_file = self.root / "worktrees_state.json"
        self.outside_dir = self.root / "outside"
        self.outside_dir.mkdir()
        self.repo = make_repo(self.root / "repo")

        for target, value in (
            ("launcher.worktrees.WORKTREES_DIR", self.worktrees_dir),
            ("launcher.worktrees_state.WORKTREES_STATE_FILE", self.state_file),
        ):
            value_patch = patch(target, value)
            value_patch.start()
            self.addCleanup(value_patch.stop)

    def read_state(self):
        return self.state_file.read_text(encoding="utf-8") if self.state_file.exists() else None

    def add_foreign_worktree(self, repo, path, branch, start_point="dev"):
        """Adds a worktree with git alone, as done outside the launcher, without any upstream."""
        run(repo, "worktree", "add", "--quiet", "--no-track", "-b", branch, str(path), start_point)


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
        self.assertEqual(worktree.repo, self.repo)
        self.assertEqual(worktree.origin_branch, "dev")
        self.assertFalse(worktree.is_merged)
        self.assertEqual(worktrees.load_worktrees(self.repo), [worktree])

    def test_local_origin_becomes_the_upstream_of_the_temp_branch(self):
        worktrees.create_worktree(self.repo, "export-pdf", "dev")

        self.assertEqual(read_upstream(self.repo, "temp/export-pdf"), "dev")

    def test_only_the_repo_id_is_saved(self):
        worktrees.create_worktree(self.repo, "export-pdf", "dev")
        repo_state = json.loads(self.read_state())["repos"][str(self.repo)]

        self.assertEqual(list(repo_state), ["id"])

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


class RemoteOriginTest(WorktreesTestCase):
    def setUp(self):
        super().setUp()
        run(self.repo, "branch", "release/test")
        self.clone = clone(self.repo, self.root / "clone")

    def test_remote_only_origin_creates_its_local_tracking_branch_first(self):
        self.assertIn("origin/release/test", worktrees.list_branches(self.clone))

        worktree = worktrees.create_worktree(self.clone, "from-remote", "origin/release/test")

        self.assertEqual(worktree.origin_branch, "release/test")
        self.assertEqual(read_upstream(self.clone, "release/test"), "origin/release/test")
        self.assertEqual(read_upstream(self.clone, "temp/from-remote"), "release/test")
        self.assertIn("release/test", worktrees.list_branches(self.clone))
        self.assertNotIn("origin/release/test", worktrees.list_branches(self.clone))
        self.assertNotIn("temp/from-remote", worktrees.list_branches(self.clone))

    def test_remote_origin_reuses_its_local_branch_once_created(self):
        worktrees.create_worktree(self.clone, "first", "origin/release/test")

        worktree = worktrees.create_worktree(self.clone, "second", "origin/release/test")

        self.assertIsNotNone(worktree)
        self.assertEqual(worktree.origin_branch, "release/test")
        self.assertEqual(read_upstream(self.clone, "temp/second"), "release/test")

    def test_pushed_handoff_branch_becomes_the_origin_of_a_new_worktree(self):
        run(self.repo, "branch", "feature/handoff")
        commit_on_branch(self.repo, "feature/handoff", "progress.txt", "half done")
        run(self.clone, "fetch", "--quiet")

        worktree = worktrees.create_worktree(self.clone, "resume", "origin/feature/handoff")

        self.assertEqual(worktree.origin_branch, "feature/handoff")
        self.assertEqual(worktree.branch, "temp/resume")
        self.assertEqual((worktree.path / "progress.txt").read_text(), "half done")


class FailedCreationTest(WorktreesTestCase):
    def test_failed_worktree_add_saves_nothing(self):
        self.assertIsNone(worktrees.create_worktree(self.repo, "broken", "no-such-branch"))

        self.assertIsNone(self.read_state())
        self.assertIsNone(worktrees_state.load_repo_id(self.repo))
        self.assertIsNone(read(self.repo, "rev-parse", "--verify", "--quiet", "refs/heads/temp/broken"))

    def test_failed_worktree_add_keeps_the_local_branch_of_a_remote_only_origin(self):
        run(self.repo, "branch", "release/test")
        cloned = clone(self.repo, self.root / "clone")
        worktrees_state.save_repo_id(cloned, "a1b2c3d4")
        occupied = self.worktrees_dir / "a1b2c3d4" / "busy"
        occupied.mkdir(parents=True)
        (occupied / "notes.txt").write_text("keep me")
        state_before = self.read_state()

        self.assertIsNone(worktrees.create_worktree(cloned, "busy", "origin/release/test"))

        self.assertEqual(self.read_state(), state_before)
        self.assertEqual(read_upstream(cloned, "release/test"), "origin/release/test")
        self.assertEqual((occupied / "notes.txt").read_text(), "keep me")


class BranchListTest(WorktreesTestCase):
    def test_temp_branches_are_excluded_local_and_remote(self):
        run(self.repo, "branch", "temp/pushed")
        cloned = clone(self.repo, self.root / "clone")
        worktrees.create_worktree(cloned, "local", "dev")

        branches = worktrees.list_branches(cloned)

        self.assertNotIn("temp/local", branches)
        self.assertNotIn("origin/temp/pushed", branches)
        self.assertNotIn("temp/pushed", branches)

    def test_local_branches_come_before_remote_only_ones(self):
        run(self.repo, "branch", "stage")
        cloned = clone(self.repo, self.root / "clone")
        run(cloned, "branch", "--quiet", "local-only")

        self.assertEqual(worktrees.list_branches(cloned), ["local-only", "master", "origin/dev", "origin/stage"])

    def test_existing_branch_is_local_or_remote(self):
        cloned = clone(self.repo, self.root / "clone")

        self.assertTrue(worktrees.is_existing_branch(self.repo, "dev"))
        self.assertTrue(worktrees.is_existing_branch(cloned, "origin/dev"))
        self.assertFalse(worktrees.is_existing_branch(cloned, "dev"))
        self.assertFalse(worktrees.is_existing_branch(cloned, "origin/nope"))
        self.assertFalse(worktrees.is_existing_branch(self.repo, "nope"))


class LoadTest(WorktreesTestCase):
    def test_worktrees_are_sorted_by_name(self):
        worktrees.create_worktree(self.repo, "beta", "dev")
        worktrees.create_worktree(self.repo, "Alpha", "dev")

        self.assertEqual([worktree.name for worktree in worktrees.load_worktrees(self.repo)], ["Alpha", "beta"])

    def test_origin_is_read_from_git(self):
        worktrees.create_worktree(self.repo, "feature", "dev")
        run(self.repo, "branch", "--quiet", "--set-upstream-to=master", "temp/feature")

        self.assertEqual(worktrees.load_worktrees(self.repo)[0].origin_branch, "master")

    def test_worktree_without_upstream_has_no_origin(self):
        repo_dir = worktrees.create_worktree(self.repo, "first", "dev").path.parent
        self.add_foreign_worktree(self.repo, repo_dir / "manual", "temp/manual")

        manual = next(worktree for worktree in worktrees.load_worktrees(self.repo) if worktree.name == "manual")

        self.assertIsNone(manual.origin_branch)
        self.assertFalse(manual.is_merged)

    def test_worktrees_not_made_by_the_launcher_are_ignored(self):
        kept = worktrees.create_worktree(self.repo, "kept", "dev")
        self.add_foreign_worktree(self.repo, self.outside_dir / "elsewhere", "temp/elsewhere")
        self.add_foreign_worktree(self.repo, kept.path.parent / "other", "other")

        self.assertEqual(worktrees.load_worktrees(self.repo), [kept])

    def test_list_does_not_depend_on_the_state_file_beyond_the_repo_id(self):
        worktree = worktrees.create_worktree(self.repo, "feature", "dev")
        repo_id = worktrees_state.load_repo_id(self.repo)
        self.state_file.unlink()
        worktrees_state.save_repo_id(self.repo, repo_id)

        self.assertEqual(worktrees.load_worktrees(self.repo), [worktree])


class MergedTest(WorktreesTestCase):
    def setUp(self):
        super().setUp()
        run(self.repo, "branch", "feature/pr")
        run(self.repo, "branch", "feature/open")
        self.clone = clone(self.repo, self.root / "clone")
        worktrees.create_worktree(self.clone, "merged-one", "origin/feature/pr")
        worktrees.create_worktree(self.clone, "open-one", "origin/feature/open")
        run(self.clone, "branch", "--quiet", "local-only")
        worktrees.create_worktree(self.clone, "local-one", "local-only")
        # INFO: The PR branch is merged then deleted on the remote
        run(self.repo, "branch", "--quiet", "-D", "feature/pr")

    def merged_names(self):
        return [worktree.name for worktree in worktrees.load_worktrees(self.clone) if worktree.is_merged]

    def fetch_prune(self):
        process = worktrees.start_fetch_prune(self.clone)
        process.wait(timeout=30)

        return process.returncode

    def test_gone_upstream_of_the_origin_marks_the_worktree_merged(self):
        self.assertEqual(self.fetch_prune(), 0)

        self.assertEqual(self.merged_names(), ["merged-one"])

    def test_nothing_is_merged_before_the_fetch(self):
        self.assertEqual(self.merged_names(), [])

    def test_failed_fetch_keeps_the_known_state(self):
        run(self.clone, "remote", "set-url", "origin", str(self.root / "no-such-remote"))

        self.assertNotEqual(self.fetch_prune(), 0)
        self.assertEqual(self.merged_names(), [])


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

    def make_repo_dir(self):
        worktrees_state.save_repo_id(self.repo, "a1b2c3d4")
        repo_dir = self.worktrees_dir / "a1b2c3d4"
        repo_dir.mkdir(parents=True)

        return repo_dir

    def test_worktree_unregistered_by_git_leaves_the_list(self):
        kept = worktrees.create_worktree(self.repo, "kept", "dev")
        removed = worktrees.create_worktree(self.repo, "removed", "dev")
        run(self.repo, "worktree", "remove", "--force", str(removed.path))

        self.assertEqual(worktrees.load_worktrees(self.repo), [kept])

    def test_empty_folder_left_by_an_unregistered_worktree_is_removed(self):
        kept = worktrees.create_worktree(self.repo, "kept", "dev")
        removed = worktrees.create_worktree(self.repo, "removed", "dev")
        self.unregister(removed)

        self.assertEqual(worktrees.load_worktrees(self.repo), [kept])
        self.assertFalse(removed.path.exists())
        self.assertTrue(kept.path.exists())
        self.assertIsNone(worktrees.validate_worktree_name(self.repo, "removed"))

    def test_non_empty_unknown_folder_is_kept(self):
        notes = self.make_repo_dir() / "notes"
        notes.mkdir()
        (notes / "todo.txt").write_text("keep me")

        self.assertEqual(worktrees.load_worktrees(self.repo), [])
        self.assertEqual((notes / "todo.txt").read_text(), "keep me")

    def test_unknown_file_is_kept(self):
        repo_dir = self.make_repo_dir()
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
