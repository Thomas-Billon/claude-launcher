import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher import worktrees_state

REPO = Path("C:/Projets/Shope")
OTHER_REPO = Path("C:/Projets/Shope_Copy")


class WorktreesStateTest(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.state_file = Path(temp_dir.name) / "worktrees_state.json"
        state_patch = patch("launcher.worktrees_state.WORKTREES_STATE_FILE", self.state_file)
        state_patch.start()
        self.addCleanup(state_patch.stop)

    def read_repo_state(self, repo):
        return json.loads(self.state_file.read_text(encoding="utf-8"))["repos"][str(repo)]

    def test_unknown_repo_has_no_state(self):
        self.assertIsNone(worktrees_state.load_repo_id(REPO))
        self.assertEqual(worktrees_state.load_favorite_branches(REPO), [])

    def test_repo_id_is_read_back_per_repo(self):
        worktrees_state.save_repo_id(REPO, "a1b2c3d4")

        self.assertEqual(worktrees_state.load_repo_id(REPO), "a1b2c3d4")
        self.assertIsNone(worktrees_state.load_repo_id(OTHER_REPO))

    def test_toggle_adds_then_removes_a_favorite_branch(self):
        self.assertTrue(worktrees_state.toggle_favorite_branch(REPO, "dev"))
        self.assertTrue(worktrees_state.toggle_favorite_branch(REPO, "origin/stage"))

        self.assertEqual(worktrees_state.load_favorite_branches(REPO), ["dev", "origin/stage"])
        self.assertEqual(self.read_repo_state(REPO)["favorite_branches"], ["dev", "origin/stage"])

        self.assertFalse(worktrees_state.toggle_favorite_branch(REPO, "dev"))

        self.assertEqual(worktrees_state.load_favorite_branches(REPO), ["origin/stage"])
        self.assertEqual(self.read_repo_state(REPO)["favorite_branches"], ["origin/stage"])

    def test_favorite_branches_are_per_repo(self):
        worktrees_state.toggle_favorite_branch(REPO, "dev")

        self.assertEqual(worktrees_state.load_favorite_branches(OTHER_REPO), [])

    def test_favorite_branches_keep_the_repo_id(self):
        worktrees_state.save_repo_id(REPO, "a1b2c3d4")
        worktrees_state.toggle_favorite_branch(REPO, "dev")

        self.assertEqual(self.read_repo_state(REPO), {"id": "a1b2c3d4", "favorite_branches": ["dev"]})

    def test_old_base_branches_are_ignored(self):
        old_state = {"repos": {str(REPO): {"id": "a1b2c3d4", "base_branches": ["dev"], "worktrees": {"fix": {"source_branch": "dev"}}}}}
        self.state_file.write_text(json.dumps(old_state), encoding="utf-8")

        self.assertEqual(worktrees_state.load_favorite_branches(REPO), [])
        self.assertEqual(worktrees_state.load_repo_id(REPO), "a1b2c3d4")

    def test_old_api_is_removed(self):
        for name in ("load_base_branches", "save_base_branches", "load_worktree_sources", "save_worktree", "forget_worktree"):
            self.assertFalse(hasattr(worktrees_state, name), name)
