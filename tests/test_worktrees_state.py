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
        state_patch = patch("launcher.worktrees_state.WORKTREES_STATE_FILE", Path(temp_dir.name) / "worktrees_state.json")
        state_patch.start()
        self.addCleanup(state_patch.stop)

    def test_unknown_repo_has_no_state(self):
        self.assertIsNone(worktrees_state.load_repo_id(REPO))
        self.assertEqual(worktrees_state.load_base_branches(REPO), [])
        self.assertEqual(worktrees_state.load_worktree_sources(REPO), {})

    def test_saved_values_are_read_back_per_repo(self):
        worktrees_state.save_repo_id(REPO, "a1b2c3d4")
        worktrees_state.save_base_branches(REPO, ["release/test", "stage"])
        worktrees_state.save_worktree(REPO, "quick-fix", "stage")

        self.assertEqual(worktrees_state.load_repo_id(REPO), "a1b2c3d4")
        self.assertEqual(worktrees_state.load_base_branches(REPO), ["release/test", "stage"])
        self.assertEqual(worktrees_state.load_worktree_sources(REPO), {"quick-fix": "stage"})
        self.assertEqual(worktrees_state.load_base_branches(OTHER_REPO), [])

    def test_forget_worktree_keeps_the_others(self):
        worktrees_state.save_worktree(REPO, "a", "dev")
        worktrees_state.save_worktree(REPO, "b", "dev")
        worktrees_state.forget_worktree(REPO, "a")

        self.assertEqual(worktrees_state.load_worktree_sources(REPO), {"b": "dev"})
